import logging

import pytest

from browsergym.assistantbench.evaluation.evaluate_utils.evaluate_strings import (
    evaluate_strings,
)
from browsergym.assistantbench.evaluation.evaluator import question_scorer

LOGGER_NAME = "browsergym.assistantbench.evaluation.evaluate_utils.evaluate_strings"


def test_evaluate_strings_scores_valid_answers_without_warning(caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        assert evaluate_strings("Paris", "Paris") == 1.0
        assert evaluate_strings(["a b", "c"], ["c", "a b"]) == 1.0
        assert evaluate_strings("London", "Paris") == 0.0
    assert not caplog.records


@pytest.mark.parametrize(
    "prediction",
    [
        [["nested", "list"]],
        [{"key": "value"}],
        ["ok", None],
    ],
)
def test_evaluate_strings_logs_malformed_prediction(caplog, prediction):
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        assert evaluate_strings(prediction, ["ok"]) == 0.0
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "String evaluation failed" in warnings[0].getMessage()
    assert warnings[0].exc_info is not None


def test_question_scorer_logs_malformed_string_list_prediction(caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        accuracy, _ = question_scorer('[["a"], ["b"]]', "a\nb")
    assert accuracy == 0.0
    assert any("String evaluation failed" in r.getMessage() for r in caplog.records)


def test_evaluate_strings_propagates_unexpected_errors(monkeypatch):
    import browsergym.assistantbench.evaluation.evaluate_utils.evaluate_strings as mod

    def boom(*args, **kwargs):
        raise RuntimeError("evaluator bug")

    monkeypatch.setattr(mod, "_align_bags", boom)
    with pytest.raises(RuntimeError):
        evaluate_strings("Paris", "Paris")
