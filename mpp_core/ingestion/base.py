from abc import ABC, abstractmethod
from typing import Iterable

from mpp_core.ingestion.dto import RawProductDTO


class BaseIngestionClient(ABC):
    @abstractmethod
    def fetch_products(self) -> Iterable[RawProductDTO]:
        """Fetch raw products from external source."""
