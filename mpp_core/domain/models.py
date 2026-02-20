from dataclasses import dataclass, field
from typing import Optional

from mpp_core.domain.enums import PipelineStage, ProductStatus


@dataclass
class Attribute:
    name: str
    value: str
    source_name: Optional[str] = None


@dataclass
class Category:
    internal_id: str
    name: str
    source_id: Optional[str] = None


@dataclass
class SKU:
    sku_id: str
    price: float
    currency: str
    stock: int = 0


@dataclass
class Product:
    source_product_id: str
    title: str
    description: str = ""
    category: Optional[Category] = None
    attributes: list[Attribute] = field(default_factory=list)
    skus: list[SKU] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    ai_description: Optional[str] = None
    status: ProductStatus = ProductStatus.NEW
    current_stage: PipelineStage = PipelineStage.INGESTION
    rejection_reason: Optional[str] = None
    external_export_id: Optional[str] = None
