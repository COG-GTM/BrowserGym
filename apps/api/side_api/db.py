"""SQLite run index (SQLModel). Step/chat/event data lives in the artifact layout."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Engine, event
from sqlmodel import Field, Session, SQLModel, create_engine

from .schemas import AgentConfig, Run


class RunRecord(SQLModel, table=True):
    __tablename__ = "runs"

    id: str = Field(primary_key=True)
    task_id: str = Field(index=True)
    goal: str | None = None
    start_url: str | None = None
    agent_json: str
    status: str = Field(index=True)
    reward: float | None = None
    n_steps: int = 0
    max_steps: int = 15
    headless: bool = True
    created_at: str = Field(index=True)
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    pid: int | None = None

    def to_run(self) -> Run:
        return Run(
            id=self.id,
            task_id=self.task_id,
            goal=self.goal,
            agent=AgentConfig.model_validate(json.loads(self.agent_json)),
            status=self.status,  # type: ignore[arg-type]
            reward=self.reward,
            n_steps=self.n_steps,
            max_steps=self.max_steps,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
            error=self.error,
        )

    def merge_run_json(self, data: dict[str, Any]) -> bool:
        """Apply runner-owned fields from run.json. Returns True if anything changed."""
        changed = False
        for key in ("status", "reward", "n_steps", "started_at", "finished_at", "error"):
            if key in data and getattr(self, key) != data[key]:
                if key == "status" and data[key] not in {
                    "queued",
                    "running",
                    "succeeded",
                    "failed",
                    "cancelled",
                }:
                    continue
                setattr(self, key, data[key])
                changed = True
        return changed


def make_engine(url: str) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.close()

    SQLModel.metadata.create_all(engine)
    return engine


def session(engine: Engine) -> Session:
    return Session(engine, expire_on_commit=False)
