from mpp_core.ingestion.base import BaseIngestionClient
from mpp_core.ingestion.dto import RawProductDTO, RawSKU


class Alibaba1688Client(BaseIngestionClient):
    """Stub ingestion client for future 1688 integration."""

    def __init__(self, batch_size: int = 10) -> None:
        self._batch_size = batch_size

    def fetch_products(self) -> list[RawProductDTO]:
        # Stub data to demonstrate pipeline wiring without real API calls.
        return [
            RawProductDTO(
                source_product_id="1688-1001",
                title="Portable Blender",
                description="Stub description from 1688 feed",
                source_category_id="1688-cat-home-appliances",
                raw_attributes={"Color": "White", "Voltage": "220V"},
                image_urls=[
                    "https://example.com/images/blender-1.jpg",
                    "https://example.com/images/blender-2.jpg",
                ],
                skus=[RawSKU(sku_id="1688-1001-A", price=24.99, currency="USD", stock=100)],
            )
        ][: self._batch_size]
