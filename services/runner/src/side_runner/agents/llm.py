"""Shared prompting for LLM agents, in the style of BrowserGym's demo_agent."""

import base64
import io
import os
import re
from typing import Any, Optional

import numpy as np
from PIL import Image

from .base import Agent, AgentOutput

SYSTEM_PROMPT = """\
# Instructions

You are a UI Assistant, your goal is to help the user perform tasks using a web browser.
You can communicate with the user via a chat, and you have access to a web browser that you
control through specific commands. Review the goal, the chat, and the current state of the
page to find the best possible next action. Your answer will be interpreted and executed by a
program, make sure to follow the formatting instructions: reason briefly, then give exactly
one action inside a single ```code block```.
When the goal is achieved (or you have the requested information), send the answer to the
user with send_msg_to_user(...). If the goal cannot be achieved, use report_infeasible(...).
"""

ACTION_EXAMPLES = """\
Here are examples of actions with chain-of-thought reasoning:

I now need to click on the Submit button to send the form. I will use the click action on the button, which has bid 12.
```click("12")```

I found the information requested by the user, I will send it to the chat.
```send_msg_to_user("The price for a 15\\" laptop is 1499 USD.")```
"""

_CODE_BLOCK = re.compile(r"```(?:[a-zA-Z]+\n)?(.*?)```", re.DOTALL)
TERMINAL_ACTIONS = ("send_msg_to_user", "report_infeasible")


def image_to_jpeg_base64(image: np.ndarray) -> str:
    img = Image.fromarray(np.asarray(image, dtype=np.uint8))
    if img.mode in ("RGBA", "LA"):
        img = img.convert("RGB")
    with io.BytesIO() as buf:
        img.save(buf, format="JPEG")
        return base64.b64encode(buf.getvalue()).decode()


def parse_response(text: str) -> tuple[str, Optional[str]]:
    """Split an LLM answer into (action, thought). The last code block is the action."""
    text = (text or "").strip()
    blocks = _CODE_BLOCK.findall(text)
    if not blocks:
        return text, None
    action = blocks[-1].strip()
    thought = _CODE_BLOCK.sub("", text).strip() or None
    return action, thought


def build_user_content(
    obs: dict, action_set, history: list[str], use_axtree: bool, use_screenshot: bool
) -> list[dict[str, Any]]:
    """Provider-neutral content parts: ``{"type": "text", "text"}`` / ``{"type": "image", "data"}``."""
    parts: list[dict[str, Any]] = []

    def text(t: str) -> None:
        parts.append({"type": "text", "text": t})

    goal_texts = [g["text"] for g in obs.get("goal_object", ()) if g.get("type") == "text"]
    if goal_texts:
        text("# Goal\n" + "\n".join(goal_texts) + "\n")

    chat = [
        m for m in obs.get("chat_messages", ()) if m["role"] in ("user", "assistant", "infeasible")
    ]
    if chat:
        text("# Chat Messages\n" + "".join(f"- [{m['role']}] {m['message']}\n" for m in chat))

    tabs = "# Currently open tabs\n"
    active = int(np.asarray(obs.get("active_page_index", [0])).ravel()[0])
    for i, (url, title) in enumerate(
        zip(obs.get("open_pages_urls", ()), obs.get("open_pages_titles", ()))
    ):
        tabs += f"Tab {i}{' (active tab)' if i == active else ''}\n  Title: {title}\n  URL: {url}\n"
    text(tabs)

    if use_axtree:
        text(f"# Current page Accessibility Tree\n\n{obs.get('axtree_txt', '')}\n")
    else:
        text(f"# Current page DOM\n\n{obs.get('pruned_html', '')}\n")

    if use_screenshot and obs.get("screenshot") is not None:
        text("# Current page Screenshot\n")
        parts.append({"type": "image", "data": image_to_jpeg_base64(obs["screenshot"])})

    text(
        "# Action Space\n\n"
        + action_set.describe(with_long_description=False, with_examples=True)
        + "\n"
        + ACTION_EXAMPLES
    )

    if history:
        text("# History of past actions\n" + "".join(f"\n{a}\n" for a in history))
        if obs.get("last_action_error"):
            text(f"# Error message from last action\n\n{obs['last_action_error']}\n")

    text(
        "# Next action\n\nThink step by step, then produce your next best action. Reflect on "
        "your past actions, any resulting error message, and the current state of the page."
    )
    return parts


class LLMAgent(Agent):
    """Base for chat-completion style agents. Subclasses implement :meth:`complete`."""

    api_key_env: str = ""
    default_model: str = ""
    model_env: str = ""

    def __init__(self, config, client=None):
        super().__init__(config)
        self.model = (
            self.config.get("model") or os.environ.get(self.model_env) or self.default_model
        )
        self.use_axtree = bool(self.config.get("use_axtree", True))
        self.use_screenshot = bool(self.config.get("use_screenshot", False))
        self.history: list[str] = []
        if client is None:
            if not os.environ.get(self.api_key_env):
                raise RuntimeError(f"{self.type} agent requires the {self.api_key_env} env var")
            client = self.make_client()
        self.client = client

    def make_client(self):
        raise NotImplementedError

    def complete(self, system: str, content: list[dict[str, Any]]) -> str:
        raise NotImplementedError

    def get_action(self, obs: dict) -> AgentOutput:
        content = build_user_content(
            obs, self.action_set, self.history, self.use_axtree, self.use_screenshot
        )
        answer = self.complete(SYSTEM_PROMPT, content)
        action, thought = parse_response(answer)
        self.history.append(action)
        return AgentOutput(
            action=action, thought=thought, done=action.lstrip().startswith(TERMINAL_ACTIONS)
        )
