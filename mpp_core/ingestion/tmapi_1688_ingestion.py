import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from mpp_core.ingestion.dto import Raw1688Product
from mpp_core.ingestion.tmapi_1688_client import Tmapi1688Client


@dataclass
class Tmapi1688IngestionResult:
    mode: str
    products_count: int
    candidates_count: int
    unique_candidates_count: int
    output_path: Path
    api_log_path: Path
    warning: Optional[str] = None


class Tmapi1688IngestionService:
    def __init__(
        self,
        *,
        client: Tmapi1688Client,
        output_path: Path = Path("data/1688_products_raw.json"),
        api_log_path: Path = Path("logs/1688/api_response.json"),
    ) -> None:
        self._client = client
        self._output_path = output_path
        self._api_log_path = api_log_path

    def run(
        self,
        *,
        shop_url: Optional[str] = None,
        member_id: Optional[str] = None,
        limit: int = 10,
        page: int = 1,
        page_size: int = 10,
        sort: str = "sales",
    ) -> Tmapi1688IngestionResult:
        self._client.clear_api_logs()
        products: list[Raw1688Product] = []
        summary: dict[str, Any] = {"mode": "shop", "status": "failed"}
        warning: Optional[str] = None

        try:
            shop_items = self._collect_shop_items(
                shop_url=shop_url,
                member_id=member_id,
                limit=limit,
                page=page,
                page_size=page_size,
                sort=sort,
            )

            for item in shop_items:
                item_id = str(item.get("item_id") or "").strip()
                if not item_id:
                    continue
                detail = self._client.get_item_detail(item_id=item_id)
                products.append(self._map_detail_to_raw_product(detail))
                if len(products) >= limit:
                    break

            self._save_products(products)
            if len(products) < limit:
                warning = f"TMAPI ingestion returned {len(products)} products, expected {limit}"
            summary = {
                "mode": "shop",
                "status": "ok",
                "target_limit": limit,
                "products_count": len(products),
                "warning": warning,
            }
        finally:
            self._save_api_logs(self._client.api_logs, summary=summary)

        if not products:
            raise RuntimeError("TMAPI ingestion returned 0 products")

        return Tmapi1688IngestionResult(
            mode="shop",
            products_count=len(products),
            candidates_count=len(shop_items),
            unique_candidates_count=len(shop_items),
            output_path=self._output_path,
            api_log_path=self._api_log_path,
            warning=warning,
        )

    def run_top_sales(
        self,
        *,
        cat_ids: list[int],
        pages_per_category: int = 1,
        top_limit: int = 10,
        page_size: int = 20,
        sort: str = "sales",
        language: str = "en",
    ) -> Tmapi1688IngestionResult:
        if not cat_ids:
            raise ValueError("cat_ids must not be empty")

        self._client.clear_api_logs()
        products: list[Raw1688Product] = []
        ranked_candidates: list[dict[str, Any]] = []
        total_candidates = 0
        summary: dict[str, Any] = {"mode": "top_sales", "status": "failed"}
        warning: Optional[str] = None

        try:
            ranked_candidates, total_candidates = self._collect_top_sales_candidates(
                cat_ids=cat_ids,
                pages_per_category=max(1, pages_per_category),
                page_size=max(1, page_size),
                sort=sort,
                language=language,
            )

            top_candidates = ranked_candidates[: max(1, top_limit)]
            for candidate in top_candidates:
                item_id = candidate["item_id"]
                detail = self._client.get_item_detail(item_id=item_id)
                products.append(
                    self._map_detail_to_raw_product(
                        detail,
                        fallback_sales=candidate["sales_text"],
                    )
                )

            self._save_products(products)

            if len(products) < top_limit:
                warning = f"Collected {len(products)} products for top_limit={top_limit}"

            summary = {
                "mode": "top_sales",
                "status": "ok",
                "cat_ids": cat_ids,
                "pages_per_category": pages_per_category,
                "top_limit": top_limit,
                "total_candidates": total_candidates,
                "unique_candidates": len(ranked_candidates),
                "products_count": len(products),
                "warning": warning,
            }
        finally:
            self._save_api_logs(self._client.api_logs, summary=summary)

        if not products:
            raise RuntimeError("TMAPI top_sales ingestion returned 0 products")

        return Tmapi1688IngestionResult(
            mode="top_sales",
            products_count=len(products),
            candidates_count=total_candidates,
            unique_candidates_count=len(ranked_candidates),
            output_path=self._output_path,
            api_log_path=self._api_log_path,
            warning=warning,
        )

    def _collect_shop_items(
        self,
        *,
        shop_url: Optional[str],
        member_id: Optional[str],
        limit: int,
        page: int,
        page_size: int,
        sort: str,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen_item_ids: set[str] = set()
        current_page = page

        while len(items) < limit:
            page_items = self._client.get_shop_products(
                shop_url=shop_url,
                member_id=member_id,
                page=current_page,
                page_size=page_size,
                sort=sort,
            )
            if not page_items:
                break

            for item in page_items:
                item_id = str(item.get("item_id") or "").strip()
                if not item_id or item_id in seen_item_ids:
                    continue
                seen_item_ids.add(item_id)
                items.append(item)
                if len(items) >= limit:
                    break

            if len(page_items) < page_size:
                break
            current_page += 1

        return items[:limit]

    def _collect_top_sales_candidates(
        self,
        *,
        cat_ids: list[int],
        pages_per_category: int,
        page_size: int,
        sort: str,
        language: str,
    ) -> tuple[list[dict[str, Any]], int]:
        by_item_id: dict[str, dict[str, Any]] = {}
        total_candidates = 0

        for cat_id in cat_ids:
            for page in range(1, pages_per_category + 1):
                category_items = self._client.get_category_products_v2(
                    cat_id=cat_id,
                    page=page,
                    page_size=page_size,
                    sort=sort,
                    language=language,
                )
                if not category_items:
                    break

                total_candidates += len(category_items)
                for item in category_items:
                    item_id = str(item.get("item_id") or "").strip()
                    if not item_id:
                        continue
                    sales_text = self._extract_sales_text(item)
                    sales_num = self._parse_sales_to_number(sales_text)
                    candidate = {
                        "item_id": item_id,
                        "sales_text": sales_text,
                        "sales_num": sales_num,
                        "cat_id": cat_id,
                        "item": item,
                    }
                    current = by_item_id.get(item_id)
                    if current is None or sales_num > current["sales_num"]:
                        by_item_id[item_id] = candidate

                if len(category_items) < page_size:
                    break

        ranked = sorted(
            by_item_id.values(),
            key=lambda candidate: (-candidate["sales_num"], candidate["item_id"]),
        )
        return ranked, total_candidates

    def _save_products(self, products: list[Raw1688Product]) -> None:
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [product.to_dict() for product in products]
        self._output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _save_api_logs(self, api_logs: list[dict[str, Any]], *, summary: Optional[dict[str, Any]] = None) -> None:
        self._api_log_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": self._now(),
            "base_url": self._client.base_url,
            "responses": api_logs,
            "summary": summary or {},
        }
        self._api_log_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _map_detail_to_raw_product(detail: dict[str, Any], *, fallback_sales: str = "") -> Raw1688Product:
        sale_count = str(detail.get("sale_count") or fallback_sales or "")
        return Raw1688Product(
            item_id=str(detail.get("item_id") or ""),
            title=str(detail.get("title") or ""),
            category_id=str(detail.get("category_id") or ""),
            images=Tmapi1688IngestionService._extract_images(detail.get("main_imgs")),
            sales=sale_count,
            attributes=Tmapi1688IngestionService._extract_attributes(detail.get("product_props")),
            sku=Tmapi1688IngestionService._extract_sku(detail.get("sku_props")),
            price_range=Tmapi1688IngestionService._extract_price_range(detail.get("sku_price_range")),
            shop=Tmapi1688IngestionService._extract_shop(detail.get("shop_info")),
        )

    @staticmethod
    def _extract_sales_text(item: dict[str, Any]) -> str:
        direct_value = item.get("sale_count") or item.get("sales") or item.get("sales_desc")
        if direct_value is not None:
            return str(direct_value)

        sale_info = item.get("sale_info")
        if isinstance(sale_info, dict):
            quantity = sale_info.get("sale_quantity_90days")
            if quantity is not None:
                return str(quantity)
        return ""

    @staticmethod
    def _parse_sales_to_number(raw_sales: str) -> int:
        if raw_sales is None:
            return 0
        text = str(raw_sales).strip().lower()
        if not text:
            return 0

        text = text.replace(",", "").replace("+", "").replace(" ", "")
        multiplier = 1.0
        if "万" in text:
            multiplier = 10_000.0
            text = text.replace("万", "")
        elif text.endswith("k"):
            multiplier = 1_000.0
            text = text[:-1]
        elif text.endswith("w"):
            multiplier = 10_000.0
            text = text[:-1]
        elif text.endswith("m"):
            multiplier = 1_000_000.0
            text = text[:-1]

        match = re.search(r"\d+(?:\.\d+)?", text)
        if not match:
            return 0
        try:
            return int(float(match.group(0)) * multiplier)
        except ValueError:
            return 0

    @staticmethod
    def _extract_images(raw_images: Any) -> list[str]:
        if not isinstance(raw_images, list):
            return []

        urls: list[str] = []
        for image in raw_images:
            if isinstance(image, str):
                clean = image.strip()
                if clean:
                    urls.append(clean)
                continue
            if not isinstance(image, dict):
                continue
            for key in ("img_url", "url", "image_url", "big"):
                value = image.get(key)
                if isinstance(value, str) and value.strip():
                    urls.append(value.strip())
                    break
        return urls

    @staticmethod
    def _extract_attributes(raw_product_props: Any) -> dict[str, Any]:
        if isinstance(raw_product_props, dict):
            return raw_product_props
        if not isinstance(raw_product_props, list):
            return {}

        attributes: dict[str, Any] = {}
        for prop in raw_product_props:
            if not isinstance(prop, dict):
                continue

            key = prop.get("name") or prop.get("prop") or prop.get("attr_name") or prop.get("title")
            if key is None:
                continue

            value = prop.get("value") or prop.get("prop_value") or prop.get("attr_value")
            if value is None:
                raw_values = prop.get("values")
                if isinstance(raw_values, list):
                    value = ", ".join(str(part) for part in raw_values if part is not None)

            attributes[str(key)] = value if value is not None else ""
        return attributes

    @staticmethod
    def _extract_sku(raw_sku_props: Any) -> list[dict[str, Any]]:
        if isinstance(raw_sku_props, list):
            return [sku for sku in raw_sku_props if isinstance(sku, dict)]
        if isinstance(raw_sku_props, dict):
            return [raw_sku_props]
        return []

    @staticmethod
    def _extract_price_range(raw_price_range: Any) -> dict[str, Any]:
        if isinstance(raw_price_range, dict):
            return raw_price_range
        return {}

    @staticmethod
    def _extract_shop(raw_shop_info: Any) -> dict[str, Any]:
        if isinstance(raw_shop_info, dict):
            return raw_shop_info
        return {}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
