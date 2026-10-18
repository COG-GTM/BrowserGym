from __future__ import annotations

import os
from dataclasses import dataclass, field

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _default_db_path() -> str:
    data_dir = os.environ.get("SIDE_DATA_DIR", "./.side-data")
    return os.path.join(data_dir, "notifications.db")


@dataclass
class Settings:
    db_path: str = field(default_factory=_default_db_path)
    dry_run: bool = False
    internal_secret: str | None = None
    expo_access_token: str | None = None
    expo_push_url: str = EXPO_PUSH_URL
    expo_receipts_url: str = EXPO_RECEIPTS_URL
    max_retries: int = 3
    backoff_base_s: float = 0.5
    backoff_max_s: float = 8.0
    http_timeout_s: float = 10.0
    receipt_interval_s: float = 60.0
    receipt_min_age_s: float = 900.0
    deep_link_base: str = "side://runs/"
    cors_origins: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        return cls(
            db_path=env.get("SIDE_NOTIFY_DB") or _default_db_path(),
            dry_run=_bool(env.get("SIDE_PUSH_DRY_RUN")),
            internal_secret=env.get("SIDE_NOTIFY_SECRET") or None,
            expo_access_token=env.get("EXPO_ACCESS_TOKEN") or None,
            expo_push_url=env.get("SIDE_EXPO_PUSH_URL", EXPO_PUSH_URL),
            expo_receipts_url=env.get("SIDE_EXPO_RECEIPTS_URL", EXPO_RECEIPTS_URL),
            max_retries=int(env.get("SIDE_PUSH_MAX_RETRIES", "3")),
            backoff_base_s=float(env.get("SIDE_PUSH_BACKOFF_BASE", "0.5")),
            backoff_max_s=float(env.get("SIDE_PUSH_BACKOFF_MAX", "8")),
            receipt_interval_s=float(env.get("SIDE_PUSH_RECEIPT_INTERVAL", "60")),
            receipt_min_age_s=float(env.get("SIDE_PUSH_RECEIPT_MIN_AGE", "900")),
            deep_link_base=env.get("SIDE_DEEP_LINK_BASE", "side://runs/"),
            cors_origins=[
                o.strip() for o in env.get("SIDE_CORS_ORIGINS", "").split(",") if o.strip()
            ],
        )
