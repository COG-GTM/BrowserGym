import os
import pathlib
from time import time

import bs4
import gymnasium as gym
import playwright.sync_api
import pytest

# register openended gym environments
import browsergym.core
import browsergym.core.action
import browsergym.core.env
from browsergym.core.action.highlevel import HighLevelActionSet
from browsergym.core.action.python import PythonActionSet
from browsergym.core.constants import BROWSERGYM_ID_ATTRIBUTE as BID_ATTR
from browsergym.utils.obs import flatten_dom_to_str

__SLOW_MO = 1000 if "DISPLAY_BROWSER" in os.environ else None
__HEADLESS = False if "DISPLAY_BROWSER" in os.environ else True
__TIMEOUT = 500

__DATA_DIR = pathlib.Path(__file__).resolve().parent / "data"
TEST_PAGE = f"file://{__DATA_DIR}/test_page.html"
BASIC_IFRAME_PAGE = f"file://{__DATA_DIR}/basic_iframe_site/basic_iframe_2.html"


def test_gym_env():
    action_set = PythonActionSet()

    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": TEST_PAGE},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )
    obs, info = env.reset()

    assert not obs["last_action_error"]

    obs, reward, term, trunc, info = env.step(
        f"""\
page.get_by_label("Name:").click()
page.get_by_label("Name:").fill("Janice")
page.get_by_label("Name:").press("Tab")
page.get_by_label("Email:").fill("janice@mail.com")
page.get_by_label("Email:").press("Tab")
page.get_by_label("Age:", exact=True).fill("21")
page.get_by_label("Age:", exact=True).press("Tab")
"""
    )

    assert obs["last_action_error"] == ""
    assert reward == 0
    assert term == False
    assert trunc == False

    obs, reward, term, trunc, info = env.step(
        f"""\
page.get_by_label("Message:").fill("Hello")
page.get_by_label("Message:").press("Tab")
page.get_by_label("Subscribe to newsletter").check()
page.get_by_label("Subscribe to newsletter").press("Tab")
page.get_by_role("button", name="Submit").press("Enter")
"""
    )

    assert obs["last_action_error"] == ""
    assert reward == 0
    assert term == False
    assert trunc == False

    obs, reward, term, trunc, info = env.step(
        f"""\
page.get_by_label("LABEL DOES NOT EXIST:").fill("Hello")
page.get_by_role("button", name="Submit").press("Enter")
"""
    )

    assert obs["last_action_error"] != ""
    assert reward == 0
    assert term == False
    assert trunc == False

    env.close()


def test_max_episode_steps():
    # no max_steps
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": TEST_PAGE},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
    )
    obs, info = env.reset()

    obs, reward, term, trunc, info = env.step("")

    assert term == False
    assert trunc == False

    obs, reward, term, trunc, info = env.step("")

    assert term == False
    assert trunc == False

    # max_steps = 2
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": TEST_PAGE},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        max_episode_steps=2,
    )
    obs, info = env.reset()

    obs, reward, term, trunc, info = env.step("")

    assert term == False
    assert trunc == False

    obs, reward, term, trunc, info = env.step("")

    assert term == False
    assert trunc == True

    env.close()


def test_active_page():
    action_set = PythonActionSet()
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": TEST_PAGE},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )
    obs, info = env.reset()

    assert len(obs["open_pages_urls"]) == 1
    assert obs["active_page_index"] == 0

    obs, reward, term, trunc, info = env.step("page.context.new_page()")

    assert len(obs["open_pages_urls"]) == 2
    assert obs["active_page_index"] == 1

    obs, reward, term, trunc, info = env.step("page.context.pages[0].mouse.click(5, 5)")

    assert len(obs["open_pages_urls"]) == 2
    assert obs["active_page_index"] == 0

    obs, reward, term, trunc, info = env.step("page.context.pages[1].mouse.click(5, 5)")

    assert len(obs["open_pages_urls"]) == 2
    assert obs["active_page_index"] == 1

    obs, reward, term, trunc, info = env.step("page.context.pages[1].close()")

    assert len(obs["open_pages_urls"]) == 1
    assert obs["active_page_index"] == 0

    obs, reward, term, trunc, info = env.step("page.close()")

    assert len(obs["open_pages_urls"]) == 1
    assert obs["active_page_index"] == 0

    obs, reward, term, trunc, info = env.step("page.context.new_page()")

    assert len(obs["open_pages_urls"]) == 2
    assert obs["active_page_index"] == 1

    obs, reward, term, trunc, info = env.step("page.close()")

    assert len(obs["open_pages_urls"]) == 1
    assert obs["active_page_index"] == 0

    env.close()


