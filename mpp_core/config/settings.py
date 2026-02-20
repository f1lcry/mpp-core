import os
from dataclasses import dataclass


@dataclass
class Settings:
    app_env: str = "dev"
    ingestion_batch_size: int = 10
    source_marketplace: str = "1688"
    target_marketplace: str = "ozon"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_env=os.getenv("MPP_APP_ENV", "dev"),
            ingestion_batch_size=int(os.getenv("MPP_INGESTION_BATCH_SIZE", "10")),
            source_marketplace=os.getenv("MPP_SOURCE_MARKETPLACE", "1688"),
            target_marketplace=os.getenv("MPP_TARGET_MARKETPLACE", "ozon"),
        )
