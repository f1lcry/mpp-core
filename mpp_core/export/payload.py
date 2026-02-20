from abc import ABC, abstractmethod

from mpp_core.domain.models import Product


class PayloadBuilder(ABC):
    @abstractmethod
    def build(self, product: Product) -> dict:
        """Build marketplace payload from internal Product model."""


class OzonPayloadBuilder(PayloadBuilder):
    """Stub payload builder for Ozon payload shape."""

    def build(self, product: Product) -> dict:
        return {
            "source_product_id": product.source_product_id,
            "title": product.title,
            "description": product.ai_description or product.description,
            "category": product.category.name if product.category else None,
            "attributes": [{"name": attr.name, "value": attr.value} for attr in product.attributes],
            "images": product.image_urls,
            "skus": [
                {
                    "sku_id": sku.sku_id,
                    "price": sku.price,
                    "currency": sku.currency,
                    "stock": sku.stock,
                }
                for sku in product.skus
            ],
        }
