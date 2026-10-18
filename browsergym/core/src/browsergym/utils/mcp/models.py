from typing import Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    message: str
    timestamp: Optional[float] = None


class PageInfo(BaseModel):
    url: str
    title: str


class BrowserObservation(BaseModel):
    """Structured result returned by every BrowserGym MCP tool."""

    action: Optional[str] = Field(None, description="BrowserGym action executed, if any")
    url: str = Field(description="URL of the active page")
    title: str = Field("", description="Title of the active page")
    open_pages: list[PageInfo] = Field(default_factory=list)
    active_page_index: int = 0
    axtree: str = Field("", description="Accessibility tree text; elements are tagged with [bid]")
    focused_element_bid: Optional[str] = None
    last_action_error: str = ""
    goal: str = ""
    chat_messages: list[ChatMessage] = Field(default_factory=list)
    reward: float = 0.0
    terminated: bool = False
    truncated: bool = False
    step: int = 0
    task_id: str = ""