def test_nested_iframes_default_demo_mode():
    demo_mode = "default"
    action_set = HighLevelActionSet(demo_mode=demo_mode)
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": BASIC_IFRAME_PAGE},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )
    obs, info = env.reset()
    assert not obs["last_action_error"]

    soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")
    inner_checkbox = soup.find("input", attrs={"id": "checkbox_2"})

    assert inner_checkbox.has_attr("checked")
    # click box
    action = f"""\
click({repr(inner_checkbox.get(BID_ATTR))})
"""
    click_start = time()
    obs, _, _, _, _ = env.step(action)
    click_end = time()
    # clicking should be slow in demo mode
    assert click_end - click_start > 1

    soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")
    inner_checkbox = soup.find("input", attrs={"id": "checkbox_2"})
    # box is not checked; meaning it was clicked by the previous action
    assert not inner_checkbox.has_attr("checked")

    env.close()


@pytest.mark.parametrize("global_demo_mode", [True, False])
@pytest.mark.parametrize("demo_mode", [None, "off", "default", "only_visible_elements", "all_blue"])
def test_demo_mode(global_demo_mode: bool, demo_mode: str):
    action_set = HighLevelActionSet(demo_mode=demo_mode)
    browsergym.core.action.set_global_demo_mode(global_demo_mode)

    demo_mode_active = (global_demo_mode and demo_mode is None) or (
        demo_mode is not None and demo_mode != "off"
    )

    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": TEST_PAGE},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )
    obs, info = env.reset()
    assert not obs["last_action_error"]

    soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")
    email_field = soup.find("input", attrs={"id": "email"})
    checkbox = soup.find("input", attrs={"id": "subscribe"})

    # check that the email field is empty
    assert email_field.get("value") == ""

    # check that the box is not checked
    assert not checkbox.has_attr("checked")

    # click box
    action = f"""\
click({repr(checkbox.get(BID_ATTR))})
"""
    obs, reward, terminated, truncated, info = env.step(action)
    assert not obs["last_action_error"]

    soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")
    checkbox = soup.find("input", attrs={"type": "checkbox", "id": "subscribe"})

    # check that the box is checked
    assert checkbox.has_attr("checked")

    # clicking should be slow (only in demo mode)
    action_time = info["action_exec_stop"] - info["action_exec_start"]
    if demo_mode_active:
        assert action_time > 2
    else:
        assert action_time <= 1.5

    # fill box
    action = f"""\
fill({repr(email_field.get(BID_ATTR))}, "test@test")
"""
    obs, reward, terminated, truncated, info = env.step(action)
    assert not obs["last_action_error"]

    soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")

    # email field has been filled correctly
    email_field = soup.find("input", attrs={"id": "email"})
    assert email_field.get("value") == "test@test"

    # typing should be slow (only in demo mode)
    action_time = info["action_exec_stop"] - info["action_exec_start"]
    if demo_mode_active:
        assert action_time > 3.5
    else:
        assert action_time <= 3.5

    env.close()


@pytest.mark.parametrize("resizeable_window", (True, False))
@pytest.mark.parametrize("size", ((1600, 1200), (800, 800)))
def test_resizeable_window(resizeable_window, size):
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": TEST_PAGE},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        viewport={"width": size[0], "height": size[1]},
        resizeable_window=resizeable_window,
    )
    obs, info = env.reset()
    assert not obs["last_action_error"]

    assert (obs["screenshot"].shape[1], obs["screenshot"].shape[0]) == size

    env.close()


class _FakePage:
    def __init__(self, title="", closed=False, title_error=None):
        self._title = title
        self._closed = closed
        self._title_error = title_error

    def is_closed(self):
        return self._closed

    def close(self):
        self._closed = True

    def title(self):
        if self._title_error:
            raise playwright.sync_api.Error(self._title_error)
        return self._title


class _FakeContext:
    def __init__(self, pages):
        self._pages = pages

    @property
    def pages(self):
        return [page for page in self._pages if not page.is_closed()]

    def new_page(self):
        page = _FakePage()
        self._pages.append(page)
        return page


def _make_unwrapped_env(pages):
    env = browsergym.core.env.BrowserEnv(task_entrypoint=None)
    env.context = _FakeContext(pages)
    return env


def test_active_page_check_history_exhausted_falls_back_to_open_page():
    closed_page = _FakePage(closed=True)
    unactivated_page = _FakePage()  # never fired browsergym_page_activated
    env = _make_unwrapped_env([closed_page, unactivated_page])
    env.page = closed_page
    env.page_history = {closed_page: None}

    env._active_page_check()

    assert env.page is unactivated_page
    assert env.page_history == {}


