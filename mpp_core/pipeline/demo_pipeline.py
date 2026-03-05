import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from mpp_core.config import Settings
from mpp_core.export import OzonApiClient, OzonDbExportRunResult, OzonDbExportRunner, OzonDbPayloadBuilder
from mpp_core.export.ozon_db_payload_builder import DEFAULT_PLACEHOLDER_IMAGE_URL
from mpp_core.ingestion import Tmapi1688Client, Tmapi1688IngestionResult, Tmapi1688IngestionService
from mpp_core.mapping import CategoryMappingService, CategoryTranslationService
from mpp_core.pipeline.image_normalization import normalize_product_images
from mpp_core.storage import ProductRecord, SqliteProductRepository
from mpp_core.storage.sqlite.database import get_connection

_DEFAULT_DEMO_TMAPI_CAT_IDS = [
    201372301,
    124740029,
    201909501,
    201771102,
    201754501,
    201689102,
    201353014,
    125062013,
]


@dataclass
class DemoPipelineRunResult:
    reset_deleted: int
    ingestion_products: int
    sqlite_persisted: int
    translated: int
    translation_fallback: int
    mapped: int
    ready_for_export: int
    exported: int
    failed_export: int


def reset_demo_state(db_path: str) -> int:
    with get_connection(db_path) as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM products").fetchone()
        deleted = int(row["total"]) if row is not None else 0
        connection.execute("DELETE FROM products")
        connection.commit()
    return deleted


