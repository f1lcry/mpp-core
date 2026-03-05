from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ProductRecord:
    id: Optional[int] = None
    item_id_1688: str = ""
    title: Optional[str] = None
    title_raw: Optional[str] = None
    title_en: Optional[str] = None
    title_ru: Optional[str] = None
    category_path_1688: Optional[str] = None
    category_1688: Optional[str] = None
    internal_category: Optional[str] = None
    category_internal: Optional[str] = None
    ozon_category_id: Optional[int] = None
    category_ozon: Optional[int] = None
    ozon_type_id: Optional[int] = None
    ozon_offer_id: Optional[str] = None
    price: Optional[float] = None
    images: list[str] = field(default_factory=list)
    status: str = "new"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
