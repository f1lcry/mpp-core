import json
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from mpp_core.config import Settings
from mpp_core.export.ozon_api_client import OzonApiClient, OzonApiError
from mpp_core.export.ozon_db_payload_builder import OzonDbPayloadBuilder
from mpp_core.storage.sqlite import ProductRecord, SqliteProductRepository


@dataclass
class OzonDbExportRunResult:
    selected: int
    exported: int
    failed: int
    request_log_path: Path
    response_log_path: Path


@dataclass
class _CategoryTypeCandidate:
    description_category_id: int
    type_id: int
    category_name: str
    type_name: str


@dataclass
class _FallbackCategory:
    description_category_id: int
    type_id: int
    attributes_payload: list[dict[str, Any]]
    category_name: str
    type_name: str


class OzonDbExportRunner:
    _FINAL_ITEM_STATUSES = {
        "imported",
        "skipped",
        "failed",
        "rejected",
        "validation_failed",
    }
    _IMPORT_ENDPOINT = "/v3/product/import"

    def __init__(
        self,
        *,
        settings: Settings,
        repository: SqliteProductRepository,
        client: OzonApiClient,
        payload_builder: OzonDbPayloadBuilder,
        logs_dir: Path,
        export_limit: int = 50,
        status_poll_interval_sec: int = 3,
        status_poll_attempts: int = 8,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._client = client
        self._payload_builder = payload_builder
        self._export_limit = max(1, export_limit)
        self._status_poll_interval_sec = status_poll_interval_sec
        self._status_poll_attempts = status_poll_attempts

        self._started_at = self._now()
        self._requests: list[dict[str, Any]] = []
        self._responses: list[dict[str, Any]] = []
        self._request_log_path = logs_dir / "db_export_request.json"
        self._response_log_path = logs_dir / "db_export_response.json"
        self._fallback_category: Optional[_FallbackCategory] = None
        self._force_fallback_category = False

    @property
    def request_log_path(self) -> Path:
        return self._request_log_path

    @property
    def response_log_path(self) -> Path:
        return self._response_log_path

    def run(self) -> OzonDbExportRunResult:
        products = self._repository.get_products_ready_for_export(limit=self._export_limit)
        if not products:
            print("no products to export")
            result = OzonDbExportRunResult(
                selected=0,
                exported=0,
                failed=0,
                request_log_path=self._request_log_path,
                response_log_path=self._response_log_path,
            )
            self._save_logs(summary={"status": "ok", "selected": 0, "exported": 0, "failed": 0})
            return result

        exported = 0
        failed = 0
        for product in products:
            success = self._export_one(product)
            if success:
                exported += 1
            else:
                failed += 1

        result = OzonDbExportRunResult(
            selected=len(products),
            exported=exported,
            failed=failed,
            request_log_path=self._request_log_path,
            response_log_path=self._response_log_path,
        )
        self._save_logs(
            summary={
                "status": "ok",
                "sqlite_db_path": self._settings.sqlite_db_path,
                "selected": result.selected,
                "exported": result.exported,
                "failed": result.failed,
            }
        )
        return result

    def _export_one(self, product: ProductRecord) -> bool:
        product_images_count = self._count_product_images(product)
        try:
            import_payload = self._payload_builder.build_payload([product])
        except Exception as exc:
            self._log_response(
                step="payload_build",
                endpoint="local",
                status_code=None,
                response={"item_id_1688": product.item_id_1688},
                item_id_1688=product.item_id_1688,
                error=str(exc),
                images_count=product_images_count,
            )
            return False

        items = import_payload.get("items", [])
        if not items:
            self._log_response(
                step="payload_build",
                endpoint="local",
                status_code=None,
                response={"item_id_1688": product.item_id_1688},
                item_id_1688=product.item_id_1688,
                error="empty payload items",
                images_count=product_images_count,
            )
            return False
        base_item_payload = items[0]
        attempt_fallback_modes = [True] if self._force_fallback_category else [False, True]

        for attempt_index, use_fallback in enumerate(attempt_fallback_modes, start=1):
            try:
                effective_item_payload = self._prepare_item_for_attempt(
                    base_item_payload=base_item_payload,
                    product=product,
                    use_fallback_category=use_fallback,
                )
            except Exception as exc:
                self._log_response(
                    step="payload_build",
                    endpoint="local",
                    status_code=None,
                    response={"item_id_1688": product.item_id_1688},
                    item_id_1688=product.item_id_1688,
                    error=str(exc),
                    images_count=product_images_count,
                )
                return False

            offer_id = str(effective_item_payload["offer_id"])
            import_payload = {"items": [self._to_import_item(effective_item_payload)]}
            images_count = self._count_item_images(effective_item_payload)
            self._log_request(
                step="product_import",
                endpoint=self._IMPORT_ENDPOINT,
                payload=import_payload,
                item_id_1688=product.item_id_1688,
                offer_id=offer_id,
                meta={"attempt": attempt_index, "fallback_category": use_fallback},
                images_count=images_count,
            )

            try:
                import_response = self._client.post(
                    endpoint=self._IMPORT_ENDPOINT,
                    payload=import_payload,
                )
            except OzonApiError as exc:
                self._log_response(
                    step="product_import",
                    endpoint=self._IMPORT_ENDPOINT,
                    status_code=exc.status_code,
                    response=exc.response_data,
                    item_id_1688=product.item_id_1688,
                    offer_id=offer_id,
                    error=str(exc),
                    images_count=images_count,
                )
                return False

            self._log_response(
                step="product_import",
                endpoint=self._IMPORT_ENDPOINT,
                status_code=import_response.status_code,
                response=import_response.data,
                item_id_1688=product.item_id_1688,
                offer_id=offer_id,
                images_count=images_count,
            )

            task_id = self._extract_task_id(import_response.data)
            if task_id is None:
                self._log_response(
                    step="product_import",
                    endpoint=self._IMPORT_ENDPOINT,
                    status_code=import_response.status_code,
                    response=import_response.data,
                    item_id_1688=product.item_id_1688,
                    offer_id=offer_id,
                    error=f"task_id not found in {self._IMPORT_ENDPOINT} response",
                    images_count=images_count,
                )
                return False

            info_response_data = self._poll_import_status(
                task_id=task_id,
                item_id_1688=product.item_id_1688,
                offer_id=offer_id,
                images_count=images_count,
            )
            item_status = self._extract_item_status(info_response_data, offer_id=offer_id)
            item_errors = self._extract_item_errors(info_response_data, offer_id=offer_id)
            if item_status in {"imported", "skipped"} and not item_errors:
                if use_fallback:
                    self._force_fallback_category = True
                return self._mark_product_exported(
                    product=product,
                    offer_id=offer_id,
                    images_count=images_count,
                )

            error_codes = [str(error.get("code")) for error in item_errors]
            self._log_response(
                step="product_finalize",
                endpoint="/v1/product/import/info",
                status_code=200 if info_response_data is not None else None,
                response=info_response_data,
                item_id_1688=product.item_id_1688,
                offer_id=offer_id,
                error=f"import status={item_status}, errors={','.join(error_codes)}",
                images_count=images_count,
            )

            if not use_fallback and self._has_category_errors(item_errors):
                self._force_fallback_category = True
                continue
            return False

        return False

    def _mark_product_exported(
        self,
        *,
        product: ProductRecord,
        offer_id: str,
        images_count: Optional[int] = None,
    ) -> bool:
        updated = self._repository.update_product_status_exported(
            product.item_id_1688,
            offer_id,
        )
        if not updated:
            self._log_response(
                step="sqlite_update",
                endpoint="sqlite",
                status_code=None,
                response={"item_id_1688": product.item_id_1688, "status": "ready_for_export"},
                item_id_1688=product.item_id_1688,
                offer_id=offer_id,
                error="failed to update status to exported",
                images_count=images_count,
            )
            return False

        self._log_response(
            step="sqlite_update",
            endpoint="sqlite",
            status_code=None,
            response={
                "item_id_1688": product.item_id_1688,
                "status": "exported",
                "ozon_offer_id": offer_id,
            },
            item_id_1688=product.item_id_1688,
            offer_id=offer_id,
            images_count=images_count,
        )
        return True

    def _prepare_item_for_attempt(
        self,
        *,
        base_item_payload: dict[str, Any],
        product: ProductRecord,
        use_fallback_category: bool,
    ) -> dict[str, Any]:
        if not use_fallback_category:
            return dict(base_item_payload)

        fallback = self._resolve_fallback_category()
        item_payload = dict(base_item_payload)
        item_payload["category_id"] = fallback.description_category_id
        item_payload["type_id"] = fallback.type_id
        item_payload["attributes"] = deepcopy(fallback.attributes_payload)

        product_name = str(item_payload.get("name") or "")
        for attribute in item_payload["attributes"]:
            if not isinstance(attribute, dict):
                continue
            if int(attribute.get("id") or 0) != 9048:
                continue
            values = attribute.get("values")
            if not isinstance(values, list) or not values:
                continue
            if isinstance(values[0], dict):
                values[0]["value"] = product_name

        self._log_response(
            step="category_fallback",
            endpoint="local",
            status_code=None,
            response={
                "item_id_1688": product.item_id_1688,
                "description_category_id": fallback.description_category_id,
                "type_id": fallback.type_id,
                "category_name": fallback.category_name,
                "type_name": fallback.type_name,
            },
            item_id_1688=product.item_id_1688,
            offer_id=str(item_payload.get("offer_id") or ""),
            images_count=self._count_item_images(item_payload),
        )
        return item_payload

    def _resolve_fallback_category(self) -> _FallbackCategory:
        if self._fallback_category is not None:
            return self._fallback_category

        try:
            tree_response = self._client.post(
                endpoint="/v1/description-category/tree",
                payload={"language": "DEFAULT"},
            )
        except OzonApiError as exc:
            raise RuntimeError(f"Failed to load Ozon category tree: {exc}") from exc

        candidates = self._extract_candidates(tree_response.data.get("result", []))
        checked = 0
        for candidate in candidates[:50]:
            checked += 1
            try:
                attributes_response = self._client.post(
                    endpoint="/v1/description-category/attribute",
                    payload={
                        "description_category_id": candidate.description_category_id,
                        "type_id": candidate.type_id,
                        "language": "DEFAULT",
                    },
                )
            except OzonApiError:
                continue

            attributes = attributes_response.data.get("result", [])
            required_attributes = [attr for attr in attributes if attr.get("is_required")]
            if any(self._is_complex_attribute(attr) for attr in required_attributes):
                continue
            try:
                attributes_payload = self._resolve_required_attributes(
                    candidate=candidate,
                    required_attributes=required_attributes,
                )
            except RuntimeError:
                continue

            self._fallback_category = _FallbackCategory(
                description_category_id=candidate.description_category_id,
                type_id=candidate.type_id,
                attributes_payload=attributes_payload,
                category_name=candidate.category_name,
                type_name=candidate.type_name,
            )
            return self._fallback_category

        raise RuntimeError(
            f"Cannot resolve fallback Ozon category/type for export (checked={checked})"
        )

    @staticmethod
    def _extract_candidates(tree_nodes: list[dict[str, Any]]) -> list[_CategoryTypeCandidate]:
        candidates: list[_CategoryTypeCandidate] = []

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
                        _CategoryTypeCandidate(
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
    def _is_complex_attribute(attribute: dict[str, Any]) -> bool:
        return bool(attribute.get("is_aspect") or attribute.get("complex_is_required"))

    def _resolve_required_attributes(
        self,
        *,
        candidate: _CategoryTypeCandidate,
        required_attributes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        for attribute in required_attributes:
            attribute_id = int(attribute.get("id") or 0)
            if attribute_id <= 0:
                continue

            dictionary_id = int(attribute.get("dictionary_id") or 0)
            if dictionary_id > 0:
                try:
                    values_response = self._client.post(
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
                except OzonApiError as exc:
                    raise RuntimeError(
                        f"Cannot load dictionary values for attribute={attribute_id}: {exc}"
                    ) from exc
                values = values_response.data.get("result", [])
                if not values:
                    raise RuntimeError(f"No dictionary values for attribute={attribute_id}")
                first_value = values[0]
                value_payload: dict[str, Any] = {
                    "dictionary_value_id": int(first_value["id"]),
                }
                if first_value.get("value"):
                    value_payload["value"] = str(first_value["value"])
            else:
                value_payload = {"value": self._attribute_scalar_value(attribute)}

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

    @staticmethod
    def _has_category_errors(errors: list[dict[str, Any]]) -> bool:
        category_error_codes = {
            "category_not_found",
            "description_category_not_found",
        }
        for error in errors:
            code = str(error.get("code") or "").strip()
            if code in category_error_codes:
                return True
        return False

    def _poll_import_status(
        self,
        *,
        task_id: int,
        item_id_1688: str,
        offer_id: str,
        images_count: Optional[int] = None,
    ) -> Optional[dict[str, Any]]:
        last_response: Optional[dict[str, Any]] = None
        for attempt in range(1, self._status_poll_attempts + 1):
            payload = {"task_id": task_id}
            self._log_request(
                step="import_status_poll",
                endpoint="/v1/product/import/info",
                payload=payload,
                item_id_1688=item_id_1688,
                offer_id=offer_id,
                meta={"attempt": attempt},
                images_count=images_count,
            )
            try:
                info_response = self._client.post(
                    endpoint="/v1/product/import/info",
                    payload=payload,
                )
            except OzonApiError as exc:
                self._log_response(
                    step="import_status_poll",
                    endpoint="/v1/product/import/info",
                    status_code=exc.status_code,
                    response=exc.response_data,
                    item_id_1688=item_id_1688,
                    offer_id=offer_id,
                    error=str(exc),
                    images_count=images_count,
                )
                return last_response

            last_response = info_response.data
            self._log_response(
                step="import_status_poll",
                endpoint="/v1/product/import/info",
                status_code=info_response.status_code,
                response=info_response.data,
                item_id_1688=item_id_1688,
                offer_id=offer_id,
                images_count=images_count,
            )

            status = self._extract_item_status(last_response, offer_id=offer_id)
            if status in self._FINAL_ITEM_STATUSES:
                return last_response

            time.sleep(self._status_poll_interval_sec)

        return last_response

    @staticmethod
    def _extract_task_id(response_data: dict[str, Any]) -> Optional[int]:
        task_id = response_data.get("result", {}).get("task_id")
        if task_id is None:
            return None
        try:
            return int(task_id)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_item_status(
        info_response_data: Optional[dict[str, Any]],
        *,
        offer_id: str,
    ) -> str:
        item = OzonDbExportRunner._find_import_item(info_response_data, offer_id=offer_id)
        if not item:
            return "unknown"
        return str(item.get("status", "unknown"))

    @staticmethod
    def _extract_item_errors(
        info_response_data: Optional[dict[str, Any]],
        *,
        offer_id: str,
    ) -> list[dict[str, Any]]:
        item = OzonDbExportRunner._find_import_item(info_response_data, offer_id=offer_id)
        if not item:
            return []
        errors = item.get("errors")
        if not isinstance(errors, list):
            return []
        return [error for error in errors if isinstance(error, dict)]

    @staticmethod
    def _find_import_item(
        info_response_data: Optional[dict[str, Any]],
        *,
        offer_id: str,
    ) -> dict[str, Any]:
        if not info_response_data:
            return {}
        items = info_response_data.get("result", {}).get("items", [])
        if not isinstance(items, list):
            return {}

        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("offer_id") or "") == offer_id:
                return item

        for item in items:
            if isinstance(item, dict):
                return item
        return {}

    @staticmethod
    def _to_import_item(item_payload: dict[str, Any]) -> dict[str, Any]:
        attributes_payload: list[dict[str, Any]] = []
        for attribute in item_payload.get("attributes", []):
            if not isinstance(attribute, dict):
                continue
            attribute_id = attribute.get("id")
            if attribute_id is None:
                continue
            try:
                normalized_id = int(attribute_id)
            except (TypeError, ValueError):
                continue

            values = attribute.get("values")
            if isinstance(values, list):
                normalized_values = [value for value in values if isinstance(value, dict)]
            else:
                raw_value = attribute.get("value")
                if raw_value is None:
                    continue
                normalized_values = [{"value": str(raw_value)}]

            if not normalized_values:
                continue

            try:
                complex_id = int(attribute.get("complex_id", 0))
            except (TypeError, ValueError):
                complex_id = 0
            attributes_payload.append(
                {
                    "id": normalized_id,
                    "complex_id": complex_id,
                    "values": normalized_values,
                }
            )

        return {
            "offer_id": str(item_payload.get("offer_id") or ""),
            "name": str(item_payload.get("name") or ""),
            "description": str(item_payload.get("description") or ""),
            "price": str(item_payload.get("price") or ""),
            "currency_code": "RUB",
            "vat": "0",
            "description_category_id": int(item_payload.get("category_id") or 0),
            "type_id": int(item_payload.get("type_id") or 0),
            "images": list(item_payload.get("images") or []),
            "attributes": attributes_payload,
            "width": int(item_payload.get("width") or 120),
            "height": int(item_payload.get("height") or 30),
            "depth": int(item_payload.get("depth") or 120),
            "dimension_unit": "mm",
            "weight": int(item_payload.get("weight") or 450),
            "weight_unit": "g",
        }

    def _log_request(
        self,
        *,
        step: str,
        endpoint: str,
        payload: dict[str, Any],
        item_id_1688: Optional[str] = None,
        offer_id: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
        images_count: Optional[int] = None,
    ) -> None:
        record: dict[str, Any] = {
            "timestamp": self._now(),
            "step": step,
            "endpoint": endpoint,
            "payload": payload,
        }
        if item_id_1688:
            record["item_id_1688"] = item_id_1688
        if offer_id:
            record["offer_id"] = offer_id
        if meta:
            record["meta"] = meta
        if images_count is not None:
            record["images_count"] = images_count
        self._requests.append(record)

    def _log_response(
        self,
        *,
        step: str,
        endpoint: str,
        status_code: Optional[int],
        response: Optional[Any],
        item_id_1688: Optional[str] = None,
        offer_id: Optional[str] = None,
        error: Optional[str] = None,
        images_count: Optional[int] = None,
    ) -> None:
        record: dict[str, Any] = {
            "timestamp": self._now(),
            "step": step,
            "endpoint": endpoint,
            "status_code": status_code,
            "response": response,
        }
        if item_id_1688:
            record["item_id_1688"] = item_id_1688
        if offer_id:
            record["offer_id"] = offer_id
        if error:
            record["error"] = error
        if images_count is not None:
            record["images_count"] = images_count
        self._responses.append(record)

    def _save_logs(self, *, summary: dict[str, Any]) -> None:
        self._request_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._request_log_path.write_text(
            json.dumps(
                {
                    "started_at": self._started_at,
                    "requests": self._requests,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self._response_log_path.write_text(
            json.dumps(
                {
                    "started_at": self._started_at,
                    "responses": self._responses,
                    "summary": summary,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _count_item_images(item_payload: dict[str, Any]) -> int:
        images = item_payload.get("images")
        if not isinstance(images, list):
            return 0
        return len([image for image in images if str(image).strip()])

    @staticmethod
    def _count_product_images(product: ProductRecord) -> int:
        images = getattr(product, "images", [])
        if not isinstance(images, list):
            return 0
        return len([image for image in images if str(image).strip()])
