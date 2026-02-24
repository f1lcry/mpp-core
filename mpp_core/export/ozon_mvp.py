import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from mpp_core.export.ozon_api_client import OzonApiClient, OzonApiError


@dataclass
class CategoryTypeCandidate:
    description_category_id: int
    type_id: int
    category_name: str
    type_name: str


@dataclass
class OzonMvpRunResult:
    offer_id: str
    task_id: int
    import_status: str
    description_category_id: int
    type_id: int
    request_log_path: Path
    response_log_path: Path


class OzonRunLogger:
    def __init__(self, log_dir: Path) -> None:
        self._log_dir = log_dir
        self._started_at = self._now()
        self._requests: list[dict[str, Any]] = []
        self._responses: list[dict[str, Any]] = []
        self._request_log_path = self._log_dir / "request.json"
        self._response_log_path = self._log_dir / "response.json"

    @property
    def request_log_path(self) -> Path:
        return self._request_log_path

    @property
    def response_log_path(self) -> Path:
        return self._response_log_path

    def log_request(self, *, step: str, endpoint: str, payload: dict[str, Any]) -> None:
        self._requests.append(
            {
                "timestamp": self._now(),
                "step": step,
                "endpoint": endpoint,
                "payload": payload,
            }
        )

    def log_response(
        self,
        *,
        step: str,
        endpoint: str,
        status_code: Optional[int],
        response: Optional[dict[str, Any]],
        error: Optional[str] = None,
    ) -> None:
        self._responses.append(
            {
                "timestamp": self._now(),
                "step": step,
                "endpoint": endpoint,
                "status_code": status_code,
                "response": response,
                "error": error,
            }
        )

    def save(self, *, summary: Optional[dict[str, Any]] = None) -> None:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        request_payload = {
            "started_at": self._started_at,
            "requests": self._requests,
        }
        response_payload = {
            "started_at": self._started_at,
            "responses": self._responses,
            "summary": summary or {},
        }
        self._request_log_path.write_text(
            json.dumps(request_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._response_log_path.write_text(
            json.dumps(response_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


class OzonMvpPayloadBuilder:
    def __init__(
        self,
        *,
        image_url: str = "https://upload.wikimedia.org/wikipedia/commons/3/3a/Cat03.jpg",
        price_rub: int = 999,
        width_mm: int = 120,
        height_mm: int = 30,
        depth_mm: int = 120,
        weight_g: int = 450,
    ) -> None:
        self._image_url = image_url
        self._price_rub = price_rub
        self._width_mm = width_mm
        self._height_mm = height_mm
        self._depth_mm = depth_mm
        self._weight_g = weight_g

    def build(
        self,
        *,
        offer_id: str,
        category: CategoryTypeCandidate,
        required_attributes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        return {
            "offer_id": offer_id,
            "name": f"MPP Core Test {category.type_name}",
            "description": f"Тестовая карточка MPP Core. Создано: {now}",
            "price": str(self._price_rub),
            "currency_code": "RUB",
            "vat": "0",
            "images": [self._image_url],
            "description_category_id": category.description_category_id,
            "type_id": category.type_id,
            "attributes": required_attributes,
            "width": self._width_mm,
            "height": self._height_mm,
            "depth": self._depth_mm,
            "dimension_unit": "mm",
            "weight": self._weight_g,
            "weight_unit": "g",
        }


class OzonMvpRunner:
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
        logs_dir: Path,
        status_poll_interval_sec: int = 3,
        status_poll_attempts: int = 8,
        max_category_candidates: int = 50,
    ) -> None:
        self._client = client
        self._logger = OzonRunLogger(log_dir=logs_dir)
        self._payload_builder = OzonMvpPayloadBuilder()
        self._status_poll_interval_sec = status_poll_interval_sec
        self._status_poll_attempts = status_poll_attempts
        self._max_category_candidates = max_category_candidates

    def run(self) -> OzonMvpRunResult:
        summary: dict[str, Any] = {"status": "failed"}
        try:
            category_tree = self._post(
                step="category_tree",
                endpoint="/v1/description-category/tree",
                payload={"language": "DEFAULT"},
            )
            candidates = self._extract_candidates(category_tree.get("result", []))
            category, attributes_payload, required_attributes = self._select_category(candidates)

            offer_id = self._make_offer_id()
            item_payload = self._payload_builder.build(
                offer_id=offer_id,
                category=category,
                required_attributes=attributes_payload,
            )

            import_response = self._post(
                step="product_import",
                endpoint="/v3/product/import",
                payload={"items": [item_payload]},
            )
            task_id = int(import_response["result"]["task_id"])

            import_info = self._poll_import_status(task_id=task_id)
            first_item = self._first_import_item(import_info)
            item_status = first_item.get("status", "unknown")

            summary = {
                "status": "ok",
                "offer_id": offer_id,
                "task_id": task_id,
                "import_status": item_status,
                "description_category_id": category.description_category_id,
                "type_id": category.type_id,
                "category_name": category.category_name,
                "type_name": category.type_name,
                "required_attribute_ids": [attr["id"] for attr in required_attributes],
            }
            return OzonMvpRunResult(
                offer_id=offer_id,
                task_id=task_id,
                import_status=item_status,
                description_category_id=category.description_category_id,
                type_id=category.type_id,
                request_log_path=self._logger.request_log_path,
                response_log_path=self._logger.response_log_path,
            )
        except Exception as exc:  # pragma: no cover - integration runtime protection
            summary = {
                "status": "failed",
                "error": str(exc),
            }
            raise
        finally:
            self._logger.save(summary=summary)

    def _post(self, *, step: str, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._logger.log_request(step=step, endpoint=endpoint, payload=payload)
        try:
            response = self._client.post(endpoint=endpoint, payload=payload)
        except OzonApiError as exc:
            self._logger.log_response(
                step=step,
                endpoint=endpoint,
                status_code=exc.status_code,
                response=exc.response_data,
                error=str(exc),
            )
            raise
        self._logger.log_response(
            step=step,
            endpoint=endpoint,
            status_code=response.status_code,
            response=response.data,
        )
        return response.data

    def _select_category(
        self,
        candidates: list[CategoryTypeCandidate],
    ) -> tuple[CategoryTypeCandidate, list[dict[str, Any]], list[dict[str, Any]]]:
        if not candidates:
            raise RuntimeError("Ozon category tree is empty")

        checked = 0
        for candidate in candidates[: self._max_category_candidates]:
            checked += 1
            attributes_response = self._post(
                step="category_attributes",
                endpoint="/v1/description-category/attribute",
                payload={
                    "description_category_id": candidate.description_category_id,
                    "type_id": candidate.type_id,
                    "language": "DEFAULT",
                },
            )
            attributes = attributes_response.get("result", [])
            required_attributes = [attr for attr in attributes if attr.get("is_required")]
            if not required_attributes:
                continue
            if any(self._is_complex_attribute(attr) for attr in required_attributes):
                continue

            try:
                payload_attributes = self._resolve_required_attributes(
                    candidate=candidate,
                    required_attributes=required_attributes,
                )
            except RuntimeError:
                continue
            return candidate, payload_attributes, required_attributes

        raise RuntimeError(
            f"Cannot find a suitable category in first {checked} candidates "
            "with resolvable required attributes"
        )

    @staticmethod
    def _is_complex_attribute(attribute: dict[str, Any]) -> bool:
        if attribute.get("is_aspect"):
            return True
        if attribute.get("complex_is_required"):
            return True
        return False

    def _resolve_required_attributes(
        self,
        *,
        candidate: CategoryTypeCandidate,
        required_attributes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        for attribute in required_attributes:
            attribute_id = int(attribute["id"])
            dictionary_id = int(attribute.get("dictionary_id") or 0)
            if dictionary_id > 0:
                values_response = self._post(
                    step="attribute_dictionary_values",
                    endpoint="/v1/description-category/attribute/values",
                    payload={
                        "description_category_id": candidate.description_category_id,
                        "type_id": candidate.type_id,
                        "attribute_id": attribute_id,
                        "language": "DEFAULT",
                        "last_value_id": 0,
                        "limit": 50,
                    },
                )
                values = values_response.get("result", [])
                if not values:
                    raise RuntimeError(
                        f"No dictionary values for attribute {attribute_id}"
                    )
                first_value = values[0]
                value_payload: dict[str, Any] = {
                    "dictionary_value_id": int(first_value["id"]),
                }
                if first_value.get("value"):
                    value_payload["value"] = str(first_value["value"])
            else:
                value_payload = {
                    "value": self._attribute_scalar_value(attribute=attribute),
                }

            resolved.append(
                {
                    "id": attribute_id,
                    "complex_id": 0,
                    "values": [value_payload],
                }
            )

        return resolved

    @staticmethod
    def _attribute_scalar_value(attribute: dict[str, Any]) -> str:
        attribute_type = str(attribute.get("type") or "String")
        attribute_name = str(attribute.get("name") or "value")

        if attribute_type in {"Integer", "Decimal"}:
            return "1"
        if attribute_type == "Boolean":
            return "true"
        if attribute_type == "Date":
            return datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if attribute_type == "URL":
            return "https://example.com"
        return f"MPP {attribute_name}"

    def _poll_import_status(self, *, task_id: int) -> dict[str, Any]:
        last_response: dict[str, Any] = {}
        for _ in range(self._status_poll_attempts):
            info_response = self._post(
                step="import_status",
                endpoint="/v1/product/import/info",
                payload={"task_id": task_id},
            )
            last_response = info_response
            first_item = self._first_import_item(info_response)
            status = first_item.get("status")
            if status in self._FINAL_ITEM_STATUSES:
                return info_response
            time.sleep(self._status_poll_interval_sec)

        return last_response

    @staticmethod
    def _first_import_item(import_info: dict[str, Any]) -> dict[str, Any]:
        items = import_info.get("result", {}).get("items", [])
        if not items:
            return {}
        return items[0]

    @staticmethod
    def _extract_candidates(tree_nodes: list[dict[str, Any]]) -> list[CategoryTypeCandidate]:
        candidates: list[CategoryTypeCandidate] = []

        def walk(
            nodes: list[dict[str, Any]],
            *,
            description_category_id: Optional[int],
            category_name: str,
        ) -> None:
            for node in nodes:
                current_category_id = node.get("description_category_id", description_category_id)
                current_category_name = str(node.get("category_name") or category_name)
                children = node.get("children") or []
                disabled = bool(node.get("disabled"))
                type_id = node.get("type_id")
                type_name = node.get("type_name")

                if not disabled and current_category_id and type_id:
                    candidates.append(
                        CategoryTypeCandidate(
                            description_category_id=int(current_category_id),
                            type_id=int(type_id),
                            category_name=current_category_name,
                            type_name=str(type_name or ""),
                        )
                    )

                if children:
                    walk(
                        children,
                        description_category_id=current_category_id,
                        category_name=current_category_name,
                    )

        walk(tree_nodes, description_category_id=None, category_name="")
        return candidates

    @staticmethod
    def _make_offer_id() -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        suffix = uuid4().hex[:8]
        return f"mpp-core-{stamp}-{suffix}"
