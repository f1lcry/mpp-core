import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from mpp_core.domain import InternalProduct
from mpp_core.export.ozon_api_client import OzonApiClient, OzonApiError
from mpp_core.export.json_payload_builder import JsonPayloadBuilder
from mpp_core.mapping import JsonMappingLoader


@dataclass
class OzonJsonImportRunResult:
    items_count: int
    task_id: Optional[int]
    import_status: str
    request_log_path: Path
    response_log_path: Path


class OzonJsonImportRunner:
    _FINAL_ITEM_STATUSES = {
        "imported",
        "failed",
        "rejected",
        "validation_failed",
    }

    def __init__(
        self,
        *,
        client: OzonApiClient,
        products_path: Path,
        mapping_path: Path,
        logs_dir: Path,
        status_poll_interval_sec: int = 3,
        status_poll_attempts: int = 8,
    ) -> None:
        self._client = client
        self._products_path = products_path
        self._mapping_loader = JsonMappingLoader(mapping_path)
        self._payload_builder = JsonPayloadBuilder()
        self._request_log_path = logs_dir / "json_request.json"
        self._response_log_path = logs_dir / "json_response.json"
        self._status_poll_interval_sec = status_poll_interval_sec
        self._status_poll_attempts = status_poll_attempts

    @property
    def request_log_path(self) -> Path:
        return self._request_log_path

    @property
    def response_log_path(self) -> Path:
        return self._response_log_path

    def run(self) -> OzonJsonImportRunResult:
        products = self._load_products()
        items = self._build_items(products)
        import_payload = {
            "items": [self._to_import_item(item_payload) for item_payload in items]
        }

        self._write_json(
            self._request_log_path,
            {
                "timestamp": self._now(),
                "endpoint": "/v3/product/import",
                "payload": import_payload,
            },
        )

        task_id: Optional[int] = None
        import_status = "unknown"
        response_payload: dict[str, Any] = {
            "timestamp": self._now(),
            "import": {
                "endpoint": "/v3/product/import",
            },
            "info": {
                "endpoint": "/v1/product/import/info",
                "response": None,
            },
            "summary": {
                "items_count": len(items),
                "task_id": None,
                "import_status": import_status,
            },
        }

        try:
            import_response = self._client.post(
                endpoint="/v3/product/import",
                payload=import_payload,
            )
            response_payload["import"]["status_code"] = import_response.status_code
            response_payload["import"]["response"] = import_response.data
            task_id = self._extract_task_id(import_response.data)
            response_payload["summary"]["task_id"] = task_id

            info_response_data: Optional[dict[str, Any]] = None
            if task_id is not None:
                info_response_data = self._poll_import_status(task_id)
                import_status = self._extract_item_status(info_response_data)
                response_payload["info"]["status_code"] = 200

            response_payload["info"]["response"] = info_response_data
            response_payload["summary"]["import_status"] = import_status
            response_payload["summary"]["items"] = self._summarize_items(info_response_data)

            self._ensure_import_success(info_response_data)

            return OzonJsonImportRunResult(
                items_count=len(items),
                task_id=task_id,
                import_status=import_status,
                request_log_path=self._request_log_path,
                response_log_path=self._response_log_path,
            )
        except OzonApiError as exc:
            if response_payload["import"].get("response") is None:
                response_payload["import"]["status_code"] = exc.status_code
                response_payload["import"]["response"] = exc.response_data
                response_payload["import"]["error"] = str(exc)
            else:
                response_payload["info"]["status_code"] = exc.status_code
                response_payload["info"]["response"] = exc.response_data
                response_payload["info"]["error"] = str(exc)
            response_payload["summary"]["task_id"] = task_id
            response_payload["summary"]["import_status"] = "failed"
            raise
        finally:
            self._write_json(
                self._response_log_path,
                response_payload,
            )

    def _build_items(self, products: list[InternalProduct]) -> list[dict[str, Any]]:
        items = []
        for product in products:
            mapping = self._mapping_loader.get_by_category(product.category)
            items.append(self._payload_builder.build(product, mapping))
        return items

    def _load_products(self) -> list[InternalProduct]:
        if not self._products_path.is_file():
            raise FileNotFoundError(f"Products file not found: {self._products_path}")

        raw_text = self._products_path.read_text(encoding="utf-8")
        try:
            raw_products = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {self._products_path}") from exc

        if not isinstance(raw_products, list):
            raise ValueError("Products JSON root must be an array")

        products = [InternalProduct.from_dict(raw) for raw in raw_products]
        if not products:
            raise ValueError("Products JSON must contain at least one product")
        return products

    @staticmethod
    def _to_import_item(item_payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "offer_id": item_payload["offer_id"],
            "name": item_payload["name"],
            "description": item_payload["description"],
            "price": item_payload["price"],
            "currency_code": item_payload["currency_code"],
            "description_category_id": item_payload["category_id"],
            "type_id": item_payload["type_id"],
            "images": item_payload["images"],
            "attributes": [
                {
                    "id": attribute["id"],
                    "complex_id": 0,
                    "values": [{"value": attribute["value"]}],
                }
                for attribute in item_payload["attributes"]
            ],
            "width": item_payload["width"],
            "height": item_payload["height"],
            "depth": item_payload["depth"],
            "dimension_unit": item_payload["dimension_unit"],
            "weight": item_payload["weight"],
            "weight_unit": item_payload["weight_unit"],
        }

    @staticmethod
    def _extract_task_id(response_data: dict[str, Any]) -> Optional[int]:
        task_id = response_data.get("result", {}).get("task_id")
        if task_id is None:
            return None
        return int(task_id)

    @staticmethod
    def _extract_item_status(info_response_data: dict[str, Any]) -> str:
        items = info_response_data.get("result", {}).get("items", [])
        if not items:
            return "unknown"
        return str(items[0].get("status", "unknown"))

    def _poll_import_status(self, task_id: int) -> dict[str, Any]:
        last_response: dict[str, Any] = {}
        for _ in range(self._status_poll_attempts):
            info_response = self._client.post(
                endpoint="/v1/product/import/info",
                payload={"task_id": task_id},
            )
            last_response = info_response.data
            if self._all_items_final(last_response):
                return last_response
            time.sleep(self._status_poll_interval_sec)
        return last_response

    def _all_items_final(self, info_response_data: dict[str, Any]) -> bool:
        items = info_response_data.get("result", {}).get("items", [])
        if not items:
            return False
        for item in items:
            status = str(item.get("status", "unknown"))
            if status not in self._FINAL_ITEM_STATUSES:
                return False
        return True

    @staticmethod
    def _summarize_items(info_response_data: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
        if not info_response_data:
            return []
        summarized: list[dict[str, Any]] = []
        items = info_response_data.get("result", {}).get("items", [])
        for item in items:
            summarized.append(
                {
                    "offer_id": item.get("offer_id"),
                    "status": item.get("status"),
                    "errors": [error.get("code") for error in item.get("errors", [])],
                }
            )
        return summarized

    @staticmethod
    def _ensure_import_success(info_response_data: Optional[dict[str, Any]]) -> None:
        if not info_response_data:
            return
        items = info_response_data.get("result", {}).get("items", [])
        failed: list[str] = []
        with_errors: list[str] = []
        for item in items:
            offer_id = str(item.get("offer_id") or "")
            status = str(item.get("status") or "")
            errors = item.get("errors") or []
            if status != "imported":
                failed.append(f"{offer_id}:{status}")
            if errors:
                codes = ",".join(str(error.get("code")) for error in errors)
                with_errors.append(f"{offer_id}:{codes}")
        if failed or with_errors:
            parts: list[str] = []
            if failed:
                parts.append(f"non-imported items={'; '.join(failed)}")
            if with_errors:
                parts.append(f"items with errors={'; '.join(with_errors)}")
            raise RuntimeError("Ozon import finished with issues: " + " | ".join(parts))

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
