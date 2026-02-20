from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from mpp_core.domain.enums import PipelineStage, ProductStatus
from mpp_core.domain.models import Product


class ProductRepository(ABC):
    @abstractmethod
    def save(self, product: Product) -> None:
        """Persist product state."""

    @abstractmethod
    def get(self, source_product_id: str) -> Optional[Product]:
        """Get product by source identifier."""

    @abstractmethod
    def list_all(self) -> list[Product]:
        """List all persisted products."""


@dataclass
class PipelineEvent:
    source_product_id: str
    stage: PipelineStage
    status: ProductStatus
    created_at: datetime
    message: str = ""


class PipelineEventRepository(ABC):
    @abstractmethod
    def add(self, event: PipelineEvent) -> None:
        """Store pipeline event entry."""

    @abstractmethod
    def list_all(self) -> list[PipelineEvent]:
        """Return event history."""
