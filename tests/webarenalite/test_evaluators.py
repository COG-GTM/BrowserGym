import json
import logging

import pytest

pytest.importorskip("nltk")
pytest.importorskip("webarena")

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from browsergym.webarenalite import evaluators
from browsergym.webarenalite.evaluators import (
    EvaluationInfrastructureError,
    HTMLContentEvaluator,
)

CONTEXT_DESTROYED = (
    "Page.evaluate: Execution context was destroyed, most likely because of a navigation"
)
TARGET_CLOSED = "Page.evaluate: Target page, context or browser has been closed"
FRAME_DETACHED = "Page.evaluate: Frame has been detached."
NOT_FOUND = "Page.evaluate: TypeError: Cannot read properties of null (reading 'outerText')"


class FakePage:
    """Minimal stand-in for playwright.sync_api.Page driven by scripted evaluate results."""

    def __init__(self, evaluate_results, networkidle_timeout=False):
        self.url = "http://localhost/start"
        self.evaluate_results = list(evaluate_results)
        self.networkidle_timeout = networkidle_timeout
        self.calls = []

    def goto(self, url):
        self.calls.append(("goto", url))
        self.url = url

    def wait_for_load_state(self, state, timeout=None):
        self.calls.append(("wait_for_load_state", state))
        if state == "networkidle" and self.networkidle_timeout:
            raise PlaywrightTimeoutError("Timeout exceeded waiting for networkidle")

    def wait_for_timeout(self, timeout):
        self.calls.append(("wait_for_timeout", timeout))

    def evaluate(self, expression):
        self.calls.append(("evaluate", expression))
        result = self.evaluate_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    def content(self):
        return "<html></html>"


def write_config(tmp_path, target):
    target = {
        "url": "http://localhost/target",
        "locator": "document.querySelector('#total').outerText",
        "required_contents": {"exact_match": "42"},
        **target,
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"intent": "", "eval": {"program_html": [target]}}))
    return config_file


def evaluate(tmp_path, page, **target):
    return HTMLContentEvaluator()(
        trajectory=[{}, {}], config_file=write_config(tmp_path, target), page=page
    )


def test_waits_for_load_state_instead_of_sleeping(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: pytest.fail("evaluator must not sleep"))
    page = FakePage(["42"], networkidle_timeout=True)

    assert evaluate(tmp_path, page) == 1.0
    assert page.calls[:3] == [
        ("goto", "http://localhost/target"),
        ("wait_for_load_state", "load"),
        ("wait_for_load_state", "networkidle"),
    ]


def test_freshly_navigated_page_settles_before_evaluation(tmp_path):
    page = FakePage(["42"])

    evaluate(tmp_path, page)

    waits = [call[1] for call in page.calls if call[0] == "wait_for_timeout"]
    assert len(waits) == 1 and 0 < waits[0] <= evaluators.MIN_SETTLE_MS
    assert page.calls.index(("wait_for_timeout", waits[0])) < [c[0] for c in page.calls].index(
        "evaluate"
    )


def test_last_url_target_does_not_settle(tmp_path):
    page = FakePage(["42"])

    evaluate(tmp_path, page, url="last")

    assert not any(call[0] in ("goto", "wait_for_timeout") for call in page.calls)


def test_locator_not_found_scores_zero_and_is_logged(tmp_path, caplog):
    page = FakePage([PlaywrightError(NOT_FOUND)])

    with caplog.at_level(logging.WARNING, logger=evaluators.__name__):
        assert evaluate(tmp_path, page) == 0.0

    assert "Cannot read properties of null" in caplog.text
    assert "#total" in caplog.text


@pytest.mark.parametrize("message", [CONTEXT_DESTROYED, FRAME_DETACHED])
def test_destroyed_context_is_retried_after_page_settles(tmp_path, caplog, message):
    page = FakePage([PlaywrightError(message), "42"])

    with caplog.at_level(logging.WARNING, logger=evaluators.__name__):
        assert evaluate(tmp_path, page) == 1.0

    evaluate_calls = [i for i, call in enumerate(page.calls) if call[0] == "evaluate"]
    assert len(evaluate_calls) == 2
    assert ("wait_for_load_state", "load") in page.calls[evaluate_calls[0] : evaluate_calls[1]]
    assert message in caplog.text


def test_persistent_page_error_raises_instead_of_scoring_zero(tmp_path, caplog):
    page = FakePage([PlaywrightError(TARGET_CLOSED), PlaywrightError(TARGET_CLOSED)])

    with caplog.at_level(logging.WARNING, logger=evaluators.__name__):
        with pytest.raises(EvaluationInfrastructureError, match="has been closed"):
            evaluate(tmp_path, page)

    assert "has been closed" in caplog.text


def test_failing_prep_action_is_logged_and_locator_still_runs(tmp_path, caplog):
    page = FakePage([PlaywrightError("Page.evaluate: TypeError: x is null"), "42"])

    with caplog.at_level(logging.WARNING, logger=evaluators.__name__):
        score = evaluate(tmp_path, page, prep_actions=["document.querySelector('#x').click()"])

    assert score == 1.0
    assert "prep_action" in caplog.text and "x is null" in caplog.text


def test_lambda_locator_prefix_is_removed_exactly(tmp_path):
    page = FakePage(["42"])

    evaluate(tmp_path, page, locator="lambda:document.title")

    assert ("evaluate", "document.title") in page.calls
