import logging
import time
import warnings
from importlib import resources
from pathlib import Path
from typing import Literal

import playwright.sync_api

from . import _get_global_playwright, chat_files

CHATBOX_DIR = resources.files(chat_files)
CHATBOX_FILE = "chatbox.html"
CHAT_ROLES = ("user", "user_image", "assistant", "info", "infeasible")

logger = logging.getLogger(__name__)


class Chat:
    def __init__(
        self, headless: bool, chat_size=(500, 800), record_video_dir=None, modern=True
    ) -> None:
        """
        Args:
            headless: whether the chat browser window is hidden.
            chat_size: (width, height) of the chat window.
            record_video_dir: if set, the chat window is recorded to `<record_video_dir>/chat_video`.
            modern: deprecated, ignored. There is a single chatbox UI now.
        """
        if not modern:
            warnings.warn(
                "Chat(modern=False) is deprecated: the classic and modern chatboxes were merged into"
                " a single chatbox, which is always used.",
                DeprecationWarning,
                stacklevel=2,
            )
        self.messages = []

        # create a new browser, browser context and page for the chat
        pw: playwright.sync_api.Playwright = _get_global_playwright()
        self.browser = pw.chromium.launch(
            headless=headless, args=[f"--window-size={chat_size[0]},{chat_size[1]}"]
        )
        self.context = self.browser.new_context(
            no_viewport=True,
            record_video_dir=Path(record_video_dir) / "chat_video" if record_video_dir else None,
            record_video_size=dict(width=chat_size[0], height=chat_size[1]),
        )
        self.page = self.context.new_page()
        self.recording_start_time = time.time() if record_video_dir else None

        # setup the chat page
        self.page.expose_function(
            "send_user_message", lambda msg: self._js_user_message_received_callback(msg=msg)
        )
        self.page.set_content(get_chatbox(CHATBOX_DIR))

    def _js_user_message_received_callback(self, msg: str):
        """Callback function for when a user message is received in the chatbox"""
        utc_time = time.time()
        self.messages.append({"role": "user", "timestamp": utc_time, "message": msg})
        # returning a list as JS doesnt like tuples
        return ["user", time.strftime("%H:%M:%S", time.localtime(utc_time)), msg]

    def add_message(
        self, role: Literal["user", "user_image", "assistant", "info", "infeasible"], msg: str
    ):
        """Add a message to the chatbox and update the page accordingly."""
        utc_time = time.time()
        if role not in CHAT_ROLES:
            raise ValueError(f"Invalid role: {role}")
        if role in ("user", "user_image", "assistant", "infeasible"):
            self.messages.append({"role": role, "timestamp": utc_time, "message": msg})
        timestamp = time.strftime("%H:%M:%S", time.localtime(utc_time))
        # pass values as arguments (not string-interpolated JS) so any message content is safe
        self.page.evaluate(
            "([role, timestamp, msg]) => addChatMessage(role, timestamp, msg)",
            [role, timestamp, msg],
        )

    def set_thinking(self, thinking: bool):
        """Show or hide the "agent is thinking" indicator. It is also toggled automatically:
        shown after a user message, hidden after an assistant/infeasible message."""
        self.page.evaluate("(thinking) => setThinking(thinking)", bool(thinking))

    def wait_for_user_message(self):
        logger.info("Waiting for message from user...")
        # reset flag
        self.page.evaluate("USER_MESSAGE_RECEIVED = false;")
        # wait for flag to be raised
        self.page.wait_for_function("USER_MESSAGE_RECEIVED", polling=100, timeout=0)
        logger.info("Message received.")

    def close(self):
        self.context.close()
        self.browser.close()


def get_chatbox(chatbox_dir=CHATBOX_DIR) -> str:
    with open(chatbox_dir / CHATBOX_FILE, "r", encoding="utf-8") as file:
        return file.read()


# backward-compatible aliases: chatbox.html and chatbox_modern.html were merged into chatbox.html
def get_chatbox_modern(chatbox_dir=CHATBOX_DIR) -> str:
    return get_chatbox(chatbox_dir)


def get_chatbox_classic(chatbox_dir=CHATBOX_DIR) -> str:
    return get_chatbox(chatbox_dir)
