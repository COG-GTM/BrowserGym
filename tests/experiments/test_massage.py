import gymnasium as gym
import pytest

from browsergym.experiments.benchmark import utils as benchmark_utils
from browsergym.experiments.benchmark.utils import (
    massage_task_within_subprocess,
    massage_tasks,
)


class _MassageTestEnv(gym.Env):
    observation_space = gym.spaces.Discrete(1)
    action_space = gym.spaces.Discrete(1)

    def __init__(self, fail_on=None):
        if fail_on == "make":
            raise RuntimeError("massage-test: make failed")
        self.fail_on = fail_on

    def action_mapping(self, action):
        return action

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        if self.fail_on == "reset":
            raise RuntimeError("massage-test: reset failed")
        return 0, {}

    def step(self, action):
        return 0, 0.0, False, False, {}

    def close(self):
        if self.fail_on in ("close", "reset"):
            raise RuntimeError("massage-test: close failed")


for _name, _fail_on in [
    ("ok", None),
    ("make-fails", "make"),
    ("close-fails", "close"),
    ("reset-and-close-fail", "reset"),
]:
    gym.register(
        id=f"browsergym/massage-test.{_name}",
        entry_point=_MassageTestEnv,
        kwargs={"fail_on": _fail_on},
        disable_env_checker=True,
        order_enforce=False,
    )


def test_massage_success():
    assert massage_task_within_subprocess("massage-test.ok", timeout=60) == ("success", None)


@pytest.mark.parametrize(
    "task_id, expected_msg",
    [
        ("massage-test.make-fails", "make failed"),
        ("massage-test.close-fails", "close failed"),
        ("massage-test.reset-and-close-fail", "reset failed"),
    ],
)
def test_massage_reports_child_errors(task_id, expected_msg):
    outcome, err_msg = massage_task_within_subprocess(task_id, timeout=60)
    assert outcome == "exception"
    assert isinstance(err_msg, str)
    assert expected_msg in err_msg


def _exit_without_reporting(outcome_queue, task_id):
    pass


def test_massage_child_exits_without_outcome(monkeypatch):
    monkeypatch.setattr(benchmark_utils, "run_massage", _exit_without_reporting)
    outcome, err_msg = massage_task_within_subprocess("massage-test.ok", timeout=60, kill_timeout=1)
    assert outcome == "exception"
    assert "exited with code 0 without reporting" in err_msg


def test_massage_tasks_continues_after_failure(monkeypatch):
    calls = []
    real = benchmark_utils.massage_task_within_subprocess

    def spy(task_id, timeout):
        calls.append(task_id)
        return real(task_id=task_id, timeout=timeout)

    monkeypatch.setattr(benchmark_utils, "massage_task_within_subprocess", spy)
    massage_tasks(["massage-test.make-fails", "massage-test.ok"], max_retries=1)
    assert calls == ["massage-test.make-fails"] * 2 + ["massage-test.ok"]
