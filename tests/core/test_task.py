import pathlib
import re
from typing import Tuple

import playwright
import pytest

from browsergym.core.env import BrowserEnv
from browsergym.core.task import AbstractBrowserTask


class MockImageGoalTask(AbstractBrowserTask):
    @classmethod
    def get_task_id(cls):
        return "mockimagegoal"

    def __init__(self, seed: int = 0, start_url: str = "https://www.google.com") -> None:
        """
        Args:
            seed: random seed.
            start_url: str, the url for the starting page.
            goal: str, the initial goal.

        """
        super().__init__(seed)
        self.start_url = start_url
        self.goal = [
            {"type": "text", "text": "This is a mock task with an image goal."},
            {
                "type": "image_url",
                "image_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAYAAADgdz34AAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAApgAAAKYB3X3/OAAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAANCSURBVEiJtZZPbBtFFMZ/M7ubXdtdb1xSFyeilBapySVU8h8OoFaooFSqiihIVIpQBKci6KEg9Q6H9kovIHoCIVQJJCKE1ENFjnAgcaSGC6rEnxBwA04Tx43t2FnvDAfjkNibxgHxnWb2e/u992bee7tCa00YFsffekFY+nUzFtjW0LrvjRXrCDIAaPLlW0nHL0SsZtVoaF98mLrx3pdhOqLtYPHChahZcYYO7KvPFxvRl5XPp1sN3adWiD1ZAqD6XYK1b/dvE5IWryTt2udLFedwc1+9kLp+vbbpoDh+6TklxBeAi9TL0taeWpdmZzQDry0AcO+jQ12RyohqqoYoo8RDwJrU+qXkjWtfi8Xxt58BdQuwQs9qC/afLwCw8tnQbqYAPsgxE1S6F3EAIXux2oQFKm0ihMsOF71dHYx+f3NND68ghCu1YIoePPQN1pGRABkJ6Bus96CutRZMydTl+TvuiRW1m3n0eDl0vRPcEysqdXn+jsQPsrHMquGeXEaY4Yk4wxWcY5V/9scqOMOVUFthatyTy8QyqwZ+kDURKoMWxNKr2EeqVKcTNOajqKoBgOE28U4tdQl5p5bwCw7BWquaZSzAPlwjlithJtp3pTImSqQRrb2Z8PHGigD4RZuNX6JYj6wj7O4TFLbCO/Mn/m8R+h6rYSUb3ekokRY6f/YukArN979jcW+V/S8g0eT/N3VN3kTqWbQ428m9/8k0P/1aIhF36PccEl6EhOcAUCrXKZXXWS3XKd2vc/TRBG9O5ELC17MmWubD2nKhUKZa26Ba2+D3P+4/MNCFwg59oWVeYhkzgN/JDR8deKBoD7Y+ljEjGZ0sosXVTvbc6RHirr2reNy1OXd6pJsQ+gqjk8VWFYmHrwBzW/n+uMPFiRwHB2I7ih8ciHFxIkd/3Omk5tCDV1t+2nNu5sxxpDFNx+huNhVT3/zMDz8usXC3ddaHBj1GHj/As08fwTS7Kt1HBTmyN29vdwAw+/wbwLVOJ3uAD1wi/dUH7Qei66PfyuRj4Ik9is+hglfbkbfR3cnZm7chlUWLdwmprtCohX4HUtlOcQjLYCu+fzGJH2QRKvP3UNz8bWk1qMxjGTOMThZ3kvgLI5AzFfo379UAAAAASUVORK5CYII=",
            },
        ]

    def setup(self, page: playwright.sync_api.Page) -> tuple[str, dict]:
        page.goto(self.start_url, timeout=10000)
        return self.goal, {}

    def teardown(self) -> None:
        pass

    def validate(
        self, page: playwright.sync_api.Page, chat_messages: list[str]
    ) -> Tuple[float, bool, str, dict]:
        reward, done, msg, info = 0, False, "", {}

        for message in chat_messages:
            if message["role"] == "user" and message["message"] == "exit":
                done = True
                break

        return reward, done, msg, info


def test_mock_image_goal_task():
    env = BrowserEnv(MockImageGoalTask)
    obs, _ = env.reset()

    assert "goal_object" in obs
    assert len(obs["goal_object"]) == 2
    assert obs["goal_object"][0]["type"] == "text"
    assert obs["goal_object"][0]["text"] == "This is a mock task with an image goal."
    assert obs["goal_object"][1]["type"] == "image_url"

    env.chat.add_message("user", "exit")
    obs, reward, terminated, _, _ = env.step("send_msg_to_user('bye')")

    assert reward == 0
    assert terminated is True

    env.close()


