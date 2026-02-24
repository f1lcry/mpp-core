import re
from datetime import datetime, timezone
from uuid import uuid4

from mpp_core.domain import InternalProduct
from mpp_core.mapping import OzonCategoryMapping


class JsonPayloadBuilder:
    def __init__(
        self,
        *,
        width_mm: int = 120,
        height_mm: int = 30,
        depth_mm: int = 120,
        weight_g: int = 450,
    ) -> None:
        self._width_mm = width_mm
        self._height_mm = height_mm
        self._depth_mm = depth_mm
        self._weight_g = weight_g

    def build(self, product: InternalProduct, mapping: OzonCategoryMapping) -> dict:
        required_attributes = mapping.required_attributes or list(mapping.attributes.keys())
        missing_attributes = [
            attribute_name
            for attribute_name in required_attributes
            if not self._has_value(self._resolve_attribute_value(product, mapping, attribute_name))
        ]
        if missing_attributes:
            missing = ", ".join(missing_attributes)
            raise ValueError(
                f"Product '{product.title}' is missing required attributes: {missing}"
            )

        attributes_payload = []
        for attribute_name, attribute_id in mapping.attributes.items():
            value = self._resolve_attribute_value(product, mapping, attribute_name)
            if not self._has_value(value):
                continue
            attributes_payload.append(
                {
                    "id": attribute_id,
                    "value": str(value),
                }
            )

        return {
            "offer_id": self._make_offer_id(product),
            "name": product.title,
            "description": product.description,
            "price": str(int(product.price)) if product.price.is_integer() else str(product.price),
            "currency_code": "RUB",
            "category_id": mapping.category_id,
            "type_id": mapping.type_id,
            "images": product.images,
            "attributes": attributes_payload,
            "width": self._width_mm,
            "height": self._height_mm,
            "depth": self._depth_mm,
            "dimension_unit": "mm",
            "weight": self._weight_g,
            "weight_unit": "g",
        }

    @staticmethod
    def _has_value(value: object) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        return True

    @staticmethod
    def _resolve_attribute_value(
        product: InternalProduct,
        mapping: OzonCategoryMapping,
        attribute_name: str,
    ) -> object:
        product_value = product.attributes.get(attribute_name)
        if JsonPayloadBuilder._has_value(product_value):
            return product_value

        default_value = mapping.default_values.get(attribute_name)
        if JsonPayloadBuilder._has_value(default_value):
            return default_value

        if attribute_name == "model":
            return product.title
        return product_value

    @staticmethod
    def _make_offer_id(product: InternalProduct) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", product.category.lower()).strip("-")
        if not slug:
            slug = "product"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        suffix = uuid4().hex[:6]
        return f"json-{slug}-{stamp}-{suffix}"
