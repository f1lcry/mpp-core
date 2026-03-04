import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from mpp_core.storage.sqlite.models import ProductRecord


class OzonDbPayloadBuilder:
    def __init__(
        self,
        *,
        default_image_url: str = "https://upload.wikimedia.org/wikipedia/commons/3/3a/Cat03.jpg",
        default_price: float = 999.0,
        default_brand: str = "MPP Core",
    ) -> None:
        self._default_image_url = default_image_url
        self._default_price = default_price
        self._default_brand = default_brand

    def build_item(self, product: ProductRecord) -> dict[str, Any]:
        category_id = product.ozon_category_id if product.ozon_category_id is not None else product.category_ozon
        if category_id is None:
            raise ValueError(f"Missing category_id for product item_id_1688={product.item_id_1688}")

        if product.ozon_type_id is None:
            raise ValueError(f"Missing type_id for product item_id_1688={product.item_id_1688}")

        return {
            "offer_id": self._build_offer_id(product),
            "name": self._build_name(product),
            "description": self._build_description(product),
            "category_id": int(category_id),
            "type_id": int(product.ozon_type_id),
            "images": self._build_images(product),
            "attributes": self._build_attributes(product),
            "price": self._build_price(product),
        }

    def build_payload(self, products: list[ProductRecord]) -> dict[str, Any]:
        return {
            "items": [self.build_item(product) for product in products]
        }

    @staticmethod
    def _build_offer_id(product: ProductRecord) -> str:
        existing = str(product.ozon_offer_id or "").strip()
        if existing:
            return existing
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        suffix = uuid4().hex[:6]
        return f"mpp-{product.item_id_1688}-{stamp}-{suffix}"

    @staticmethod
    def _build_name(product: ProductRecord) -> str:
        for candidate in (product.title, product.title_ru, product.title_en, product.title_raw):
            clean = str(candidate or "").strip()
            if clean:
                return clean
        return f"Product {product.item_id_1688}"

    def _build_description(self, product: ProductRecord) -> str:
        raw_description = getattr(product, "description", None)
        clean_description = str(raw_description or "").strip()
        if clean_description:
            return clean_description
        return self._build_name(product)

    def _build_price(self, product: ProductRecord) -> str:
        price = float(product.price) if product.price is not None else self._default_price
        if price <= 0:
            price = self._default_price
        if price.is_integer():
            return str(int(price))
        return f"{price:.2f}".rstrip("0").rstrip(".")

    def _build_images(self, product: ProductRecord) -> list[str]:
        raw_images = getattr(product, "images", None)
        images = self._normalize_images(raw_images)
        if images:
            return images
        return [self._default_image_url]

    @staticmethod
    def _normalize_images(raw_images: Any) -> list[str]:
        if raw_images is None:
            return []
        if isinstance(raw_images, str):
            text = raw_images.strip()
            if not text:
                return []
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = [text]
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            return [text]
        if isinstance(raw_images, list):
            return [str(item).strip() for item in raw_images if str(item).strip()]
        return []

    def _build_attributes(self, product: ProductRecord) -> list[dict[str, Any]]:
        raw_attributes = getattr(product, "attributes", None)
        attributes = OzonDbPayloadBuilder._normalize_attributes(raw_attributes)
        if attributes:
            return attributes

        fallback_type = str(
            product.internal_category or product.category_internal or product.category_path_1688 or "Product"
        ).strip()
        return [
            {
                "id": 85,
                "complex_id": 0,
                "values": [{"value": self._default_brand}],
            },
            {
                "id": 9048,
                "complex_id": 0,
                "values": [{"value": self._build_name(product)}],
            },
            {
                "id": 8229,
                "complex_id": 0,
                "values": [{"value": fallback_type}],
            },
        ]

    @staticmethod
    def _normalize_attributes(raw_attributes: Any) -> list[dict[str, Any]]:
        if raw_attributes is None:
            return []

        if isinstance(raw_attributes, str):
            text = raw_attributes.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return []
            return OzonDbPayloadBuilder._normalize_attributes(parsed)

        if not isinstance(raw_attributes, list):
            return []

        attributes: list[dict[str, Any]] = []
        for attribute in raw_attributes:
            if not isinstance(attribute, dict):
                continue

            attribute_id = attribute.get("id")
            if attribute_id is None:
                continue
            try:
                normalized_id = int(attribute_id)
            except (TypeError, ValueError):
                continue

            if "values" in attribute and isinstance(attribute.get("values"), list):
                try:
                    complex_id = int(attribute.get("complex_id", 0))
                except (TypeError, ValueError):
                    complex_id = 0
                attributes.append(
                    {
                        "id": normalized_id,
                        "complex_id": complex_id,
                        "values": attribute["values"],
                    }
                )
                continue

            if "value" in attribute:
                attributes.append(
                    {
                        "id": normalized_id,
                        "complex_id": 0,
                        "values": [{"value": str(attribute["value"])}],
                    }
                )

        return attributes
