from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    # Expo (web, dev server / Metro)
    "http://localhost:8081",
    "http://127.0.0.1:8081",
    "http://localhost:19006",
    "http://127.0.0.1:19006",
    "http://localhost:19000",
    "http://127.0.0.1:19000",
]


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    data_dir: Path = Path("./.side-data")
    db_url: str | None = None
    runner_cmd: str | None = None
    fake_runner: bool = False
    fake_step_delay: float = 0.5
    notify_url: str | None = None
    notify_secret: str | None = None
    cors_origins: list[str] = field(default_factory=lambda: list(DEFAULT_CORS_ORIGINS))
    contract_path: Path | None = None
    poll_interval: float = 0.1
    sse_heartbeat: float = 15.0

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        extra_origins = [
            o.strip() for o in env.get("SIDE_CORS_ORIGINS", "").split(",") if o.strip()
        ]
        contract = env.get("SIDE_CONTRACT_PATH")
        return cls(
            data_dir=Path(env.get("SIDE_DATA_DIR", "./.side-data")),
            db_url=env.get("SIDE_DB_URL") or None,
            runner_cmd=env.get("SIDE_RUNNER_CMD") or None,
            fake_runner=_truthy(env.get("SIDE_FAKE_RUNNER")),
            fake_step_delay=float(env.get("SIDE_FAKE_STEP_DELAY", "0.5")),
            notify_url=(env.get("SIDE_NOTIFY_URL") or "").strip().rstrip("/") or None,
            notify_secret=env.get("SIDE_NOTIFY_SECRET") or None,
            cors_origins=DEFAULT_CORS_ORIGINS + extra_origins,
            contract_path=Path(contract) if contract else None,
        )

    @property
    def resolved_db_url(self) -> str:
        return self.db_url or f"sqlite:///{(self.data_dir / 'side.db').resolve()}"

    def resolved_contract_path(self) -> Path | None:
        if self.contract_path:
            return self.contract_path if self.contract_path.is_file() else None
        for parent in Path(__file__).resolve().parents:
            candidate = parent / "contracts" / "openapi.yaml"
            if candidate.is_file():
                return candidate
        return None
