from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RunStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
TERMINAL_STATUSES: frozenset[str] = frozenset({"succeeded", "failed", "cancelled"})

EXPO_TOKEN_RE = re.compile(r"^Expo(nent)?PushToken\[[^\]]+\]$")


class DeviceRegistration(BaseModel):
    expo_push_token: str = Field(min_length=1)
    platform: Literal["ios", "android"]
    run_ids: list[str] = Field(
        default_factory=list, description="Subscribe to specific runs; empty = all runs"
    )

    @field_validator("expo_push_token")
    @classmethod
    def _validate_token(cls, v: str) -> str:
        v = v.strip()
        if not EXPO_TOKEN_RE.match(v):
            raise ValueError("expo_push_token must look like ExponentPushToken[...]")
        return v

    @field_validator("run_ids")
    @classmethod
    def _dedupe_run_ids(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(r for r in v if r))


class RunEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["status", "step", "chat", "log"]
    run_id: str = Field(min_length=1)
    timestamp: str
    status: RunStatus | None = None
    step: dict[str, Any] | None = None
    chat: dict[str, Any] | None = None
    log: str | None = None


class RunEventAck(BaseModel):
    accepted: bool = True
    action: Literal["ignored", "duplicate", "queued"]
    recipients: int = 0
    reason: str | None = None
