from mpp_core.domain.models import Product
from mpp_core.enrichment.interfaces import BaseAIProvider, ImageProcessor


class StubAIProvider(BaseAIProvider):
    def generate_description(self, product: Product) -> str:
        return f"[stub-ai] Enriched description for {product.title}"


class NoOpImageProcessor(ImageProcessor):
    def process(self, image_urls: list[str]) -> list[str]:
        return image_urls
