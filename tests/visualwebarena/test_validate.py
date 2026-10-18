import enum
import logging
import sys
import types
from types import SimpleNamespace

import pytest

from browsergym.visualwebarena.task import GenericVisualWebArenaTask


class _ActionTypes(enum.IntEnum):
    NONE = 0
    STOP = 17


@pytest.fixture(autouse=True)
def webarena_actions(monkeypatch):
    try:
        import visualwebarena.browser_env.actions  # noqa: F401
    except ImportError:
        actions = types.ModuleType("visualwebarena.browser_env.actions")
        actions.ActionTypes = _ActionTypes
        monkeypatch.setitem(sys.modules, "visualwebarena", types.ModuleType("visualwebarena"))
        monkeypatch.setitem(
            sys.modules,
            "visualwebarena.browser_env",
            types.ModuleType("visualwebarena.browser_env"),
        )
        monkeypatch.setitem(sys.modules, "visualwebarena.browser_env.actions", actions)


def llm_fuzzy_match(pred, reference, question):
    response = "the judge rambled without a verdict"
    if "partially correct" in response or "incorrect" in response:
        return 0.0
    assert "correct" in response
    return 1.0


def fuzzy_evaluator(trajectory, config_file, page):
    return llm_fuzzy_match(trajectory[-1]["answer"], "reference", "question")


def misconfigured_evaluator(trajectory, config_file, page):
    required_contents = "not a list"
    assert isinstance(required_contents, list)
    return 1.0


def make_task(evaluator):
    task = GenericVisualWebArenaTask.__new__(GenericVisualWebArenaTask)
    task.webarena_instance = SimpleNamespace(urls={}, home_url="http://localhost")
    task.config_file = None
    task.evaluator = evaluator
    return task


PAGE = SimpleNamespace(context=SimpleNamespace(pages=[SimpleNamespace(url="about:blank")]))
STOP_CHAT = [{"role": "assistant", "message": "42"}]


def test_llm_fuzzy_match_assertion_scores_zero_and_is_reported(caplog):
    task = make_task(fuzzy_evaluator)
    with caplog.at_level(logging.WARNING, logger="browsergym.visualwebarena.task"):
        reward, done, _, info = task.validate(PAGE, STOP_CHAT)

    assert reward == 0.0
    assert done
    assert info["evaluation_error"].startswith("AssertionError")
    assert any(r.levelno == logging.WARNING and r.exc_info for r in caplog.records)


def test_other_evaluator_assertion_is_not_swallowed():
    task = make_task(misconfigured_evaluator)
    with pytest.raises(AssertionError):
        task.validate(PAGE, STOP_CHAT)


def test_successful_evaluation_has_no_evaluation_error():
    task = make_task(lambda **kwargs: 1.0)
    reward, done, _, info = task.validate(PAGE, STOP_CHAT)
    assert (reward, done, info) == (1.0, True, {})
