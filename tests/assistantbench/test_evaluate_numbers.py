import math

import pytest

from browsergym.assistantbench.evaluation.evaluate_utils.evaluate_numbers import (
    distance_function_log,
    evaluate_numbers,
)

ONE_MINUS_LN2 = 1 - math.log(2)


@pytest.mark.parametrize(
    "pred, gold, expected",
    [
        (0, 0, 1),
        (0.0, 0.0, 1),
        (10, 10, 1),
        (2.5, 2.5, 1),
        (20, 10, ONE_MINUS_LN2),
        (10, 20, ONE_MINUS_LN2),
        (11, 10, 1 - math.log(1.1)),
        (10, 11, 1 - math.log(1.1)),
        (1000, 1, 0),
        (1, 1000, 0),
        (2.7, 1, 1 - math.log(2.7)),
        # pred == 0 or gold == 0 is replaced by 1e-4 before the log ratio
        (0, 1e-4, 1),
        (1e-4, 0, 1),
        (0, 2e-4, ONE_MINUS_LN2),
        (2e-4, 0, ONE_MINUS_LN2),
        (0, 5, 0),
        (5, 0, 0),
        # negative answers (e.g. temperatures) are scored on magnitude when signs agree
        (-5, -5, 1),
        (-20, -10, ONE_MINUS_LN2),
        (-10, -20, ONE_MINUS_LN2),
        (-1000, -1, 0),
        (0, -1e-4, 0),
        (-1e-4, 0, 0),
        # opposite signs get no partial credit
        (-10, 10, 0),
        (10, -10, 0),
        (-10, 5, 0),
        (5, -10, 0),
    ],
)
def test_distance_function_log(pred, gold, expected):
    score = distance_function_log(pred, gold)
    assert not math.isnan(score)
    assert 0 <= score <= 1
    assert score == pytest.approx(expected)


@pytest.mark.parametrize(
    "a, b",
    [(20, 10), (3, 7), (0, 5), (0.001, 0.0005), (-4, -9), (-4, 9), (123456, 123457)],
)
def test_distance_function_log_is_symmetric(a, b):
    assert distance_function_log(a, b) == pytest.approx(distance_function_log(b, a))


def test_distance_function_log_does_not_warn_on_negative_inputs(recwarn):
    distance_function_log(-10, 5)
    distance_function_log(5, -10)
    distance_function_log(-10, -20)
    assert not [w for w in recwarn if issubclass(w.category, RuntimeWarning)]


@pytest.mark.parametrize(
    "pred, gold, expected",
    [
        ("3", "3", 1),
        ("3", 3, 1),
        (3, "3", 1),
        ("3.0", 3, 1),
        ("20", "10", ONE_MINUS_LN2),
        ("-20", -10, ONE_MINUS_LN2),
        ("0", 0, 1),
        ("1e3", 1000, 1),
        (10, 10.0, 1),
    ],
)
def test_evaluate_numbers_parses_strings(pred, gold, expected):
    assert evaluate_numbers(pred, gold) == pytest.approx(expected)


@pytest.mark.parametrize(
    "pred, gold",
    [
        ("abc", 3),
        ("", 3),
        ("3 km", 3),
        (3, "abc"),
        ("abc", "abc"),
    ],
)
def test_evaluate_numbers_non_numeric_scores_zero(pred, gold):
    assert evaluate_numbers(pred, gold) == 0


def test_evaluate_numbers_matches_distance_function_log():
    for pred, gold in [(7, 3), (3, 7), (0, 2), (-2, -8), (1.5, -1.5)]:
        assert evaluate_numbers(pred, gold) == pytest.approx(distance_function_log(pred, gold))
