from abc import ABC, abstractmethod
from typing import Optional

from mpp_core.domain.models import Category


class CategoryMappingStore(ABC):
    @abstractmethod
    def get_internal_category(self, source_category_id: str) -> Optional[Category]:
        """Resolve source marketplace category to internal category."""


class AttributeMappingStore(ABC):
    @abstractmethod
    def get_internal_attribute_name(self, source_attribute_name: str) -> Optional[str]:
        """Resolve source attribute key to internal attribute key."""