class DemoPipelineRunner:
    def __init__(
        self,
        *,
        settings: Optional[Settings] = None,
        top_limit: int = 10,
        logs_dir_mapping: Path = Path("logs/mapping"),
    ) -> None:
        self._settings = settings or Settings.from_env()
        self._top_limit = max(1, top_limit)
        self._logs_dir_mapping = logs_dir_mapping
        self._repository = SqliteProductRepository(db_path=self._settings.sqlite_db_path)
        self._repository.init_db()

    def run(self) -> DemoPipelineRunResult:
        print("STEP 1 RESET STATE")
        deleted = reset_demo_state(self._settings.sqlite_db_path)
        print(f"- sqlite db: {self._settings.sqlite_db_path}")
        print(f"- deleted products: {deleted}")

        print("STEP 2 1688 INGESTION")
        ingestion_result, sqlite_stats = self._run_tmapi_ingestion()
        print(f"- mode: {ingestion_result.mode}")
        print(f"- candidates: {ingestion_result.candidates_count}")
        print(f"- unique_candidates: {ingestion_result.unique_candidates_count}")
        print(f"- products: {ingestion_result.products_count}")
        print(f"- raw output: {ingestion_result.output_path}")
        print(f"- 1688 log: {ingestion_result.api_log_path}")
        print(f"- sqlite inserted: {sqlite_stats['inserted']}")
        print(f"- sqlite updated: {sqlite_stats['updated']}")
        print(f"- sqlite persisted_total: {sqlite_stats['persisted_total']}")
        if ingestion_result.warning:
            print(f"- warning: {ingestion_result.warning}")

        print("STEP 3 TRANSLATION")
        translation_result = CategoryTranslationService().run(self._repository)
        translation_fallback = self._apply_demo_translation_fallback()
        print(f"- translation candidates: {translation_result.candidates}")
        print(f"- translation translated: {translation_result.translated}")
        print(f"- translation fallback: {translation_fallback}")
        print(f"- translation skipped: {translation_result.skipped}")

        print("STEP 4 CATEGORY MAPPING")
        mapping_result = CategoryMappingService().run(self._repository)
        ready_for_export = CategoryMappingService.promote_to_ready_for_export(self._repository)
        print(f"- mapping candidates: {mapping_result.candidates}")
        print(f"- mapping mapped: {mapping_result.mapped}")
        print(f"- mapping skipped: {mapping_result.skipped}")
        print(f"- ready_for_export: {ready_for_export}")

        print("STEP 5 OZON EXPORT")
        export_result = self._run_ozon_export()
        print(f"- selected: {export_result.selected}")
        print(f"- exported: {export_result.exported}")
        print(f"- failed: {export_result.failed}")
        print(f"- ozon request log: {export_result.request_log_path}")
        print(f"- ozon response log: {export_result.response_log_path}")

        summary = DemoPipelineRunResult(
            reset_deleted=deleted,
            ingestion_products=ingestion_result.products_count,
            sqlite_persisted=sqlite_stats["persisted_total"],
            translated=translation_result.translated + translation_fallback,
            translation_fallback=translation_fallback,
            mapped=mapping_result.mapped,
            ready_for_export=ready_for_export,
            exported=export_result.exported,
            failed_export=export_result.failed,
        )
        self._write_mapping_log(summary=summary)

        print("PIPELINE FINISHED")
        print(f"- exported: {summary.exported}")
        print(f"- failed_export: {summary.failed_export}")
        print(f"- mapping log: {self._logs_dir_mapping / 'pipeline_demo.json'}")
        return summary

    def _run_tmapi_ingestion(self) -> tuple[Tmapi1688IngestionResult, dict[str, int]]:
        if not self._settings.has_tmapi_token:
            raise RuntimeError(
                "TMAPI token is required. Set MPP_TMAPI_TOKEN in .env"
            )

        client = Tmapi1688Client(
            api_token=self._settings.tmapi_token or "",
            base_url=self._settings.tmapi_base_url,
            timeout_sec=self._settings.tmapi_timeout_sec,
            verify_ssl=self._settings.tmapi_verify_ssl,
        )
        ingestion_service = Tmapi1688IngestionService(client=client)
        cat_ids = self._settings.tmapi_cat_ids or list(_DEFAULT_DEMO_TMAPI_CAT_IDS)
        ingestion_result = ingestion_service.run_top_sales(
            cat_ids=cat_ids,
            pages_per_category=max(1, self._settings.tmapi_category_pages),
            top_limit=self._top_limit,
            page_size=20,
            sort="sales",
            language="en",
        )
        sqlite_stats = self._persist_tmapi_products_to_sqlite(
            output_path=ingestion_result.output_path
        )
        return ingestion_result, sqlite_stats

    def _run_ozon_export(self) -> OzonDbExportRunResult:
        if not self._settings.has_ozon_seller_credentials:
            raise RuntimeError(
                "Ozon credentials are required. "
                "Set MPP_OZON_SELLER_CLIENT_ID and MPP_OZON_SELLER_API_KEY in .env"
            )

        client = OzonApiClient(
            client_id=self._settings.ozon_seller_client_id or "",
            api_key=self._settings.ozon_seller_api_key or "",
            base_url=self._settings.ozon_seller_base_url,
            verify_ssl=self._settings.ozon_verify_ssl,
            timeout_sec=self._settings.ozon_request_timeout_sec,
        )
        runner = OzonDbExportRunner(
            settings=self._settings,
            repository=self._repository,
            client=client,
            payload_builder=OzonDbPayloadBuilder(),
            logs_dir=Path("logs/ozon"),
            export_limit=self._top_limit,
        )
        return runner.run()

    def _persist_tmapi_products_to_sqlite(self, *, output_path: Path) -> dict[str, int]:
        raw_products = self._load_raw_1688_products(output_path)
        inserted = 0
        updated = 0
        skipped = 0
        seen_item_ids: set[str] = set()

        for raw_product in raw_products:
            item_id = str(raw_product.get("item_id") or "").strip()
            if not item_id or item_id in seen_item_ids:
                skipped += 1
                continue
            seen_item_ids.add(item_id)

            existing = self._repository.get_product_by_1688_id(item_id)
            status = "new"
            normalized_images = normalize_product_images(
                raw_product,
                placeholder_image_url=DEFAULT_PLACEHOLDER_IMAGE_URL,
            )
            self._repository.upsert_product(
                ProductRecord(
                    item_id_1688=item_id,
                    title=self._normalize_string(raw_product.get("title")),
                    title_raw=self._normalize_string(raw_product.get("title")),
                    category_path_1688=self._normalize_string(raw_product.get("category_id")),
                    category_1688=self._normalize_string(raw_product.get("category_id")),
                    price=self._extract_price(raw_product),
                    status=status,
                )
            )
            self._repository.replace_product_images(
                item_id_1688=item_id,
                image_urls=normalized_images,
                source="tmapi",
            )

            if existing is None:
                inserted += 1
            else:
                updated += 1

        return {
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "persisted_total": inserted + updated,
        }

    @staticmethod
    def _load_raw_1688_products(output_path: Path) -> list[dict[str, Any]]:
        if not output_path.exists():
            raise RuntimeError(f"TMAPI output file not found: {output_path}")

        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid TMAPI output JSON: {output_path}") from exc

        if not isinstance(payload, list):
            raise RuntimeError(f"Invalid TMAPI output format (expected list): {output_path}")
        return [item for item in payload if isinstance(item, dict)]

    @staticmethod
    def _extract_price(raw_product: dict[str, Any]) -> Optional[float]:
        price_range = raw_product.get("price_range")
        if isinstance(price_range, dict):
            for key in ("price", "sale_price", "min_price", "max_price", "start_price", "origin_price"):
                parsed = DemoPipelineRunner._to_float(price_range.get(key))
                if parsed is not None:
                    return parsed

        sku_list = raw_product.get("sku")
        if isinstance(sku_list, list):
            for sku in sku_list:
                if not isinstance(sku, dict):
                    continue
                for key in ("sale_price", "price", "origin_price"):
                    parsed = DemoPipelineRunner._to_float(sku.get(key))
                    if parsed is not None:
                        return parsed
        return None

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text:
            return None
        try:
            return float(text.replace(",", "."))
        except ValueError:
            return None

    @staticmethod
    def _normalize_string(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _write_mapping_log(self, *, summary: DemoPipelineRunResult) -> None:
        self._logs_dir_mapping.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "reset_deleted": summary.reset_deleted,
                "ingestion_products": summary.ingestion_products,
                "sqlite_persisted": summary.sqlite_persisted,
                "translated": summary.translated,
                "translation_fallback": summary.translation_fallback,
                "mapped": summary.mapped,
                "ready_for_export": summary.ready_for_export,
                "exported": summary.exported,
                "failed_export": summary.failed_export,
            },
        }
        (self._logs_dir_mapping / "pipeline_demo.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _apply_demo_translation_fallback(self) -> int:
        new_products = self._repository.get_products_by_status("new")
        updated = 0
        for product in new_products:
            internal_category = self._resolve_fallback_internal_category(product)
            if self._repository.update_translation(product.item_id_1688, internal_category):
                updated += 1
        return updated

    @staticmethod
    def _resolve_fallback_internal_category(product: ProductRecord) -> str:
        source = " ".join(
            [
                str(product.title or ""),
                str(product.title_raw or ""),
                str(product.category_path_1688 or ""),
                str(product.category_1688 or ""),
            ]
        ).lower()
        if "patch" in source:
            return "warming_patches"
        if "towel" in source or "cleansing" in source:
            return "disposable_bed_sheets"
        return "collectible_toys"