def test_active_page_check_crashed_page_falls_back_to_history():
    previous_page = _FakePage()
    crashed_page = _FakePage()
    env = _make_unwrapped_env([previous_page, crashed_page])
    env.page = crashed_page
    env.page_history = {previous_page: None, crashed_page: None}
    env.crashed_pages = {crashed_page}

    env._active_page_check()

    assert crashed_page.is_closed()
    assert env.page is previous_page
    assert list(env.page_history) == [previous_page]
    assert env.crashed_pages == set()


def test_active_page_check_only_crashed_page_opens_new_page():
    crashed_page = _FakePage()
    env = _make_unwrapped_env([crashed_page])
    env.page = crashed_page
    env.page_history = {crashed_page: None}
    env.crashed_pages = {crashed_page}

    env._active_page_check()

    assert env.page is not crashed_page
    assert env.context.pages == [env.page]


def test_open_pages_titles_tolerates_failing_pages():
    env = _make_unwrapped_env(
        [
            _FakePage(title="active"),
            _FakePage(title_error="Target crashed"),
            _FakePage(title_error="Execution context was destroyed"),
        ]
    )

    assert env._get_open_pages_titles() == ("active", "", "")


class _FakeChat:
    messages = []


class _RaisingTask:
    def __init__(self, error):
        self.error = error
        self.calls = 0

    def validate(self, page, chat_messages):
        self.calls += 1
        raise playwright.sync_api.Error(self.error)


def test_task_validate_crashed_page_recovers_without_reward():
    crashed_page, other_page = _FakePage(), _FakePage()
    env = _make_unwrapped_env([other_page, crashed_page])
    env.page = crashed_page
    env.page_history = {other_page: None, crashed_page: None}
    env.chat = _FakeChat()
    env.task = _RaisingTask("Page.evaluate: Target crashed")

    reward, done, user_message, info = env._task_validate()

    assert (reward, done, user_message) == (0, False, None)
    assert "Target crashed" in info["task_validation_error"]
    assert env.task.calls == 1  # validation is not re-run
    assert crashed_page.is_closed()
    assert env.page is other_page


def test_task_validate_other_errors_are_raised():
    page = _FakePage()
    env = _make_unwrapped_env([page])
    env.page = page
    env.page_history = {page: None}
    env.chat = _FakeChat()
    env.task = _RaisingTask("Page.evaluate: ReferenceError: foo is not defined")

    with pytest.raises(playwright.sync_api.Error):
        env._task_validate()


def test_crash_during_post_extract_recovers(monkeypatch):
    post_extract = browsergym.core.env._post_extract
    crashed = []

    def crashing_post_extract(page):
        # crash the renderer after the dom / axtree have been extracted
        if not crashed:
            crashed.append(page)
            try:
                page.goto("chrome://crash")
            except Exception:
                pass
        return post_extract(page)

    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": TEST_PAGE},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
    )
    env.reset()
    first_page = env.unwrapped.page
    second_page = env.unwrapped.context.new_page()
    second_page.goto(TEST_PAGE)
    env.unwrapped.page = second_page
    env.unwrapped.page_history[second_page] = None

    monkeypatch.setattr(browsergym.core.env, "_post_extract", crashing_post_extract)
    obs = env.unwrapped._get_obs()

    assert crashed == [second_page] and second_page.is_closed()
    assert env.unwrapped.page is first_page
    assert len(obs["open_pages_urls"]) == 1
    assert obs["url"] == TEST_PAGE
    assert obs["axtree_object"]
    assert obs["screenshot"].size > 0

    env.close()


def test_crashed_active_page_recovery():
    action_set = PythonActionSet()
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": TEST_PAGE},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )
    obs, info = env.reset()

    obs, reward, term, trunc, info = env.step("page.context.new_page()")

    assert len(obs["open_pages_urls"]) == 2
    assert obs["active_page_index"] == 1

    # crash the renderer of the active page
    obs, reward, term, trunc, info = env.step(
        """\
try:
    page.goto("chrome://crash")
except Exception:
    pass
"""
    )

    # the crashed page is closed, the previously active page becomes active again
    assert len(obs["open_pages_urls"]) == 1
    assert obs["active_page_index"] == 0
    assert obs["url"] == TEST_PAGE
    assert obs["axtree_object"]

    # the only remaining page crashes, a fresh page is opened
    obs, reward, term, trunc, info = env.step(
        """\
try:
    page.goto("chrome://crash")
except Exception:
    pass
"""
    )

    assert len(obs["open_pages_urls"]) == 1
    assert obs["active_page_index"] == 0
    assert obs["url"] == "about:blank"

    env.close()
