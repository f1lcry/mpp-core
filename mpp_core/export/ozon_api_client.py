import json
import ssl
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib import error, request


@dataclass
class OzonApiResponse:
    status_code: int
    data: dict[str, Any]
    raw_body: str


class OzonApiError(RuntimeError):
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


class OzonApiClient:
    def __init__(
        self,
        *,
        client_id: str,
        api_key: str,
        base_url: str = "https://api-seller.ozon.ru",
        verify_ssl: bool = True,
        timeout_sec: int = 30,
        retry_attempts: int = 3,
        retry_backoff_sec: float = 1.0,
    ) -> None:
        self._client_id = client_id
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._verify_ssl = verify_ssl
        self._timeout_sec = timeout_sec
        self._retry_attempts = max(1, retry_attempts)
        self._retry_backoff_sec = max(0.0, retry_backoff_sec)

    @property
    def base_url(self) -> str:
        return self._base_url

    def post(self, endpoint: str, payload: dict[str, Any]) -> OzonApiResponse:
        url = f"{self._base_url}{endpoint}"
        request_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        for attempt in range(1, self._retry_attempts + 1):
            req = request.Request(
                url=url,
                data=request_body,
                method="POST",
                headers={
                    "Client-Id": self._client_id,
                    "Api-Key": self._api_key,
                    "Content-Type": "application/json",
                },
            )

            try:
                with request.urlopen(
                    req,
                    timeout=self._timeout_sec,
                    context=self._build_ssl_context(),
                ) as response:
                    raw_body = response.read().decode("utf-8")
                    data = self._parse_json(raw_body, endpoint=endpoint)
                    return OzonApiResponse(
                        status_code=response.status,
                        data=data,
                        raw_body=raw_body,
                    )
            except error.HTTPError as exc:
                raw_body = exc.read().decode("utf-8")
                response_data = self._try_parse_json(raw_body)
                if self._should_retry_http_error(status_code=exc.code, attempt=attempt):
                    self._sleep_before_retry(attempt)
                    continue
                raise OzonApiError(
                    f"Ozon API HTTP error at {endpoint}: {exc.code}",
                    endpoint=endpoint,
                    status_code=exc.code,
                    response_data=response_data,
                    raw_body=raw_body,
                ) from exc
            except error.URLError as exc:
                reason = exc.reason
                if isinstance(reason, ssl.SSLCertVerificationError):
                    raise OzonApiError(
                        (
                            "SSL certificate verification failed. "
                            "Set MPP_OZON_VERIFY_SSL=false for local trusted-proxy environments."
                        ),
                        endpoint=endpoint,
                    ) from exc
                if attempt < self._retry_attempts:
                    self._sleep_before_retry(attempt)
                    continue
                raise OzonApiError(
                    f"Ozon API request failed at {endpoint}: {reason}",
                    endpoint=endpoint,
                ) from exc

        raise OzonApiError(
            f"Ozon API request failed at {endpoint}: retry limit exceeded",
            endpoint=endpoint,
        )

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
        data = OzonApiClient._try_parse_json(raw_body)
        if data is None:
            raise OzonApiError(
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
