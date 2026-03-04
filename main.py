import json
import sys
from pathlib import Path
from typing import Any, Optional

from mpp_core.compliance import AlwaysApproveRule, ComplianceEngine
from mpp_core.config import Settings
from mpp_core.domain import Category
from mpp_core.enrichment import EnrichmentService, NoOpImageProcessor, StubAIProvider
from mpp_core.export import (
    OzonApiClient,
    OzonExporter,
    OzonJsonImportRunner,
    OzonMvpRunner,
    OzonPayloadBuilder,
)
from mpp_core.ingestion import Alibaba1688Client, Tmapi1688Client, Tmapi1688IngestionService
from mpp_core.mapping import (
    AttributeMapper,
    CategoryMapper,
    CategoryMappingService,
    CategoryTranslationService,
)
from mpp_core.pipeline import PipelineOrchestrator
from mpp_core.storage import (
    InMemoryAttributeMappingStore,
    InMemoryCategoryMappingStore,
    InMemoryPipelineEventRepository,
    InMemoryProductRepository,
    ProductRecord,
    SqliteProductRepository,
)

def build_orchestrator(settings: Settings) -> PipelineOrchestrator:
    ingestion_client = Alibaba1688Client(batch_size=settings.ingestion_batch_size)

    compliance_engine = ComplianceEngine(rules=[AlwaysApproveRule()])

    category_mapping_store = InMemoryCategoryMappingStore(
        mapping={
            "1688-cat-home-appliances": Category(
                internal_id="home-kitchen-small-appliances",
                name="Home Kitchen / Small Appliances",
                source_id="1688-cat-home-appliances",
            )
        }
    )
    attribute_mapping_store = InMemoryAttributeMappingStore(
        mapping={"Color": "color", "Voltage": "voltage"}
    )

    category_mapper = CategoryMapper(mapping_store=category_mapping_store)
    attribute_mapper = AttributeMapper(mapping_store=attribute_mapping_store)

    enrichment_service = EnrichmentService(
        ai_provider=StubAIProvider(),
        image_processor=NoOpImageProcessor(),
    )

    payload_builder = OzonPayloadBuilder()
    exporter = OzonExporter(
        client_id=settings.ozon_seller_client_id,
        api_key=settings.ozon_seller_api_key,
    )

    product_repository = InMemoryProductRepository()
    event_repository = InMemoryPipelineEventRepository()

    return PipelineOrchestrator(
        ingestion_client=ingestion_client,
        compliance_engine=compliance_engine,
        category_mapper=category_mapper,
        attribute_mapper=attribute_mapper,
        enrichment_service=enrichment_service,
        payload_builder=payload_builder,
        exporter=exporter,
        product_repository=product_repository,
        event_repository=event_repository,
    )


def run_demo() -> None:
    settings = Settings.from_env()
    orchestrator = build_orchestrator(settings)
    processed = orchestrator.run_once()

    print(f"Processed products: {len(processed)}")
    for product in processed:
        print(
            f"- {product.source_product_id} | status={product.status.value} | "
            f"stage={product.current_stage.value} | export_id={product.external_export_id}"
        )


def run_ozon_mvp_import() -> None:
    settings = Settings.from_env()
    if not settings.has_ozon_seller_credentials:
        raise RuntimeError(
            "Ozon credentials are required. "
            "Set MPP_OZON_SELLER_CLIENT_ID and MPP_OZON_SELLER_API_KEY in .env"
        )

    client = OzonApiClient(
        client_id=settings.ozon_seller_client_id or "",
        api_key=settings.ozon_seller_api_key or "",
        base_url=settings.ozon_seller_base_url,
        verify_ssl=settings.ozon_verify_ssl,
        timeout_sec=settings.ozon_request_timeout_sec,
    )
    runner = OzonMvpRunner(client=client, logs_dir=Path("logs/ozon"))
    result = runner.run()

    print("Ozon MVP import completed")
    print(f"- offer_id: {result.offer_id}")
    print(f"- task_id: {result.task_id}")
    print(f"- status: {result.import_status}")
    print(f"- description_category_id: {result.description_category_id}")
    print(f"- type_id: {result.type_id}")
    print(f"- request log: {result.request_log_path}")
    print(f"- response log: {result.response_log_path}")


