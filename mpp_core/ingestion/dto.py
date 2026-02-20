from dataclasses import dataclass, field


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
