from abc import ABC, abstractmethod

from mpp_core.export.models import ExportResult


class BaseMarketplaceExporter(ABC):
    @abstractmethod
    def export(self, payload: dict) -> ExportResult:
        """Send payload to target marketplace."""
