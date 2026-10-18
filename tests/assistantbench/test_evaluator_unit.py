"""
Branch-level tests for the AssistantBench scorer. Pure Python, no browser required.

These pin the exact (score, has_ans) tuples produced for answer shapes that are not covered by the
replayed predictions in test_evaluation.py, so a change to parse_answer / fix_number /
fix_prediction / question_scorer cannot silently shift benchmark rewards.
"""

import math

import pytest

from browsergym.assistantbench.evaluation.evaluator import (
    find_isnan,
    fix_ans,
    fix_number,
    fix_prediction,
    is_empty_answer,
    parse_answer,
    question_scorer,
)


@pytest.mark.parametrize(
    "gold_lines, expected_answer, expected_evaluator",
    [
        (["42"], 42.0, "number"),
        (["$1,500"], 1.5, "number"),
        (["12 square kilometers"], 12.0, "number"),
        (['{"a": 1}'], [{"a": 1}], "json"),
        (["{'name': 'Bob', 'age': '3'}"], [{"name": "Bob", "age": "3"}], "json"),
        (["Paris"], "Paris", "string"),
        (['{"a": 1}', '{"b": 2}'], [{"a": 1}, {"b": 2}], "json"),
        (["Paris", "London"], ["Paris", "London"], "string list"),
        (['{"a": 1}', "Paris"], ['{"a": 1}', "Paris"], "string list"),
    ],
)
def test_parse_answer_routing(gold_lines, expected_answer, expected_evaluator):
    answer, evaluator = parse_answer(gold_lines)
    assert evaluator == expected_evaluator
    assert answer == expected_answer
    assert type(answer) == type(expected_answer)


@pytest.mark.parametrize(
    "raw, expected_value, expected_is_num",
    [
        ("$1,500", 1.5, True),
        ("45%", 45.0, True),
        ("300 sqft", 300.0, True),
        ("12 square kilometers", 12.0, True),
        ("$ 12 ", 12.0, True),
        ("1,5", 1.5, True),
        ("1,500,000", "1,500,000", False),
        ("abc", "abc", False),
        (7, 7.0, True),
        (2.5, 2.5, True),
    ],
)
def test_fix_number(raw, expected_value, expected_is_num):
    value, is_num = fix_number(raw)
    assert is_num is expected_is_num
    assert value == expected_value
    assert type(value) == type(expected_value)


def test_fix_number_comma_is_a_decimal_separator():
    # Intended behaviour (matches the reference AssistantBench scorer): commas are decimal
    # separators, so "1,500" means 1.5 and scores ~0 against a gold of 1500.
    assert fix_number("1,500") == (1.5, True)
    assert question_scorer("1,500", "1500") == (0.0, 1.0)
    assert question_scorer("1,5", "1.5") == (1.0, 1.0)


def test_fix_ans_rewrites_single_quoted_dicts():
    assert fix_ans("{'a': 'b', 'c': 1}") == '{"a": "b", "c": 1}'
    assert fix_ans(None) is None


@pytest.mark.parametrize(
    "value, expected",
    [
        (float("nan"), True),
        (1.0, False),
        ("nan", False),
        (None, False),
        ([1.0, float("nan")], False),
    ],
)
def test_find_isnan(value, expected):
    assert find_isnan(value) is expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("", True),
        ([], True),
        (None, True),
        (float("nan"), True),
        ("x", False),
        (0.0, False),
        (3, False),
        (True, False),
        ({"a": 1}, False),
    ],
)
def test_is_empty_answer(value, expected):
    assert is_empty_answer(value) is expected


@pytest.mark.parametrize(
    "prediction, gold, evaluator, expected",
    [
        ([], 3.0, "number", ([], False)),
        ("", "Paris", "string", ("", False)),
        (None, 3.0, "number", (None, False)),
        (["3", "4"], 3.0, "number", (["3", "4"], False)),
        (["3", "4"], ["3", "4"], "string list", (["3", "4"], True)),
        (["3"], 3.0, "number", (3.0, True)),
        ([3], 3.0, "number", (3.0, True)),
        (["3.5"], 3.5, "number", (3.5, True)),
        (["Paris"], "Paris", "string", (["Paris"], True)),
        # numeric singleton unwrapping only applies to number golds; text keeps its units
        (["3"], "Paris", "string", (["3"], True)),
        (["300 sqft"], "area: 300 sqft", "string", (["300 sqft"], True)),
        ("$12", 12.0, "number", (12.0, True)),
        ('{"a": 1}\n{"b": 2}', [{"a": 1}], "json", ([{"a": 1}, {"b": 2}], True)),
        ("not json", [{"a": 1}], "json", (["not json"], True)),
        ({"a": 1}, [{"a": 1}], "json", ([{"a": 1}], True)),
    ],
)
def test_fix_prediction(prediction, gold, evaluator, expected):
    assert fix_prediction(prediction, gold, evaluator) == expected


@pytest.mark.parametrize(
    "prediction, gold, expected",
    [
        # empty / missing answers -> has_ans 0
        ("", "Paris", (0.0, 0.0)),
        ("[]", "3", (0.0, 0.0)),
        ("NaN", "3", (0.0, 0.0)),
        ("null", "3", (0.0, 0.0)),
        ('["", ""]', "x\ny", (0.0, 0.0)),
        ("[null]", "x\ny", (0.0, 0.0)),
        ('["", "x"]', "x\ny", (0.5, 1.0)),
        # JSON-encoded prediction strings are decoded before scoring
        ('"Paris"', "Paris", (1.0, 1.0)),
        ("Paris", "Paris", (1.0, 1.0)),
        (3, "3", (1.0, 1.0)),
        # number gold
        ("1500", "1500", (1.0, 1.0)),
        ("12", "12 square kilometers", (1.0, 1.0)),
        ("1500 sqft", "1500", (1.0, 1.0)),
        ("0", "0", (1.0, 1.0)),
        ("6", "3", (1 - math.log(2), 1.0)),
        ('["3"]', "3", (1.0, 1.0)),
        ("[3]", "3", (1.0, 1.0)),
        ('["3.5"]', "3.5", (1.0, 1.0)),
        ('["3", "4"]', "3", (0.0, 1.0)),
        ('["Paris"]', "3", (0.0, 1.0)),
        ('{"a": 1}', "3", (0.0, 1.0)),
        ("true", "3", (0.0, 1.0)),
        # json gold
        ('{"a": 1}\n{"b": 2}', '{"a": 1}\n{"b": 2}', (1.0, 1.0)),
        ('{"a": 1}', "{'a': 1}", (1.0, 1.0)),
        # only gold answers get fix_ans quote repair, single-quoted predictions do not parse
        ("{'a': 1}", "{'a': 1}", (0.0, 1.0)),
        # numeric-looking singleton vs text gold is scored as text, units included
        ('["300 sqft"]', "area: 300 sqft", (0.8, 1.0)),
        ('["3"]', "Paris", (0.0, 1.0)),
        # string list gold
        ("London, Paris", "Paris\nLondon", (1 / 3, 1.0)),
        ('["Paris", "London"]', "Paris\nLondon", (1.0, 1.0)),
    ],
)
def test_question_scorer(prediction, gold, expected):
    score, has_ans = question_scorer(prediction, gold)
    assert (score, has_ans) == pytest.approx(expected)
