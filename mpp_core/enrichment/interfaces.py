from abc import ABC, abstractmethod

from mpp_core.domain.models import Product


class BaseAIProvider(ABC):
    @abstractmethod
    def generate_description(self, product: Product) -> str:
        """Generate enhanced product description."""


class ImageProcessor(ABC):
    @abstractmethod
    def process(self, image_urls: list[str]) -> list[str]:
        """Apply image processing pipeline and return resulting image URLs."""
