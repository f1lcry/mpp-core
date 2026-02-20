from mpp_core.export.base import BaseMarketplaceExporter
from mpp_core.export.models import ExportResult


class OzonExporter(BaseMarketplaceExporter):
    """Stub exporter without real HTTP calls."""

    def export(self, payload: dict) -> ExportResult:
        source_id = payload.get("source_product_id", "unknown")
        return ExportResult(
            success=True,
            message="Stub export completed",
            external_id=f"ozon-{source_id}",
        )
