from unittest import mock

import pytest

from browsergym.core.chat import Chat
from browsergym.core.env import BrowserEnv
from browsergym.core.task import OpenEndedTask


class FlakyTask(OpenEndedTask):
    def teardown(self):
        raise RuntimeError("remote cleanup failed")


def make_env(task_entrypoint=OpenEndedTask):
    return BrowserEnv(
        task_entrypoint=task_entrypoint,
        task_kwargs={"start_url": "about:blank"},
        headless=True,
    )


def install_resources(env, task=None):
    env.task = task if task is not None else mock.MagicMock(name="task")
    env.chat = mock.MagicMock(name="chat")
    env.context = mock.MagicMock(name="context")
    env.browser = mock.MagicMock(name="browser")
    env.page = mock.MagicMock(name="page")
    env.page_history = {env.page: None}
    return env.task, env.chat, env.context, env.browser


def assert_released(env):
    assert env.task is None
    assert env.chat is None
    assert env.context is None
    assert env.browser is None
    assert env.page is None
    assert env.page_history == {}


@pytest.mark.parametrize("failing", ["task", "chat", "context", "browser"])
def test_close_releases_everything_when_one_release_fails(failing):
    env = make_env()
    task, chat, context, browser = install_resources(env)
    resources = {"task": task, "chat": chat, "context": context, "browser": browser}
    method = "teardown" if failing == "task" else "close"
    getattr(resources[failing], method).side_effect = RuntimeError("boom")

    env.close()

    task.teardown.assert_called_once()
    chat.close.assert_called_once()
    context.close.assert_called_once()
    browser.close.assert_called_once()
    assert_released(env)

    # closing again is a no-op instead of closing already-closed objects
    env.close()
    task.teardown.assert_called_once()
    browser.close.assert_called_once()


def test_close_releases_everything_then_reraises_interruption():
    env = make_env()
    task, chat, context, browser = install_resources(env)
    task.teardown.side_effect = KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        env.close()

    chat.close.assert_called_once()
    context.close.assert_called_once()
    browser.close.assert_called_once()
    assert_released(env)


def test_close_on_partially_initialized_env():
    env = make_env()
    task = mock.MagicMock(name="task")
    browser = mock.MagicMock(name="browser")
    # e.g. reset() failed in browser.new_context(): task and browser exist, context/chat don't
    env.task, env.browser = task, browser

    env.close()

    task.teardown.assert_called_once()
    browser.close.assert_called_once()
    assert_released(env)


def test_reset_recovers_after_failed_reset():
    env = make_env()
    pw = mock.MagicMock(name="playwright")
    first_browser = mock.MagicMock(name="first_browser")
    first_browser.new_context.side_effect = RuntimeError("new_context failed")
    pw.chromium.launch.return_value = first_browser

    with mock.patch("browsergym.core.env._get_global_playwright", return_value=pw):
        with pytest.raises(RuntimeError, match="new_context failed"):
            env.reset()

        # half-built env: task and browser set, context/chat missing
        assert env.task is not None
        assert env.browser is first_browser
        assert env.context is None and env.chat is None

        second_browser = mock.MagicMock(name="second_browser")
        second_browser.new_context.side_effect = RuntimeError("new_context failed again")
        pw.chromium.launch.return_value = second_browser
        with pytest.raises(RuntimeError, match="new_context failed again"):
            env.reset()

    # the second reset released the first episode's browser instead of raising AttributeError
    first_browser.close.assert_called_once()
    env.close()
    second_browser.close.assert_called_once()
    assert_released(env)


def test_reset_releases_previous_episode_when_task_teardown_fails():
    env = make_env(task_entrypoint=FlakyTask)
    task, chat, context, browser = install_resources(env, task=FlakyTask(seed=0, start_url="x"))
    pw = mock.MagicMock(name="playwright")
    pw.chromium.launch.side_effect = RuntimeError("stop after teardown")

    with mock.patch("browsergym.core.env._get_global_playwright", return_value=pw):
        with pytest.raises(RuntimeError, match="stop after teardown"):
            env.reset()

    chat.close.assert_called_once()
    context.close.assert_called_once()
    browser.close.assert_called_once()
    assert env.chat is None and env.context is None and env.browser is None


def test_chat_close_releases_browser_when_context_close_fails():
    chat = Chat.__new__(Chat)
    chat.context = mock.MagicMock(name="context")
    chat.browser = mock.MagicMock(name="browser")
    context, browser = chat.context, chat.browser
    context.close.side_effect = RuntimeError("browser crashed")

    chat.close()

    context.close.assert_called_once()
    browser.close.assert_called_once()
    assert chat.context is None and chat.browser is None
    chat.close()  # idempotent
    browser.close.assert_called_once()


def test_chat_init_releases_browser_when_setup_fails():
    pw = mock.MagicMock(name="playwright")
    browser = pw.chromium.launch.return_value
    browser.new_context.side_effect = RuntimeError("new_context failed")

    with mock.patch("browsergym.core.chat._get_global_playwright", return_value=pw):
        with pytest.raises(RuntimeError, match="new_context failed"):
            Chat(headless=True)

    browser.close.assert_called_once()


def test_chat_close_releases_browser_then_reraises_interruption():
    chat = Chat.__new__(Chat)
    chat.context = mock.MagicMock(name="context")
    chat.browser = mock.MagicMock(name="browser")
    browser = chat.browser
    chat.context.close.side_effect = KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        chat.close()

    browser.close.assert_called_once()
    assert chat.context is None and chat.browser is None