LOCAL_START_URL = f"file://{pathlib.Path(__file__).resolve().parent}/data/example.html"
IMAGE_DATA_URL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
LEGACY_GOAL_WARNING = 'WARNING: This goal cannot be converted to a text-only goal format. Use the new goal format instead ("goal_object" field). Any agent reading this should abort immediately.'
CHAT_GREETING = {
    "role": "assistant",
    "message": "Hi! I am your UI assistant, I can perform web tasks for you. What can I help you with?",
}


class MockGoalTask(AbstractBrowserTask):
    """Mock task whose setup() returns an arbitrary goal, to exercise BrowserEnv's goal handling."""

    @classmethod
    def get_task_id(cls):
        return "mockgoal"

    def __init__(self, seed: int = 0, goal=None) -> None:
        super().__init__(seed)
        self.goal = goal

    def setup(self, page: playwright.sync_api.Page) -> tuple[str, dict]:
        page.goto(LOCAL_START_URL, timeout=10000)
        return self.goal, {}

    def teardown(self) -> None:
        pass

    def validate(
        self, page: playwright.sync_api.Page, chat_messages: list[str]
    ) -> Tuple[float, bool, str, dict]:
        return 0, False, "", {}


def _chat(obs):
    return [{"role": m["role"], "message": m["message"]} for m in obs["chat_messages"]]


@pytest.mark.parametrize(
    "goal,expected_goal_object,expected_legacy_goal,expected_chat",
    [
        (None, [], "", [CHAT_GREETING]),
        (
            "Open the example page.",
            [{"type": "text", "text": "Open the example page."}],
            "Open the example page.",
            [CHAT_GREETING, {"role": "user", "message": "Open the example page."}],
        ),
        (
            [
                {"type": "text", "text": "Find this item."},
                {"type": "text", "text": "Then report its price."},
            ],
            [
                {"type": "text", "text": "Find this item."},
                {"type": "text", "text": "Then report its price."},
            ],
            "Find this item.\nThen report its price.",
            [
                CHAT_GREETING,
                {"role": "user", "message": "Find this item."},
                {"role": "user", "message": "Then report its price."},
            ],
        ),
        # VisualWebArena-style goal, with images given as {"url": ...} dicts
        (
            [
                {"type": "text", "text": "Find this item."},
                {"type": "image_url", "image_url": {"url": IMAGE_DATA_URL}},
                {"type": "text", "text": "Then report its price."},
            ],
            [
                {"type": "text", "text": "Find this item."},
                {"type": "image_url", "image_url": {"url": IMAGE_DATA_URL}},
                {"type": "text", "text": "Then report its price."},
            ],
            "Find this item.\n" + LEGACY_GOAL_WARNING,
            [
                CHAT_GREETING,
                {"role": "user", "message": "Find this item."},
                {"role": "user_image", "message": IMAGE_DATA_URL},
                {"role": "user", "message": "Then report its price."},
            ],
        ),
        # image given as a plain string
        (
            [{"type": "image_url", "image_url": IMAGE_DATA_URL}],
            [{"type": "image_url", "image_url": IMAGE_DATA_URL}],
            LEGACY_GOAL_WARNING,
            [CHAT_GREETING, {"role": "user_image", "message": IMAGE_DATA_URL}],
        ),
    ],
    ids=["none", "str", "text_list", "image_url_dict", "image_url_str"],
)
def test_goal_dispatch(goal, expected_goal_object, expected_legacy_goal, expected_chat):
    env = BrowserEnv(MockGoalTask, task_kwargs={"goal": goal}, headless=True)
    try:
        obs, _ = env.reset()

        assert list(obs["goal_object"]) == expected_goal_object
        assert obs["goal"] == expected_legacy_goal
        assert _chat(obs) == expected_chat

        obs, _, _, _, info = env.step("noop()")
        assert list(obs["goal_object"]) == expected_goal_object
        assert obs["goal"] == expected_legacy_goal
        assert not obs["last_action_error"]
        assert info["action_exec_timeout"] == 0
    finally:
        env.close()


@pytest.mark.parametrize(
    "goal,error_match",
    [
        (42, "task_goal should be of type str or list, got <class 'int'>"),
        (
            {"type": "text", "text": "hi"},
            "task_goal should be of type str or list, got <class 'dict'>",
        ),
        (
            [{"type": "text", "text": "hi"}, {"type": "audio", "audio": "x.wav"}],
            "Unknown message type 'audio' in the task goal.",
        ),
    ],
    ids=["int", "dict", "unknown_message_type"],
)
def test_goal_dispatch_invalid(goal, error_match):
    env = BrowserEnv(MockGoalTask, task_kwargs={"goal": goal}, headless=True)
    try:
        with pytest.raises(ValueError, match=re.escape(error_match)):
            env.reset()
    finally:
        env.close()


if __name__ == "__main__":
    test_mock_image_goal_task()
