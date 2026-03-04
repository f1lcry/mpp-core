import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

_DEFAULT_ENV_FILES = (".env", ".env.local")


def _load_env_files(env_files: Iterable[str]) -> None:
    for env_file in env_files:
        env_path = Path(env_file)
        if not env_path.is_absolute():
            env_path = Path.cwd() / env_path
        if not env_path.is_file():
            continue

        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            os.environ.setdefault(key, value)


def _to_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    clean = value.strip()
    return clean or None


def _to_bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    clean = value.strip().lower()
    if clean in {"1", "true", "yes", "on"}:
        return True
    if clean in {"0", "false", "no", "off"}:
        return False
    return default


def _to_int(value: Optional[str], default: int) -> int:
    if value is None:
        return default
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return default


def _to_int_list(value: Optional[str]) -> list[int]:
    if value is None:
        return []
    parsed: list[int] = []
    for raw_part in value.split(","):
        part = raw_part.strip()
        if not part:
            continue
        try:
            parsed.append(int(part))
        except ValueError:
            continue
    return parsed


@dataclass
class Settings:
    app_env: str = "dev"
    ingestion_batch_size: int = 10
    source_marketplace: str = "1688"
    target_marketplace: str = "ozon"
    ozon_seller_client_id: Optional[str] = None
    ozon_seller_api_key: Optional[str] = None
    ozon_seller_base_url: str = "https://api-seller.ozon.ru"
    ozon_verify_ssl: bool = True
    ozon_request_timeout_sec: int = 30
    tmapi_token: Optional[str] = None
    tmapi_base_url: str = "https://api.tmapi.top"
    tmapi_timeout_sec: int = 30
    tmapi_verify_ssl: bool = True
    tmapi_mode: str = "top_sales"
    tmapi_cat_ids: list[int] = field(default_factory=list)
    tmapi_category_pages: int = 1
    tmapi_top_limit: int = 10
    tmapi_shop_url: Optional[str] = None
    tmapi_member_id: Optional[str] = None
    sqlite_db_path: str = "data/mpp_core.db"

    @classmethod
    def from_env(cls, env_files: Iterable[str] = _DEFAULT_ENV_FILES) -> "Settings":
        _load_env_files(env_files)
        return cls(
            app_env=os.getenv("MPP_APP_ENV", "dev"),
            ingestion_batch_size=int(os.getenv("MPP_INGESTION_BATCH_SIZE", "10")),
            source_marketplace=os.getenv("MPP_SOURCE_MARKETPLACE", "1688"),
            target_marketplace=os.getenv("MPP_TARGET_MARKETPLACE", "ozon"),
            ozon_seller_client_id=_to_optional(os.getenv("MPP_OZON_SELLER_CLIENT_ID")),
            ozon_seller_api_key=_to_optional(os.getenv("MPP_OZON_SELLER_API_KEY")),
            ozon_seller_base_url=os.getenv("MPP_OZON_SELLER_BASE_URL", "https://api-seller.ozon.ru").rstrip("/"),
            ozon_verify_ssl=_to_bool(os.getenv("MPP_OZON_VERIFY_SSL"), default=True),
            ozon_request_timeout_sec=int(os.getenv("MPP_OZON_REQUEST_TIMEOUT_SEC", "30")),
            tmapi_token=_to_optional(os.getenv("MPP_TMAPI_TOKEN")),
            tmapi_base_url=os.getenv("MPP_TMAPI_BASE_URL", "https://api.tmapi.top").rstrip("/"),
            tmapi_timeout_sec=_to_int(os.getenv("MPP_TMAPI_TIMEOUT_SEC"), default=30),
            tmapi_verify_ssl=_to_bool(os.getenv("MPP_TMAPI_VERIFY_SSL"), default=True),
            tmapi_mode=os.getenv("MPP_TMAPI_MODE", "top_sales").strip().lower(),
            tmapi_cat_ids=_to_int_list(os.getenv("MPP_TMAPI_CAT_IDS")),
            tmapi_category_pages=max(1, _to_int(os.getenv("MPP_TMAPI_CATEGORY_PAGES"), default=1)),
            tmapi_top_limit=max(1, _to_int(os.getenv("MPP_TMAPI_TOP_LIMIT"), default=10)),
            tmapi_shop_url=_to_optional(os.getenv("MPP_TMAPI_SHOP_URL")),
            tmapi_member_id=_to_optional(os.getenv("MPP_TMAPI_MEMBER_ID")),
            sqlite_db_path=os.getenv("MPP_SQLITE_DB_PATH", "data/mpp_core.db"),
        )

    @property
    def has_ozon_seller_credentials(self) -> bool:
        return bool(self.ozon_seller_client_id and self.ozon_seller_api_key)

    @property
    def has_tmapi_token(self) -> bool:
        return bool(self.tmapi_token)

    @property
    def has_tmapi_shop_selector(self) -> bool:
        return bool(self.tmapi_shop_url or self.tmapi_member_id)

    @property
    def has_tmapi_categories(self) -> bool:
        return bool(self.tmapi_cat_ids)