def run_ozon_json_import() -> None:
    settings = Settings.from_env()
    if not settings.has_ozon_seller_credentials:
        raise RuntimeError(
            "Ozon credentials are required. "
            "Set MPP_OZON_SELLER_CLIENT_ID and MPP_OZON_SELLER_API_KEY in .env"
        )

    client = OzonApiClient(
        client_id=settings.ozon_seller_client_id or "",
        api_key=settings.ozon_seller_api_key or "",
        base_url=settings.ozon_seller_base_url,
        verify_ssl=settings.ozon_verify_ssl,
        timeout_sec=settings.ozon_request_timeout_sec,
    )
    runner = OzonJsonImportRunner(
        client=client,
        products_path=Path("data/products.json"),
        mapping_path=Path("data/mapping.json"),
        logs_dir=Path("logs/ozon"),
    )
    result = runner.run()

    print("Ozon JSON import completed")
    print(f"- items: {result.items_count}")
    print(f"- task_id: {result.task_id}")
    print(f"- status: {result.import_status}")
    print(f"- request log: {result.request_log_path}")
    print(f"- response log: {result.response_log_path}")


def run_tmapi_test() -> None:
    settings = Settings.from_env()
    if not settings.has_tmapi_token:
        raise RuntimeError(
            "TMAPI token is required. "
            "Set MPP_TMAPI_TOKEN in .env"
        )

    client = Tmapi1688Client(
        api_token=settings.tmapi_token or "",
        base_url=settings.tmapi_base_url,
        timeout_sec=settings.tmapi_timeout_sec,
        verify_ssl=settings.tmapi_verify_ssl,
    )
    ingestion_service = Tmapi1688IngestionService(client=client)

    if settings.tmapi_mode == "top_sales":
        if not settings.has_tmapi_categories:
            raise RuntimeError(
                "TMAPI category list is required for top_sales mode. "
                "Set MPP_TMAPI_CAT_IDS in .env"
            )
        result = ingestion_service.run_top_sales(
            cat_ids=settings.tmapi_cat_ids,
            pages_per_category=settings.tmapi_category_pages,
            top_limit=settings.tmapi_top_limit,
            page_size=20,
            sort="sales",
            language="en",
        )
    elif settings.tmapi_mode == "shop":
        if not settings.has_tmapi_shop_selector:
            raise RuntimeError(
                "TMAPI shop selector is required for shop mode. "
                "Set MPP_TMAPI_SHOP_URL or MPP_TMAPI_MEMBER_ID in .env"
            )
        result = ingestion_service.run(
            shop_url=settings.tmapi_shop_url,
            member_id=settings.tmapi_member_id,
            page=1,
            page_size=10,
            sort="sales",
            limit=settings.tmapi_top_limit,
        )
    else:
        raise RuntimeError(
            "Unsupported TMAPI mode. "
            "Use MPP_TMAPI_MODE=top_sales or MPP_TMAPI_MODE=shop"
        )

    sqlite_stats = persist_tmapi_products_to_sqlite(
        output_path=result.output_path,
        db_path=settings.sqlite_db_path,
    )

    print("TMAPI 1688 ingestion test completed")
    print(f"- mode: {result.mode}")
    print(f"- candidates: {result.candidates_count}")
    print(f"- unique_candidates: {result.unique_candidates_count}")
    print(f"- products: {result.products_count}")
    print(f"- output: {result.output_path}")
    print(f"- api log: {result.api_log_path}")
    print(f"- sqlite db: {settings.sqlite_db_path}")
    print(f"- sqlite inserted: {sqlite_stats['inserted']}")
    print(f"- sqlite updated: {sqlite_stats['updated']}")
    print(f"- sqlite skipped: {sqlite_stats['skipped']}")
    print(f"- sqlite persisted_total: {sqlite_stats['persisted_total']}")
    if result.warning:
        print(f"- warning: {result.warning}")


