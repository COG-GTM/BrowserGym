from typing import Union

import numpy as np


# Renamed calc_z function to distance_function_log
def distance_function_log(pred: float, gold: float):
    if pred == gold == 0:
        return 1
    if pred == 0:
        pred = 1e-4
    if gold == 0:
        gold = 1e-4
    if (pred < 0) != (gold < 0):
        return 0
    return max(0, 1 - abs(np.log(pred / gold)))


def evaluate_numbers(pred: Union[float, str], gold: float):
    res = None
    if type(pred) != float and type(pred) != int:
        try:
            pred = float(pred)
        except ValueError:
            res = 0
    if type(gold) != float and type(gold) != int:
        try:
            gold = float(gold)
        except ValueError:
            res = 0
    if res is None:
        res = distance_function_log(pred, gold)
    return res
