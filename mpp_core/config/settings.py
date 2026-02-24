import os
from dataclasses import dataclass
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
        )

    @property
    def has_ozon_seller_credentials(self) -> bool:
        return bool(self.ozon_seller_client_id and self.ozon_seller_api_key)