def run_category_map() -> None:
    settings = Settings.from_env()
    repository = SqliteProductRepository(db_path=settings.sqlite_db_path)
    repository.init_db()

    translation_service = CategoryTranslationService()
    mapping_service = CategoryMappingService()

    translation_result = translation_service.run(repository)
    mapping_result = mapping_service.run(repository)
    ready_for_export = CategoryMappingService.promote_to_ready_for_export(repository)

    print("Category translation and mapping completed")
    print(f"- sqlite db: {settings.sqlite_db_path}")
    print(f"- translation candidates: {translation_result.candidates}")
    print(f"- translation translated: {translation_result.translated}")
    print(f"- translation skipped: {translation_result.skipped}")
    print(f"- mapping candidates: {mapping_result.candidates}")
    print(f"- mapping mapped: {mapping_result.mapped}")
    print(f"- mapping skipped: {mapping_result.skipped}")
    print(f"- ready_for_export updated: {ready_for_export}")


def persist_tmapi_products_to_sqlite(*, output_path: Path, db_path: str) -> dict[str, int]:
    repository = SqliteProductRepository(db_path=db_path)
    repository.init_db()

    raw_products = _load_raw_1688_products(output_path)
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

        existing = repository.get_product_by_1688_id(item_id)
        status = existing.status if existing is not None else "new"
        repository.upsert_product(
            ProductRecord(
                item_id_1688=item_id,
                title=_normalize_string(raw_product.get("title")),
                title_raw=_normalize_string(raw_product.get("title")),
                category_path_1688=_normalize_string(raw_product.get("category_id")),
                category_1688=_normalize_string(raw_product.get("category_id")),
                price=_extract_price(raw_product),
                status=status,
            )
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


def _extract_price(raw_product: dict[str, Any]) -> Optional[float]:
    price_range = raw_product.get("price_range")
    if isinstance(price_range, dict):
        for key in ("price", "sale_price", "min_price", "max_price", "start_price", "origin_price"):
            parsed = _to_float(price_range.get(key))
            if parsed is not None:
                return parsed

    sku_list = raw_product.get("sku")
    if isinstance(sku_list, list):
        for sku in sku_list:
            if not isinstance(sku, dict):
                continue
            for key in ("sale_price", "price", "origin_price"):
                parsed = _to_float(sku.get(key))
                if parsed is not None:
                    return parsed

    return None


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def _normalize_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def run_sqlite_test() -> None:
    settings = Settings.from_env()
    repository = SqliteProductRepository(db_path=settings.sqlite_db_path)
    repository.init_db()

    test_product = ProductRecord(
        item_id_1688="test-1688-001",
        title="Test product title",
        title_raw="Test product title",
        category_path_1688="1688-test-category",
        category_1688="1688-test-category",
        price=1.0,
        status="new",
    )

    repository.delete_product(test_product.item_id_1688)
    created = repository.create_product(test_product)
    fetched = repository.get_product_by_1688_id(test_product.item_id_1688)

    print("SQLite storage test")
    print()
    print("created product:")
    print(f"item_id_1688: {created.item_id_1688}")
    print(f"status: {created.status}")
    print()
    print("fetched product:")
    if fetched is None:
        print("item_id_1688: <not found>")
        print("status: <not found>")
    else:
        print(f"item_id_1688: {fetched.item_id_1688}")
        print(f"status: {fetched.status}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "ozon-mvp":
        run_ozon_mvp_import()
    elif len(sys.argv) > 1 and sys.argv[1] == "ozon-json-import":
        run_ozon_json_import()
    elif len(sys.argv) > 1 and sys.argv[1] == "tmapi-test":
        run_tmapi_test()
    elif len(sys.argv) > 1 and sys.argv[1] == "category-map":
        run_category_map()
    elif len(sys.argv) > 1 and sys.argv[1] == "sqlite-test":
        run_sqlite_test()
    else:
        run_demo()
