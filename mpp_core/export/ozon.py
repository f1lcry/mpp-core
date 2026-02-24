from typing import Optional

from mpp_core.export.base import BaseMarketplaceExporter
from mpp_core.export.models import ExportResult


class OzonExporter(BaseMarketplaceExporter):
    """Stub exporter without real HTTP calls."""

    def __init__(self, client_id: Optional[str] = None, api_key: Optional[str] = None) -> None:
        self._client_id = client_id
        self._api_key = api_key

    def _build_auth_headers(self) -> dict[str, str]:
        if not self._client_id or not self._api_key:
            return {}
        return {
            "Client-Id": self._client_id,
            "Api-Key": self._api_key,
        }

    def export(self, payload: dict) -> ExportResult:
        source_id = payload.get("source_product_id", "unknown")
        auth_state = "configured" if self._build_auth_headers() else "missing"
        return ExportResult(
            success=True,
            message=f"Stub export completed (ozon auth: {auth_state})",
            external_id=f"ozon-{source_id}",
        )
