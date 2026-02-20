from mpp_core.domain.models import Product
from mpp_core.enrichment.interfaces import BaseAIProvider, ImageProcessor


class EnrichmentService:
    def __init__(self, ai_provider: BaseAIProvider, image_processor: ImageProcessor) -> None:
        self._ai_provider = ai_provider
        self._image_processor = image_processor

    def enrich(self, product: Product) -> Product:
        product.ai_description = self._ai_provider.generate_description(product)
        product.image_urls = self._image_processor.process(product.image_urls)
        return product
