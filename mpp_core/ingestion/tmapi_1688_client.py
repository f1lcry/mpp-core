import json
import ssl
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib import error, parse, request


class TmapiApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        endpoint: str,
        status_code: Optional[int] = None,
        response_data: Optional[dict[str, Any]] = None,
        raw_body: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.endpoint = endpoint
        self.status_code = status_code
        self.response_data = response_data or {}
        self.raw_body = raw_body or ""


class Tmapi1688Client:
    def __init__(
        self,
        *,
        api_token: str,
        base_url: str = "https://api.tmapi.top",
        verify_ssl: bool = True,
        timeout_sec: int = 30,
        retry_attempts: int = 3,
        retry_backoff_sec: float = 1.0,
    ) -> None:
        clean_token = api_token.strip()
        if not clean_token:
            raise ValueError("TMAPI token is required")

        self._api_token = clean_token
        self._base_url = base_url.rstrip("/")
        self._verify_ssl = verify_ssl
        self._timeout_sec = timeout_sec
        self._retry_attempts = max(1, retry_attempts)
        self._retry_backoff_sec = max(0.0, retry_backoff_sec)
        self._api_logs: list[dict[str, Any]] = []

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def api_logs(self) -> list[dict[str, Any]]:
        return list(self._api_logs)

    def clear_api_logs(self) -> None:
        self._api_logs.clear()

    def get_shop_products(
        self,
        *,
        shop_url: Optional[str] = None,
        member_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
        sort: str = "sales",
    ) -> list[dict[str, Any]]:
        clean_shop_url = (shop_url or "").strip()
        clean_member_id = (member_id or "").strip()
        if not clean_shop_url and not clean_member_id:
            raise ValueError("shop_url or member_id must be provided")

        params: dict[str, Any] = {
            "page": page,
            "page_size": page_size,
            "sort": sort,
        }
        if clean_shop_url:
            endpoint = "/1688/shop/items/v2"
            params["shop_url"] = clean_shop_url
        else:
            endpoint = "/1688/shop/items"
            params["member_id"] = clean_member_id

        response_data = self._get(
            endpoint=endpoint,
            params=params,
            operation="get_shop_products",
        )
        payload = self._extract_data_payload(response_data=response_data, endpoint=endpoint)
        raw_items = payload.get("items", [])
        if not isinstance(raw_items, list):
            raise TmapiApiError(
                "Invalid TMAPI response format: data.items must be an array",
                endpoint=endpoint,
                response_data=response_data,
            )
        return [item for item in raw_items if isinstance(item, dict)]

    def get_item_detail(self, *, item_id: str) -> dict[str, Any]:
        clean_item_id = str(item_id).strip()
        if not clean_item_id:
            raise ValueError("item_id must be provided")

        endpoint = "/1688/v2/item_detail"
        response_data = self._get(
            endpoint=endpoint,
            params={"item_id": clean_item_id, "language": "en"},
            operation="get_item_detail",
        )
        return self._extract_data_payload(response_data=response_data, endpoint=endpoint)

    def get_category_products_v2(
        self,
        *,
        cat_id: int,
        page: int = 1,
        page_size: int = 20,
        sort: str = "sales",
        language: str = "en",
    ) -> list[dict[str, Any]]:
        endpoint = "/1688/category/items/v2"
        response_data = self._get(
            endpoint=endpoint,
            params={
                "cat_id": int(cat_id),
                "page": page,
                "page_size": page_size,
                "sort": sort,
                "language": language,
            },
            operation="get_category_products_v2",
        )
        payload = self._extract_data_payload(response_data=response_data, endpoint=endpoint)
        raw_items = payload.get("items", [])
        if not isinstance(raw_items, list):
            raise TmapiApiError(
                "Invalid TMAPI response format: data.items must be an array",
                endpoint=endpoint,
                response_data=response_data,
            )
        return [item for item in raw_items if isinstance(item, dict)]

    def _get(
        self,
        *,
        endpoint: str,
        params: dict[str, Any],
        operation: str,
    ) -> dict[str, Any]:
        normalized_endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        params_with_token = dict(params)
        params_with_token["apiToken"] = self._api_token
        query = parse.urlencode(params_with_token)
        url = f"{self._base_url}{normalized_endpoint}?{query}"
        safe_params = self._sanitize_params(params_with_token)

        for attempt in range(1, self._retry_attempts + 1):
            req = request.Request(url=url, method="GET")
            try:
                with request.urlopen(
                    req,
                    timeout=self._timeout_sec,
                    context=self._build_ssl_context(),
                ) as response:
                    raw_body = response.read().decode("utf-8")
                    response_data = self._parse_json(raw_body, endpoint=normalized_endpoint)
                    try:
                        self._ensure_api_success(
                            endpoint=normalized_endpoint,
                            response_data=response_data,
                            status_code=response.status,
                            raw_body=raw_body,
                        )
                    except TmapiApiError as exc:
                        self._record_api_log(
                            operation=operation,
                            endpoint=normalized_endpoint,
                            params=safe_params,
                            attempt=attempt,
                            status_code=response.status,
                            response_data=response_data,
                            raw_body=raw_body,
                            error_message=str(exc),
                        )
                        raise
                    self._record_api_log(
                        operation=operation,
                        endpoint=normalized_endpoint,
                        params=safe_params,
                        attempt=attempt,
                        status_code=response.status,
                        response_data=response_data,
                        raw_body=raw_body,
                    )
                    return response_data
            except error.HTTPError as exc:
                raw_body = exc.read().decode("utf-8")
                response_data = self._try_parse_json(raw_body) or {}
                self._record_api_log(
                    operation=operation,
                    endpoint=normalized_endpoint,
                    params=safe_params,
                    attempt=attempt,
                    status_code=exc.code,
                    response_data=response_data,
                    raw_body=raw_body,
                    error_message=f"HTTP {exc.code}",
                )
                if self._should_retry_http_error(status_code=exc.code, attempt=attempt):
                    self._sleep_before_retry(attempt)
                    continue
                raise TmapiApiError(
                    f"TMAPI HTTP error at {normalized_endpoint}: {exc.code}",
                    endpoint=normalized_endpoint,
                    status_code=exc.code,
                    response_data=response_data,
                    raw_body=raw_body,
                ) from exc
            except error.URLError as exc:
                reason = str(exc.reason)
                if isinstance(exc.reason, ssl.SSLCertVerificationError):
                    self._record_api_log(
                        operation=operation,
                        endpoint=normalized_endpoint,
                        params=safe_params,
                        attempt=attempt,
                        status_code=None,
                        response_data=None,
                        raw_body="",
                        error_message=reason,
                    )
                    raise TmapiApiError(
                        (
                            "SSL certificate verification failed. "
                            "Set MPP_TMAPI_VERIFY_SSL=false for local trusted-proxy environments."
                        ),
                        endpoint=normalized_endpoint,
                    ) from exc
                self._record_api_log(
                    operation=operation,
                    endpoint=normalized_endpoint,
                    params=safe_params,
                    attempt=attempt,
                    status_code=None,
                    response_data=None,
                    raw_body="",
                    error_message=reason,
                )
                if attempt < self._retry_attempts:
                    self._sleep_before_retry(attempt)
                    continue
                raise TmapiApiError(
                    f"TMAPI request failed at {normalized_endpoint}: {reason}",
                    endpoint=normalized_endpoint,
                ) from exc

        raise TmapiApiError(
            f"TMAPI request failed at {normalized_endpoint}: retry limit exceeded",
            endpoint=normalized_endpoint,
        )

    def _ensure_api_success(
        self,
        *,
        endpoint: str,
        response_data: dict[str, Any],
        status_code: int,
        raw_body: str,
    ) -> None:
        api_code = response_data.get("code")
        if api_code is None:
            return

        try:
            normalized_code = int(api_code)
        except (TypeError, ValueError):
            return

        if normalized_code == 200:
            return

        message = str(response_data.get("message") or response_data.get("msg") or "Unknown API error")
        raise TmapiApiError(
            f"TMAPI API error at {endpoint}: {normalized_code} ({message})",
            endpoint=endpoint,
            status_code=status_code,
            response_data=response_data,
            raw_body=raw_body,
        )

    @staticmethod
    def _extract_data_payload(*, response_data: dict[str, Any], endpoint: str) -> dict[str, Any]:
        payload = response_data.get("data")
        if isinstance(payload, dict):
            return payload

        fallback_payload = response_data.get("result")
        if isinstance(fallback_payload, dict):
            return fallback_payload

        raise TmapiApiError(
            f"Invalid TMAPI response format at {endpoint}: data object is missing",
            endpoint=endpoint,
            response_data=response_data,
        )

    def _record_api_log(
        self,
        *,
        operation: str,
        endpoint: str,
        params: dict[str, Any],
        attempt: int,
        status_code: Optional[int],
        response_data: Optional[dict[str, Any]],
        raw_body: str,
        error_message: Optional[str] = None,
    ) -> None:
        self._api_logs.append(
            {
                "timestamp": self._now(),
                "operation": operation,
                "endpoint": endpoint,
                "params": params,
                "attempt": attempt,
                "status_code": status_code,
                "response": response_data,
                "raw_body": raw_body,
                "error": error_message,
            }
        )

    @staticmethod
    def _sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
        safe: dict[str, Any] = {}
        for key, value in params.items():
            if key == "apiToken":
                safe[key] = "***"
            else:
                safe[key] = value
        return safe

    def _should_retry_http_error(self, *, status_code: int, attempt: int) -> bool:
        retryable_status_codes = {408, 429, 500, 502, 503, 504}
        return status_code in retryable_status_codes and attempt < self._retry_attempts

    def _sleep_before_retry(self, attempt: int) -> None:
        if self._retry_backoff_sec <= 0:
            return
        time.sleep(self._retry_backoff_sec * attempt)

    def _build_ssl_context(self) -> Optional[ssl.SSLContext]:
        if self._verify_ssl:
            return None
        return ssl._create_unverified_context()

    @staticmethod
    def _parse_json(raw_body: str, *, endpoint: str) -> dict[str, Any]:
        data = Tmapi1688Client._try_parse_json(raw_body)
        if data is None:
            raise TmapiApiError(
                f"Invalid JSON response from {endpoint}",
                endpoint=endpoint,
                raw_body=raw_body,
            )
        return data

    @staticmethod
    def _try_parse_json(raw_body: str) -> Optional[dict[str, Any]]:
        if not raw_body:
            return {}
        try:
            parsed = json.loads(raw_body)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
        return {"result": parsed}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
