"""Shared type definitions for BrowserGym observations, chat messages and goals."""

from typing import Any, TypedDict

import numpy as np
import playwright.sync_api
from numpy.typing import NDArray


class ChatMessage(TypedDict):
    """A message in the chat, as stored in ``Chat.messages`` and ``obs["chat_messages"]``."""

    role: str
    timestamp: float
    message: str


class _GoalMessageBase(TypedDict):
    type: str


class GoalMessage(_GoalMessageBase, total=False):
    """A goal message, OpenAI style (``{"type": "text", "text": ...}`` or ``{"type": "image_url", ...}``)."""

    text: str
    image_url: str | dict[str, str]


Goal = str | list[dict[str, Any]] | None
"""A task goal: legacy text, a list of OpenAI-style messages, or nothing."""


class ElementProperties(TypedDict):
    """Extra properties of a DOM element, indexed by bid in ``obs["extra_element_properties"]``."""

    visibility: float | None
    bbox: list[float] | None
    clickable: bool
    set_of_marks: bool | None


class BrowserGymObservation(TypedDict, total=False):
    """Observation returned by ``BrowserEnv.reset()`` and ``BrowserEnv.step()``.

    ``page`` is only present with ``use_raw_page_output=True``, in which case ``screenshot``,
    ``dom_object``, ``axtree_object``, ``extra_element_properties`` and ``focused_element_bid``
    are absent.
    """

    page: playwright.sync_api.Page
    chat_messages: tuple[ChatMessage, ...]
    goal: str
    goal_object: tuple[dict[str, Any], ...]
    open_pages_urls: tuple[str, ...]
    open_pages_titles: tuple[str, ...]
    active_page_index: NDArray[np.int_]
    url: str
    screenshot: NDArray[np.uint8]
    dom_object: dict[str, Any]
    axtree_object: dict[str, Any]
    extra_element_properties: dict[str, ElementProperties]
    focused_element_bid: str
    last_action: str
    last_action_error: str
    elapsed_time: NDArray[np.float64]
