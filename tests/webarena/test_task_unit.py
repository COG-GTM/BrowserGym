"""Offline unit tests for GenericWebArenaTask (no live WebArena instance required)."""

import enum
import json
import sys
from unittest.mock import MagicMock

import pytest

from browsergym.webarena.task import GenericWebArenaTask

WA_URLS = {
    "SHOPPING": "http://wa-shopping.test:7770",
    "SHOPPING_ADMIN": "http://wa-shopping-admin.test:7780/admin",
    "REDDIT": "http://wa-reddit.test:9999",
    "GITLAB": "http://wa-gitlab.test:8023",
    "WIKIPEDIA": "http://wa-wikipedia.test:8888/wikipedia_en_all_maxi_2022-05/A/Landing",
    "MAP": "http://wa-map.test:3000",
    "HOMEPAGE": "http://wa-homepage.test:4399",
}

TASK_CONFIGS = [
    {"task_id": 0, "intent_template_id": 100, "start_url": "__SHOPPING_ADMIN__", "sites": []},
    {"task_id": 1, "intent_template_id": 100, "start_url": "__GITLAB__", "sites": []},
    {"task_id": 2, "intent_template_id": 200, "start_url": "__REDDIT__", "sites": []},
]

ENV_CONFIG_SRC = """
import os

REDDIT = os.environ["REDDIT"]
SHOPPING = os.environ["SHOPPING"]
SHOPPING_ADMIN = os.environ["SHOPPING_ADMIN"]
GITLAB = os.environ["GITLAB"]
WIKIPEDIA = os.environ["WIKIPEDIA"]
MAP = os.environ["MAP"]
HOMEPAGE = os.environ["HOMEPAGE"]
ACCOUNTS = {}
"""

ACTIONS_SRC = """
from enum import IntEnum


class ActionTypes(IntEnum):
    NONE = 0
    STOP = 17
"""


@pytest.fixture
def fake_webarena(tmp_path, monkeypatch):
    """Install a minimal on-disk `webarena` package and dummy WA_* URLs for one test."""
    pkg = tmp_path / "webarena"
    (pkg / "browser_env").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "test.raw.json").write_text(json.dumps(TASK_CONFIGS))
    (pkg / "browser_env" / "__init__.py").write_text("")
    (pkg / "browser_env" / "env_config.py").write_text(ENV_CONFIG_SRC)
    (pkg / "browser_env" / "actions.py").write_text(ACTIONS_SRC)

    for key, url in WA_URLS.items():
        monkeypatch.setenv(f"WA_{key}", url)
        # WebArenaInstance copies WA_X -> X; register X so monkeypatch restores it afterwards
        monkeypatch.setenv(key, url)

    saved = {k: v for k, v in sys.modules.items() if k == "webarena" or k.startswith("webarena.")}
    for k in saved:
        del sys.modules[k]
    monkeypatch.syspath_prepend(str(tmp_path))

    from webarena.browser_env.actions import ActionTypes

    yield ActionTypes

    for k in [k for k in sys.modules if k == "webarena" or k.startswith("webarena.")]:
        del sys.modules[k]
    sys.modules.update(saved)


@pytest.fixture
def task(fake_webarena):
    task = GenericWebArenaTask(seed=0, task_id=0)
    task.config_file = "/tmp/fake_config.json"
    task.evaluator = MagicMock(return_value=0.0)
    return task


def make_page(*urls):
    page = MagicMock()
    page.context.pages = [MagicMock(url=url) for url in urls]
    return page


def evaluated_action(task):
    assert task.evaluator.call_count == 1
    trajectory = task.evaluator.call_args.kwargs["trajectory"]
    assert len(trajectory) == 2
    return trajectory[-1]


# __init__


def test_init_substitutes_urls_and_filters_by_task_id(fake_webarena):
    task = GenericWebArenaTask(seed=0, task_id=0)
    assert [c["task_id"] for c in task.task_configs] == [0]
    assert task.task_configs[0]["start_url"] == WA_URLS["SHOPPING_ADMIN"]


def test_init_filters_by_intent_template_id(fake_webarena):
    task = GenericWebArenaTask(seed=0, intent_template_id=100)
    assert sorted(c["task_id"] for c in task.task_configs) == [0, 1]
    assert {c["start_url"] for c in task.task_configs} == {
        WA_URLS["SHOPPING_ADMIN"],
        WA_URLS["GITLAB"],
    }


@pytest.mark.parametrize(
    "kwargs", [{}, {"task_id": 0, "intent_template_id": 100}], ids=["neither", "both"]
)
def test_init_requires_exactly_one_id(fake_webarena, kwargs):
    with pytest.raises(ValueError, match="One and only one"):
        GenericWebArenaTask(seed=0, **kwargs)


