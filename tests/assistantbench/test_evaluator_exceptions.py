from unittest import mock

import numpy as np
import pytest

from browsergym.assistantbench.evaluation import evaluator
from browsergym.assistantbench.evaluation.evaluate_utils import evaluate_dicts
from browsergym.assistantbench.evaluation.evaluator import (
    find_isnan,
    fix_ans,
    fix_number,
    fix_prediction,
    parse_answer,
    question_scorer,
)


def test_parse_fallbacks_preserved():
    assert find_isnan(float("nan")) is True
    assert find_isnan("abc") is False
    assert find_isnan(None) is False
    assert find_isnan([1.0, 2.0]) is False
    assert fix_ans(None) is None
    assert fix_number("12 sqft") == (12.0, True)
    assert fix_number("abc") == ("abc", False)
    assert parse_answer(["abc"]) == ("abc", "string")
    assert parse_answer(["{'a': 1}"]) == ([{"a": 1}], "json")
    assert parse_answer(["a", "b"]) == (["a", "b"], "string list")
    assert fix_prediction({"a": 1}, [{"a": 1}], "json") == ([{"a": 1}], True)
    assert fix_prediction("not json", [{"a": 1}], "json") == (["not json"], True)
    assert evaluate_dicts.fix_number("abc") == "abc"
    assert question_scorer("abc", "abc") == (1.0, 1.0)
    assert question_scorer('{"a": 1}', "{'a': 1}") == (1.0, 1.0)


def test_deeply_nested_json_falls_back_to_string():
    deep = "[" * 100000 + "0" + "]" * 100000
    assert question_scorer(deep, "abc") == (0.0, 1.0)
    assert parse_answer([deep]) == (deep, "string")
    assert parse_answer([deep, deep]) == ([deep, deep], "string list")
    assert fix_prediction(deep, [{"a": 1}], "json") == ([deep], True)


@pytest.mark.parametrize("exc", [KeyboardInterrupt, SystemExit])
def test_interrupts_propagate_from_json_loads(exc):
    with mock.patch.object(evaluator.json, "loads", side_effect=exc):
        with pytest.raises(exc):
            question_scorer("abc", "abc")
        with pytest.raises(exc):
            parse_answer(["abc"])
        with pytest.raises(exc):
            parse_answer(["a", "b"])
        with pytest.raises(exc):
            fix_prediction("abc", [{"a": 1}], "json")


@pytest.mark.parametrize("exc", [KeyboardInterrupt, SystemExit])
def test_interrupts_propagate_from_isnan(exc):
    with mock.patch.object(evaluator.np, "isnan", side_effect=exc):
        with pytest.raises(exc):
            find_isnan(1.0)


def test_unexpected_errors_are_not_swallowed():
    with mock.patch.object(evaluator.np, "isnan", side_effect=RuntimeError("bug")):
        with pytest.raises(RuntimeError):
            find_isnan(np.float64(1.0))
    with mock.patch.object(evaluator.json, "loads", side_effect=RuntimeError("bug")):
        with pytest.raises(RuntimeError):
            question_scorer("abc", "abc")
