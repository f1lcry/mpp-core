from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawSKU:
    sku_id: str
    price: float
    currency: str
    stock: int = 0


@dataclass
class RawProductDTO:
    source_product_id: str
    title: str
    description: str
    source_category_id: str
    raw_attributes: dict[str, str] = field(default_factory=dict)
    image_urls: list[str] = field(default_factory=list)
    skus: list[RawSKU] = field(default_factory=list)


@dataclass
class Raw1688Product:
    item_id: str
    title: str
    category_id: str
    images: list[str] = field(default_factory=list)
    sales: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    sku: list[dict[str, Any]] = field(default_factory=list)
    price_range: dict[str, Any] = field(default_factory=dict)
    shop: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "title": self.title,
            "category_id": self.category_id,
            "images": self.images,
            "sales": self.sales,
            "attributes": self.attributes,
            "sku": self.sku,
            "price_range": self.price_range,
            "shop": self.shop,
        }
