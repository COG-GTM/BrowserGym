import math

import pytest

from browsergym.assistantbench.evaluation.evaluate_utils.evaluate_dicts import (
    calc_recall,
    calculate_f1_score,
    evaluate_dicts,
    evaluate_pair_of_dicts,
)
from browsergym.assistantbench.evaluation.evaluate_utils.utils import _align_bags
from browsergym.assistantbench.evaluation.evaluator import question_scorer

GOLD = {"name": "Joe's Pizza", "price": 12.5}


def test_calculate_f1_score():
    assert calculate_f1_score(0, 0) == 0
    assert calculate_f1_score(1.0, 1.0) == pytest.approx(1.0)
    assert calculate_f1_score(1.0, 0.5) == pytest.approx(2 / 3)
    assert calculate_f1_score(0.5, 1.0) == pytest.approx(2 / 3)
    assert calculate_f1_score(1.0, 0.0) == 0


def test_identical_dicts():
    assert evaluate_pair_of_dicts(dict(GOLD), GOLD) == pytest.approx(1.0)
    assert evaluate_dicts([dict(GOLD)], [GOLD]) == pytest.approx(1.0)


def test_missing_key_lowers_recall_only():
    pred = {"name": "Joe's Pizza"}
    assert calc_recall(pred, GOLD, True) == pytest.approx(0.5)
    assert calc_recall(GOLD, pred, False) == pytest.approx(1.0)
    assert evaluate_pair_of_dicts(pred, GOLD) == pytest.approx(2 / 3)


def test_extra_key_lowers_precision_only():
    pred = {"name": "Joe's Pizza", "price": 12.5, "city": "Brooklyn"}
    assert calc_recall(pred, GOLD, True) == pytest.approx(1.0)
    assert calc_recall(GOLD, pred, False) == pytest.approx(2 / 3)
    assert evaluate_pair_of_dicts(pred, GOLD) == pytest.approx(0.8)


def test_type_mismatch_scores_zero_for_that_key():
    pred = {"name": "Joe's Pizza", "price": "cheap"}
    assert calc_recall(pred, GOLD, True) == pytest.approx(0.5)
    assert calc_recall(GOLD, pred, False) == pytest.approx(0.5)
    assert evaluate_pair_of_dicts(pred, GOLD) == pytest.approx(0.5)


def test_all_keys_wrong_type_gives_zero():
    assert evaluate_pair_of_dicts({"price": "cheap"}, {"price": 12.5}) == 0
    # the string evaluator would give "a" vs ["a"] full credit; the type check must win
    assert evaluate_pair_of_dicts({"tags": "a"}, {"tags": ["a"]}) == 0


def test_numeric_strings_and_ints_are_normalised():
    # "$12.5" -> 12.5 and int 12 -> 12.0 via fix_number, so neither is a type mismatch
    pred = {"name": "Joe's Pizza", "price": "$12.5"}
    assert evaluate_pair_of_dicts(pred, GOLD) == pytest.approx(1.0)
    assert evaluate_pair_of_dicts({"price": 12}, {"price": 12.0}) == pytest.approx(1.0)


def test_close_numbers_get_partial_credit():
    expected = 1 - math.log(11 / 10)
    assert evaluate_pair_of_dicts({"price": 11}, {"price": 10}) == pytest.approx(expected)
    assert evaluate_pair_of_dicts({"price": 10}, {"price": 11}) == pytest.approx(expected)
    assert 0 < expected < 1


def test_evaluator_is_chosen_from_gold_value_type():
    # Both directions must pick the evaluator from the gold value's type; picking it from
    # the prediction (here a nested dict) would raise KeyError in the evaluator lookup.
    pred = {"name": {"first": "Joe"}, "price": 12.5}
    assert calc_recall(pred, GOLD, True) == pytest.approx(0.5)
    assert calc_recall(GOLD, pred, False) == pytest.approx(0.5)
    assert evaluate_pair_of_dicts(pred, GOLD) == pytest.approx(0.5)
    with pytest.raises(KeyError):
        calc_recall(pred, GOLD, False)


@pytest.mark.parametrize("pred", ["foo", ["foo"], [1, 2], [["a"]]])
def test_non_dict_predictions_score_zero(pred):
    assert evaluate_dicts(pred, [GOLD]) == 0


def test_empty_prediction_scores_zero():
    assert evaluate_dicts([], [GOLD, GOLD]) == 0
    assert evaluate_dicts("", [GOLD]) == 0


GOLD_ROWS = [
    {"name": "a", "price": 1.0},
    {"name": "b", "price": 2.0},
    {"name": "c", "price": 3.0},
]


def test_alignment_is_order_independent():
    assert evaluate_dicts(list(reversed(GOLD_ROWS)), GOLD_ROWS) == pytest.approx(1.0)


def test_fewer_predictions_than_gold_are_padded():
    pred = [GOLD_ROWS[2], GOLD_ROWS[0]]
    assert list(_align_bags(pred, GOLD_ROWS, evaluate_pair_of_dicts)) == pytest.approx(
        [1.0, 0.0, 1.0]
    )
    assert evaluate_dicts(pred, GOLD_ROWS) == pytest.approx(2 / 3)


def test_more_predictions_than_gold_are_padded():
    pred = GOLD_ROWS + [{"name": "d", "price": 4.0}]
    assert evaluate_dicts(pred, GOLD_ROWS) == pytest.approx(3 / 4)
    assert evaluate_dicts(GOLD_ROWS[:2], GOLD_ROWS[:1]) == pytest.approx(1 / 2)


def test_question_scorer_json_answers():
    gold = '{"name": "a", "price": 1}\n{"name": "b", "price": 2}'
    assert question_scorer(gold, gold) == (pytest.approx(1.0), 1.0)
    # one of two rows predicted, with a missing key
    score, has_ans = question_scorer('{"name": "a"}', gold)
    assert score == pytest.approx((2 / 3) / 2)
    assert has_ans == 1.0