def test_init_unknown_task_id(fake_webarena):
    with pytest.raises(ValueError, match=r"task_id=999\.$"):
        GenericWebArenaTask(seed=0, task_id=999)


def test_init_unknown_intent_template_id(fake_webarena):
    with pytest.raises(ValueError, match=r"intent_template_id=999\.$"):
        GenericWebArenaTask(seed=0, intent_template_id=999)


# validate: unauthorized-URL safeguard


@pytest.mark.parametrize(
    "off_domain_url",
    [
        "https://www.google.com/search?q=answer",
        "http://wa-shopping.test:7771/",  # same host, different port
        "http://evil.test/?next=http://wa-reddit.test:9999",
    ],
)
def test_validate_unauthorized_tab_terminates(task, off_domain_url):
    page = make_page(WA_URLS["SHOPPING_ADMIN"] + "/dashboard", off_domain_url)
    messages = [{"role": "assistant", "message": "42"}]

    assert task.validate(page, messages) == (
        0,
        True,
        "",
        {"error": "Unauthorized url, terminating task"},
    )
    task.evaluator.assert_not_called()


def test_validate_authorized_tabs_reach_evaluator(task, fake_webarena):
    page = make_page(
        "about:blank",
        "chrome://newtab/",
        WA_URLS["HOMEPAGE"] + "/password.html",
        *[url + "/some/path?x=1" for key, url in WA_URLS.items() if key != "HOMEPAGE"],
    )
    task.evaluator.return_value = 0.0

    assert task.validate(page, []) == (0.0, False, "", {})
    assert task.evaluator.call_args.kwargs["page"] is page
    assert task.evaluator.call_args.kwargs["config_file"] == task.config_file
    assert task.evaluator.call_args.kwargs["client"] is None


# validate: chat message -> action mapping and done logic


def test_validate_assistant_message_is_stop_answer(task, fake_webarena):
    ActionTypes = fake_webarena
    task.evaluator.return_value = 1.0
    messages = [
        {"role": "user", "message": "goal"},
        {"role": "assistant", "message": "The answer is 42"},
    ]

    assert task.validate(make_page(WA_URLS["MAP"]), messages) == (1.0, True, "", {})
    action = evaluated_action(task)
    assert action == {"action_type": ActionTypes.STOP, "answer": "The answer is 42"}


def test_validate_stop_with_zero_score_is_done(task, fake_webarena):
    task.evaluator.return_value = 0.0
    messages = [{"role": "assistant", "message": "wrong answer"}]

    assert task.validate(make_page(WA_URLS["MAP"]), messages) == (0.0, True, "", {})


def test_validate_infeasible_maps_to_na(task, fake_webarena):
    ActionTypes = fake_webarena
    task.evaluator.return_value = 1.0
    messages = [{"role": "infeasible", "message": "Unachievable task."}]

    assert task.validate(make_page(WA_URLS["MAP"]), messages) == (1.0, True, "", {})
    assert evaluated_action(task) == {"action_type": ActionTypes.STOP, "answer": "N/A"}


@pytest.mark.parametrize(
    "messages",
    [[], [{"role": "user", "message": "goal"}], [{"role": "user_image", "message": "img"}]],
    ids=["no-messages", "last-user", "last-other-role"],
)
def test_validate_non_stop_zero_score_not_done(task, fake_webarena, messages):
    ActionTypes = fake_webarena
    task.evaluator.return_value = 0.0

    assert task.validate(make_page(WA_URLS["MAP"]), messages) == (0.0, False, "", {})
    assert evaluated_action(task) == {"action_type": ActionTypes.NONE, "answer": "whatever"}


def test_validate_non_stop_positive_score_is_done(task):
    task.evaluator.return_value = 1.0

    assert task.validate(make_page(WA_URLS["MAP"]), []) == (1.0, True, "", {})


# validate: evaluator AssertionError fallback


def test_validate_evaluator_assertion_error_scores_zero_and_stops(task):
    task.evaluator.side_effect = AssertionError("llm_fuzzy_match: 'correct' not in response")
    messages = [{"role": "assistant", "message": "some answer"}]

    assert task.validate(make_page(WA_URLS["MAP"]), messages) == (0.0, True, "", {})


def test_validate_evaluator_assertion_error_without_stop_not_done(task):
    task.evaluator.side_effect = AssertionError()

    assert task.validate(make_page(WA_URLS["MAP"]), []) == (0.0, False, "", {})


def test_validate_evaluator_other_errors_propagate(task):
    task.evaluator.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        task.validate(make_page(WA_URLS["MAP"]), [{"role": "assistant", "message": "x"}])
