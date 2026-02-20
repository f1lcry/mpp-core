from typing import Optional

from mpp_core.domain.models import Category, Product
from mpp_core.mapping.interfaces import AttributeMappingStore, CategoryMappingStore
from mpp_core.storage.repositories import PipelineEvent, PipelineEventRepository, ProductRepository


class InMemoryProductRepository(ProductRepository):
    def __init__(self) -> None:
        self._storage: dict[str, Product] = {}

    def save(self, product: Product) -> None:
        self._storage[product.source_product_id] = product

    def get(self, source_product_id: str) -> Optional[Product]:
        return self._storage.get(source_product_id)

    def list_all(self) -> list[Product]:
        return list(self._storage.values())


class InMemoryPipelineEventRepository(PipelineEventRepository):
    def __init__(self) -> None:
        self._events: list[PipelineEvent] = []

    def add(self, event: PipelineEvent) -> None:
        self._events.append(event)

    def list_all(self) -> list[PipelineEvent]:
        return list(self._events)


class InMemoryCategoryMappingStore(CategoryMappingStore):
    def __init__(self, mapping: dict[str, Category]) -> None:
        self._mapping = mapping

    def get_internal_category(self, source_category_id: str) -> Optional[Category]:
        return self._mapping.get(source_category_id)


class InMemoryAttributeMappingStore(AttributeMappingStore):
    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = mapping

    def get_internal_attribute_name(self, source_attribute_name: str) -> Optional[str]:
        return self._mapping.get(source_attribute_name)
