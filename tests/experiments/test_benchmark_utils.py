import logging
import sys
import time
import types

import numpy as np
import pytest

from browsergym.experiments.benchmark import utils
from browsergym.experiments.benchmark.utils import (
    make_env_args_list_from_repeat_tasks,
    make_env_args_list_from_workarena_curriculum,
    massage_task_within_subprocess,
    massage_tasks,
    prepare_backend,
    run_massage,
)
from browsergym.experiments.loop import SEED_MAX, EnvArgs


# module-level (picklable) stand-ins for run_massage, executed inside the massage sub-process


def _massage_success(outcome_queue, task_id):
    outcome_queue.put(("success", None))


def _massage_exception(outcome_queue, task_id):
    outcome_queue.put(("exception", f"boom in {task_id}"))


def _massage_hang(outcome_queue, task_id):
    time.sleep(30)
    outcome_queue.put(("success", None))


def _massage_exit_without_outcome(outcome_queue, task_id):
    pass


def _massage_crash(outcome_queue, task_id):
    raise RuntimeError("crash before reporting an outcome")


class _ScriptedMassage:
    """Replaces massage_task_within_subprocess, returns pre-defined outcomes in order."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, task_id, timeout):
        self.calls.append((task_id, timeout))
        return self.outcomes.pop(0)


# make_env_args_list_from_repeat_tasks


def test_repeat_tasks_size_and_fields():
    tasks = ["miniwob.click-test", "miniwob.click-button", "miniwob.enter-text"]
    env_args_list = make_env_args_list_from_repeat_tasks(
        task_list=tasks,
        max_steps=7,
        n_repeats=4,
        seeds_rng=np.random.RandomState(0),
        viewport={"width": 800, "height": 600},
    )

    assert len(env_args_list) == len(tasks) * 4
    assert [env_args.task_name for env_args in env_args_list] == [
        t for t in tasks for _ in range(4)
    ]
    for env_args in env_args_list:
        assert isinstance(env_args, EnvArgs)
        assert isinstance(env_args.task_seed, int)
        assert 0 <= env_args.task_seed < SEED_MAX
        assert env_args.max_steps == 7
        assert env_args.headless is True
        assert env_args.record_video is False
        assert env_args.wait_for_user_message is False
        assert env_args.viewport == {"width": 800, "height": 600}
        assert env_args.slow_mo is None
        assert env_args.storage_state is None
        assert env_args.task_kwargs is None


def test_repeat_tasks_seeds_are_deterministic():
    tasks = ["miniwob.click-test", "miniwob.click-button"]

    def seeds(rng_seed):
        return [
            env_args.task_seed
            for env_args in make_env_args_list_from_repeat_tasks(
                task_list=tasks, max_steps=5, n_repeats=5, seeds_rng=np.random.RandomState(rng_seed)
            )
        ]

    expected_rng = np.random.RandomState(0)
    expected = [
        int(seed) for _ in tasks for seed in expected_rng.randint(low=0, high=SEED_MAX, size=5)
    ]

    assert seeds(0) == expected
    assert seeds(0) == seeds(0)
    assert seeds(0) != seeds(1)


def test_repeat_tasks_empty():
    assert (
        make_env_args_list_from_repeat_tasks(
            task_list=[], max_steps=5, n_repeats=3, seeds_rng=np.random.RandomState(0)
        )
        == []
    )
    assert (
        make_env_args_list_from_repeat_tasks(
            task_list=["miniwob.click-test"],
            max_steps=5,
            n_repeats=0,
            seeds_rng=np.random.RandomState(0),
        )
        == []
    )


# make_env_args_list_from_workarena_curriculum


class _FakeWorkArenaTask:
    def __init__(self, task_id):
        self.task_id = task_id

    def get_task_id(self):
        return self.task_id


def _install_fake_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


@pytest.mark.parametrize(
    "level,task_category_filter,curriculum_type,expected_filter,expected_is_agent",
    [
        ("l1", None, "human", "l1", False),
        ("l2", "shopping", "agent", "l2.shopping", True),
    ],
)
def test_workarena_curriculum(
    monkeypatch, level, task_category_filter, curriculum_type, expected_filter, expected_is_agent
):
    calls = []

    def get_all_tasks_agents(filter, meta_seed, is_agent_curriculum, n_seed_l1):
        calls.append(
            dict(filter=filter, meta_seed=meta_seed, is_agent=is_agent_curriculum, n=n_seed_l1)
        )
        return [(_FakeWorkArenaTask("workarena.a"), 3), (_FakeWorkArenaTask("workarena.b"), 11)]

    _install_fake_module(
        monkeypatch, "browsergym.workarena", get_all_tasks_agents=get_all_tasks_agents
    )

    env_args_list = make_env_args_list_from_workarena_curriculum(
        level=level,
        task_category_filter=task_category_filter,
        meta_seed=42,
        max_steps=15,
        curriculum_type=curriculum_type,
        seeds_l1=4,
    )

    assert calls == [dict(filter=expected_filter, meta_seed=42, is_agent=expected_is_agent, n=4)]
    assert [(e.task_name, e.task_seed, e.max_steps) for e in env_args_list] == [
        ("workarena.a", 3, 15),
        ("workarena.b", 11, 15),
    ]


@pytest.mark.parametrize("level,curriculum_type", [("l4", "human"), ("l1", "robot")])
def test_workarena_curriculum_invalid_args(level, curriculum_type):
    with pytest.raises(AssertionError):
        make_env_args_list_from_workarena_curriculum(
            level=level,
            task_category_filter=None,
            meta_seed=0,
            max_steps=10,
            curriculum_type=curriculum_type,
        )


# prepare_backend


def test_prepare_backend_unknown():
    with pytest.raises(NotImplementedError, match="Unknown benchmark backend 'unknown'"):
        prepare_backend("unknown")


@pytest.mark.parametrize(
    "backend,instance_module,instance_class,expected_task_ids",
    [
        (
            "webarena",
            "browsergym.webarena.instance",
            "WebArenaInstance",
            [f"webarena.{i}" for i in (410, 533, 561, 562, 574, 640, 680, 740)],
        ),
        (
            "visualwebarena",
            "browsergym.visualwebarena.instance",
            "VisualWebArenaInstance",
            [
                f"visualwebarena.{i}"
                for i in (0, 33, 555, 666, 282, 305, 314, 317, 318, 319, 410, 411, 427, 436, 440)
            ],
        ),
    ],
)
def test_prepare_backend_warm_up(
    monkeypatch, backend, instance_module, instance_class, expected_task_ids
):
    events = []

    class FakeInstance:
        def full_reset(self):
            events.append("full_reset")

    _install_fake_module(monkeypatch, f"browsergym.{backend}")
    _install_fake_module(monkeypatch, instance_module, **{instance_class: FakeInstance})
    monkeypatch.setattr(
        utils, "massage_tasks", lambda task_ids: events.append(("massage_tasks", task_ids))
    )

    prepare_backend(backend)

    assert events == ["full_reset", ("massage_tasks", expected_task_ids)]


def test_prepare_backend_warm_up_reset_failure_skips_massage(monkeypatch):
    class FailingInstance:
        def full_reset(self):
            raise RuntimeError("reset failed")

    _install_fake_module(monkeypatch, "browsergym.webarena")
    _install_fake_module(
        monkeypatch, "browsergym.webarena.instance", WebArenaInstance=FailingInstance
    )
    massaged = []
    monkeypatch.setattr(utils, "massage_tasks", massaged.append)

    with pytest.raises(RuntimeError, match="reset failed"):
        prepare_backend("webarena")
    assert massaged == []


# massage_tasks


def test_massage_tasks_success_first_try(monkeypatch, caplog):
    scripted = _ScriptedMassage([("success", None), ("success", None)])
    monkeypatch.setattr(utils, "massage_task_within_subprocess", scripted)

    with caplog.at_level(logging.INFO, logger=utils.logger.name):
        massage_tasks(["task.a", "task.b"], max_retries=1, timeout=12)

    assert scripted.calls == [("task.a", 12), ("task.b", 12)]
    assert "Massaging task 1 / 2: task.a" in caplog.text
    assert "Massaging task 2 / 2: task.b" in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_massage_tasks_retry_then_success(monkeypatch, caplog):
    scripted = _ScriptedMassage([("exception", "e"), ("success", None)])
    monkeypatch.setattr(utils, "massage_task_within_subprocess", scripted)

    with caplog.at_level(logging.INFO, logger=utils.logger.name):
        massage_tasks(["task.a"], max_retries=1, timeout=5)

    assert scripted.calls == [("task.a", 5), ("task.a", 5)]
    assert "Massage resulted in exception, retrying (1 / 1 retries)" in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_massage_tasks_no_retry(monkeypatch, caplog):
    scripted = _ScriptedMassage([("exception", "e"), ("success", None)])
    monkeypatch.setattr(utils, "massage_task_within_subprocess", scripted)

    with caplog.at_level(logging.INFO, logger=utils.logger.name):
        massage_tasks(["task.a"], max_retries=0, timeout=5)

    assert scripted.calls == [("task.a", 5)]
    assert "retrying" not in caplog.text
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == ["Massage unsuccessful after 0 retries, skipping. Last error message: e"]


def test_massage_tasks_gives_up_after_max_retries(monkeypatch, caplog):
    scripted = _ScriptedMassage(
        [
            ("exception", "first"),
            ("timeout", "Timeout 5 seconds exceeded"),
            ("exception", "last"),
            ("success", None),
        ]
    )
    monkeypatch.setattr(utils, "massage_task_within_subprocess", scripted)

    with caplog.at_level(logging.INFO, logger=utils.logger.name):
        massage_tasks(["task.a", "task.b"], max_retries=2, timeout=5)

    # task.a is attempted 1 + max_retries times, then skipped; task.b still gets massaged
    assert scripted.calls == [("task.a", 5)] * 3 + [("task.b", 5)]
    assert "Massage resulted in exception, retrying (1 / 2 retries)" in caplog.text
    assert "Massage resulted in timeout, retrying (2 / 2 retries)" in caplog.text
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == ["Massage unsuccessful after 2 retries, skipping. Last error message: last"]


# massage_task_within_subprocess (real sub-process, stubbed run_massage)


def test_massage_subprocess_success(monkeypatch):
    monkeypatch.setattr(utils, "run_massage", _massage_success)
    assert massage_task_within_subprocess("task.a", timeout=20) == ("success", None)


def test_massage_subprocess_exception(monkeypatch):
    monkeypatch.setattr(utils, "run_massage", _massage_exception)
    assert massage_task_within_subprocess("task.a", timeout=20) == ("exception", "boom in task.a")


def test_massage_subprocess_timeout_kills_process(monkeypatch, caplog):
    monkeypatch.setattr(utils, "run_massage", _massage_hang)

    start = time.monotonic()
    with caplog.at_level(logging.WARNING, logger=utils.logger.name):
        outcome = massage_task_within_subprocess("task.a", timeout=1, kill_timeout=5)
    elapsed = time.monotonic() - start

    assert outcome == ("timeout", "Timeout 1 seconds exceeded")
    # the hung sub-process was killed instead of waited for
    assert elapsed < 10
    assert "zombie" not in caplog.text


def test_massage_subprocess_zombie_warning(monkeypatch, caplog):
    class UnkillableProcess:
        exitcode = None

        def __init__(self, target, args):
            self.kill_calls = 0

        def start(self):
            pass

        def join(self, timeout=None):
            pass

        def is_alive(self):
            return True

        def kill(self):
            self.kill_calls += 1

    processes = []

    def make_process(target, args):
        process = UnkillableProcess(target, args)
        processes.append(process)
        return process

    monkeypatch.setattr(utils.mp, "Process", make_process)

    with caplog.at_level(logging.WARNING, logger=utils.logger.name):
        outcome = massage_task_within_subprocess("task.a", timeout=1, kill_timeout=2)

    assert outcome == ("timeout", "Timeout 1 seconds exceeded")
    assert [p.kill_calls for p in processes] == [1]
    assert (
        "Massage sub-process still alive 2 seconds after kill(), you might have a zombie process now."
        in caplog.text
    )


@pytest.mark.parametrize("target", [_massage_exit_without_outcome, _massage_crash])
def test_massage_subprocess_died_without_outcome(monkeypatch, target):
    monkeypatch.setattr(utils, "run_massage", target)

    start = time.monotonic()
    outcome, err_msg = massage_task_within_subprocess("task.a", timeout=20)
    elapsed = time.monotonic() - start

    assert outcome == "exception"
    assert "without reporting an outcome" in err_msg
    # no kill_timeout-long wait on the empty queue of an already exited sub-process
    assert elapsed < 5


def test_massage_subprocess_died_without_outcome_is_retried(monkeypatch, caplog):
    targets = [_massage_crash, _massage_success]
    real_process = utils.mp.Process
    used = []

    def make_process(target, args):
        used.append(targets[len(used)])
        return real_process(target=used[-1], args=args)

    monkeypatch.setattr(utils.mp, "Process", make_process)

    with caplog.at_level(logging.INFO, logger=utils.logger.name):
        massage_tasks(["task.a"], max_retries=1, timeout=20)

    assert used == targets
    assert "Massage resulted in exception, retrying (1 / 1 retries)" in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


# run_massage (in-process, fake gym environment)


class _FakeQueue:
    def __init__(self):
        self.items = []

    def put(self, item):
        self.items.append(item)


class _FakeEnv:
    def __init__(self, action_mapping_error=None, step_error=None, close_error=None):
        self.action_mapping_error = action_mapping_error
        self.step_error = step_error
        self.close_error = close_error
        self.calls = []

    @property
    def unwrapped(self):
        return self

    def action_mapping(self, action):
        self.calls.append(("action_mapping", action))
        if self.action_mapping_error:
            raise self.action_mapping_error

    def reset(self):
        self.calls.append(("reset",))

    def step(self, action):
        self.calls.append(("step", action))
        if self.step_error:
            raise self.step_error

    def close(self):
        self.calls.append(("close",))
        if self.close_error:
            raise self.close_error


def _patch_gym_make(monkeypatch, env):
    made = []

    def make(gym_id):
        made.append(gym_id)
        return env

    monkeypatch.setattr("gymnasium.make", make)
    return made


def test_run_massage_success(monkeypatch):
    env = _FakeEnv()
    made = _patch_gym_make(monkeypatch, env)
    outcome_queue = _FakeQueue()

    run_massage(outcome_queue, "webarena.410")

    assert made == ["browsergym/webarena.410"]
    assert env.calls == [
        ("action_mapping", "noop()"),
        ("reset",),
        ("step", "noop()"),
        ("step", "noop()"),
        ("close",),
    ]
    assert outcome_queue.items == [("success", None)]


def test_run_massage_action_mapping_fallback(monkeypatch):
    env = _FakeEnv(action_mapping_error=AttributeError("no action mapping"))
    _patch_gym_make(monkeypatch, env)
    outcome_queue = _FakeQueue()

    run_massage(outcome_queue, "webarena.410")

    assert env.calls == [
        ("action_mapping", "noop()"),
        ("reset",),
        ("step", ""),
        ("step", ""),
        ("close",),
    ]
    assert outcome_queue.items == [("success", None)]


def test_run_massage_exception(monkeypatch):
    env = _FakeEnv(step_error=ValueError("validation failed"))
    _patch_gym_make(monkeypatch, env)
    outcome_queue = _FakeQueue()

    run_massage(outcome_queue, "webarena.410")

    assert env.calls[-1] == ("close",)
    assert len(outcome_queue.items) == 1
    outcome, err_msg = outcome_queue.items[0]
    assert outcome == "exception"
    assert any("ValueError: validation failed" in line for line in err_msg)
