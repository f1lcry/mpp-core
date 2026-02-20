from mpp_core.domain.models import Attribute, Product
from mpp_core.mapping.interfaces import AttributeMappingStore, CategoryMappingStore


class CategoryMapper:
    def __init__(self, mapping_store: CategoryMappingStore) -> None:
        self._mapping_store = mapping_store

    def map(self, product: Product, source_category_id: str) -> Product:
        product.category = self._mapping_store.get_internal_category(source_category_id)
        return product


class AttributeMapper:
    def __init__(self, mapping_store: AttributeMappingStore) -> None:
        self._mapping_store = mapping_store

    def map(self, product: Product) -> Product:
        mapped_attributes: list[Attribute] = []
        for attribute in product.attributes:
            internal_name = self._mapping_store.get_internal_attribute_name(attribute.name)
            mapped_attributes.append(
                Attribute(
                    name=internal_name or attribute.name,
                    value=attribute.value,
                    source_name=attribute.source_name or attribute.name,
                )
            )
        product.attributes = mapped_attributes
        return product
