"""Pydantic v2 models mirroring ``components.schemas`` in contracts/openapi.yaml."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RunStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
AgentType = Literal["mock", "scripted", "openai", "anthropic"]
ChatRole = Literal["user", "assistant", "info", "infeasible"]
EventType = Literal["status", "step", "chat", "log"]

TERMINAL_STATUSES: frozenset[str] = frozenset({"succeeded", "failed", "cancelled"})


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Health(_Model):
    status: Literal["ok"] = "ok"
    version: str


class Task(_Model):
    id: str
    benchmark: str
    title: str
    description: str | None = None
    requires_setup: bool


class AgentInfo(_Model):
    type: AgentType
    title: str
    models: list[str] = Field(default_factory=list)


class AgentConfig(_Model):
    type: AgentType
    model: str | None = None
    use_screenshot: bool = False
    use_axtree: bool = True


class RunCreate(_Model):
    task_id: str = Field(min_length=1)
    agent: AgentConfig
    goal: str | None = None
    start_url: str | None = None
    max_steps: int = Field(default=15, ge=1, le=100)
    headless: bool = True


class Run(_Model):
    id: str
    task_id: str
    goal: str | None = None
    agent: AgentConfig
    status: RunStatus
    reward: float | None = None
    n_steps: int = 0
    max_steps: int = 15
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


class RunList(_Model):
    items: list[Run]
    next_cursor: str | None


class Step(_Model):
    index: int
    action: str | None = None
    thought: str | None = None
    url: str | None = None
    reward: float = 0.0
    terminated: bool = False
    truncated: bool = False
    last_action_error: str | None = None
    screenshot_url: str | None = None
    elapsed_ms: float | None = None
    timestamp: str


class StepDetail(Step):
    axtree_txt: str | None = None
    pruned_html: str | None = None
    focused_element_bid: str | None = None


class ChatMessage(_Model):
    role: ChatRole
    message: str
    timestamp: str


class ChatCreate(_Model):
    message: str = Field(min_length=1)


class RunEvent(_Model):
    type: EventType
    run_id: str
    timestamp: str
    status: RunStatus | None = None
    step: Step | None = None
    chat: ChatMessage | None = None
    log: str | None = None

    def to_json_dict(self) -> dict:
        # Omit absent optional payloads, but keep nulls inside Step (e.g. action) as the
        # contract marks those fields required + nullable.
        return {k: v for k, v in self.model_dump(mode="json").items() if v is not None}


class DeviceRegistration(_Model):
    expo_push_token: str
    platform: Literal["ios", "android"]
    run_ids: list[str] = Field(default_factory=list)


class ErrorResponse(_Model):
    detail: str
