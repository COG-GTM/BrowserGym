import dataclasses
import json
import logging
import re
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from browsergym.core.action.highlevel import HighLevelActionSet
from browsergym.experiments import loop
from browsergym.experiments.agent import Agent
from browsergym.experiments.loop import (
    AbstractAgentArgs,
    EnvArgs,
    ExpArgs,
    ExpResult,
    StepInfo,
    _aggregate_episode_stats,
    _extract_err_msg,
    get_exp_result,
)
from browsergym.utils.obs import flatten_axtree_to_str


class MiniwobTestAgent(Agent):

    action_set = HighLevelActionSet(subsets="bid")

    def obs_preprocessor(self, obs: dict):
        return {"axtree_txt": flatten_axtree_to_str(obs["axtree_object"])}

    def get_action(self, obs: dict) -> tuple[str, dict]:
        match = re.search(r"^\s*\[(\d+)\].*button", obs["axtree_txt"], re.MULTILINE | re.IGNORECASE)

        if match:
            bid = match.group(1)
            action = f'click("{bid}")'
        else:
            raise Exception("Can't find the button's bid")

        return action, dict(think="I'm clicking the button as requested.")


@dataclasses.dataclass
class MiniwobTestAgentArgs(AbstractAgentArgs):
    def make_agent(self):
        return MiniwobTestAgent()


def test_run_exp():
    exp_args = ExpArgs(
        agent_args=MiniwobTestAgentArgs(),
        env_args=EnvArgs(task_name="miniwob.click-test", task_seed=42),
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        exp_args.prepare(tmp_dir)
        exp_args.run()
        exp_result = get_exp_result(exp_args.exp_dir)
        exp_record = exp_result.get_exp_record()

        target = {
            "env_args.task_name": "miniwob.click-test",
            "env_args.task_seed": 42,
            "env_args.headless": True,
            "env_args.record_video": False,
            "n_steps": 1,
            "cum_reward": 1.0,
            "terminated": True,
            "truncated": False,
        }

        assert len(exp_result.steps_info) == 2

        for key, target_val in target.items():
            assert key in exp_record
            assert exp_record[key] == target_val

        # TODO investigate why it's taking almost 5 seconds to solve
        assert exp_record["stats.cum_step_elapsed"] < 5
        if exp_record["stats.cum_step_elapsed"] > 3:
            t = exp_record["stats.cum_step_elapsed"]
            logging.warning(
                f"miniwob.click-test is taking {t:.2f}s (> 3s) to solve with an oracle."
            )


class RaisingMiniwobAgent(MiniwobTestAgent):
    def get_action(self, obs: dict) -> tuple[str, dict]:
        raise ValueError("agent blew up")


@dataclasses.dataclass
class RaisingMiniwobAgentArgs(AbstractAgentArgs):
    def make_agent(self):
        return RaisingMiniwobAgent()


class NoneActionMiniwobAgent(MiniwobTestAgent):
    def get_action(self, obs: dict) -> tuple[str, dict]:
        return None, dict(think="I give up.")


@dataclasses.dataclass
class NoneActionMiniwobAgentArgs(AbstractAgentArgs):
    def make_agent(self):
        return NoneActionMiniwobAgent()


class InterruptedMiniwobAgent(MiniwobTestAgent):
    def get_action(self, obs: dict) -> tuple[str, dict]:
        raise KeyboardInterrupt()


@dataclasses.dataclass
class InterruptedMiniwobAgentArgs(AbstractAgentArgs):
    def make_agent(self):
        return InterruptedMiniwobAgent()


@dataclasses.dataclass
class BrokenAgentArgs(AbstractAgentArgs):
    def make_agent(self):
        raise RuntimeError("cannot build agent")


def _read_summary(exp_dir):
    with open(Path(exp_dir) / "summary_info.json") as f:
        return json.load(f)


def test_run_exp_agent_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(loop, "_is_debugging", lambda: False)
    exp_args = ExpArgs(
        agent_args=RaisingMiniwobAgentArgs(),
        env_args=EnvArgs(task_name="miniwob.click-test", task_seed=42),
    )
    exp_args.prepare(tmp_path)
    exp_args.run()

    exp_result = ExpResult(exp_args.exp_dir)
    assert exp_result.status == "error"

    summary = exp_result.summary_info
    assert "ValueError" in summary["err_msg"]
    assert "agent blew up" in summary["err_msg"]
    assert "miniwob.click-test" in summary["err_msg"]
    assert "Traceback" in summary["stack_trace"]
    assert summary["n_steps"] == 0
    assert summary["cum_reward"] == 0
    assert summary["terminated"] is False
    assert summary["truncated"] is False

    assert exp_args.err_msg == summary["err_msg"]
    assert exp_args.stack_trace == summary["stack_trace"]
    # the reset step is still saved by the finally block
    assert len(exp_result.steps_info) == 1


def test_run_exp_agent_exception_reraised_in_debug_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(loop, "_is_debugging", lambda: True)
    exp_args = ExpArgs(
        agent_args=RaisingMiniwobAgentArgs(),
        env_args=EnvArgs(task_name="miniwob.click-test", task_seed=42),
        enable_debug=True,
    )
    exp_args.prepare(tmp_path)
    with pytest.raises(ValueError, match="agent blew up"):
        exp_args.run()

    # summary is still written by the finally block before the error propagates
    summary = _read_summary(exp_args.exp_dir)
    assert "ValueError" in summary["err_msg"]
    assert ExpResult(exp_args.exp_dir).status == "error"


def test_run_exp_none_action_truncates(tmp_path):
    exp_args = ExpArgs(
        agent_args=NoneActionMiniwobAgentArgs(),
        env_args=EnvArgs(task_name="miniwob.click-test", task_seed=42),
    )
    exp_args.prepare(tmp_path)
    exp_args.run()

    exp_result = ExpResult(exp_args.exp_dir)
    assert exp_result.status == "done"

    summary = exp_result.summary_info
    assert summary["err_msg"] is None
    assert summary["stack_trace"] is None
    assert summary["truncated"] is True
    assert summary["terminated"] is False
    assert summary["n_steps"] == 0
    assert summary["cum_reward"] == 0
    assert summary["stats.cum_steps"] == 1

    steps = exp_result.steps_info
    assert len(steps) == 1
    assert steps[0].action is None
    assert steps[0].truncated is True
    assert steps[0].agent_info["think"] == "I give up."
    assert not list(Path(exp_args.exp_dir).glob("step_1.pkl.gz"))


def test_run_exp_interrupt_records_early_termination(tmp_path):
    exp_args = ExpArgs(
        agent_args=InterruptedMiniwobAgentArgs(),
        env_args=EnvArgs(task_name="miniwob.click-test", task_seed=42),
    )
    exp_args.prepare(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        exp_args.run()

    exp_result = ExpResult(exp_args.exp_dir)
    assert exp_result.status == "error"

    summary = exp_result.summary_info
    assert "KeyboardInterrupt" in summary["err_msg"]
    assert "Early termination??" in summary["err_msg"]
    assert summary["stack_trace"] is None
    assert summary["terminated"] is False
    assert summary["truncated"] is False
    assert len(exp_result.steps_info) == 1


def test_run_exp_agent_creation_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(loop, "_is_debugging", lambda: False)
    exp_args = ExpArgs(
        agent_args=BrokenAgentArgs(),
        env_args=EnvArgs(task_name="miniwob.click-test", task_seed=42),
    )
    exp_args.prepare(tmp_path)
    exp_args.run()

    exp_result = ExpResult(exp_args.exp_dir)
    assert exp_result.status == "error"

    summary = exp_result.summary_info
    assert "RuntimeError" in summary["err_msg"]
    assert "cannot build agent" in summary["err_msg"]
    assert summary["n_steps"] == 0
    assert summary["stats.cum_steps"] == 1
    assert summary["terminated"] is None
    assert summary["truncated"] is None
    assert not list(Path(exp_args.exp_dir).glob("step_*.pkl.gz"))


def test_prepare_rerun_moves_old_exp_dir(tmp_path):
    exp_args = ExpArgs(
        agent_args=MiniwobTestAgentArgs(),
        env_args=EnvArgs(task_name="miniwob.click-test", task_seed=42),
    )
    exp_args.prepare(tmp_path)
    old_exp_dir = Path(exp_args.exp_dir)
    (old_exp_dir / "marker.txt").write_text("first run")

    exp_args.prepare(tmp_path)
    new_exp_dir = Path(exp_args.exp_dir)

    moved_dir = old_exp_dir.with_name("_" + old_exp_dir.name)
    assert moved_dir.is_dir()
    assert (moved_dir / "marker.txt").read_text() == "first run"
    assert (moved_dir / "exp_args.pkl").exists()

    assert new_exp_dir.is_dir()
    assert (new_exp_dir / "exp_args.pkl").exists()
    assert not (new_exp_dir / "marker.txt").exists()


def test_make_dir_avoids_collisions(tmp_path):
    exp_args = ExpArgs(
        agent_args=MiniwobTestAgentArgs(),
        env_args=EnvArgs(task_name="miniwob.click-test", task_seed=42),
        exp_name="agent/on:task*1",
    )
    exp_args.exp_date = datetime(2024, 1, 2, 3, 4, 5)

    exp_args._make_dir(tmp_path)
    first = Path(exp_args.exp_dir)
    assert first.name == "2024-01-02_03-04-05_agent_on_task_1"
    first.mkdir()

    exp_args._make_dir(tmp_path)
    second = Path(exp_args.exp_dir)
    assert second.name == "2024-01-02_03-04-05_agent_on_task_1_1"
    second.mkdir()

    exp_args._make_dir(tmp_path)
    assert Path(exp_args.exp_dir).name == "2024-01-02_03-04-05_agent_on_task_1_2"


def _step(stats=None, agent_info=None, reward=0, raw_reward=0, **kwargs):
    return StepInfo(
        stats=stats,
        agent_info={} if agent_info is None else agent_info,
        reward=reward,
        raw_reward=raw_reward,
        **kwargs,
    )


def test_aggregate_episode_stats_empty_episode():
    assert _aggregate_episode_stats([]) == {"cum_steps": 0}


@pytest.mark.filterwarnings("ignore:All-NaN:RuntimeWarning")
def test_aggregate_episode_stats_sum_max_and_nan_handling():
    episode_info = [
        _step(stats=None),  # e.g. reset step without stats
        _step(stats={"a": 1, "b": 2.5, "c": None, "d": float("nan")}),
        _step(stats={"a": 3, "b": None, "c": None}),
        _step(stats={"a": 2, "b": 0.5, "c": None, "d": 4.0}),  # "e" missing until here
        _step(stats={"e": 7}),
    ]

    stats = _aggregate_episode_stats(episode_info)

    assert stats == {
        "cum_steps": 5,
        "cum_a": 6,
        "max_a": 3,
        "cum_b": 3.0,
        "max_b": 2.5,
        # all-None stats: nansum is 0, nanmax is NaN -> None
        "cum_c": 0.0,
        "max_c": None,
        "cum_d": 4.0,
        "max_d": 4.0,
        "cum_e": 7,
        "max_e": 7,
    }
    # values are plain python types (json serializable), not numpy scalars
    for key, val in stats.items():
        assert val is None or type(val) in (int, float), key
    json.dumps(stats)


def test_extract_err_msg_no_errors():
    assert _extract_err_msg([]) == (None, None)
    assert _extract_err_msg([_step(), _step(agent_info={"think": "ok"})]) == (None, None)


def test_extract_err_msg_last_error_wins():
    no_agent_info = _step()
    no_agent_info.agent_info = None
    episode_info = [
        _step(agent_info={"err_msg": "first", "stack_trace": "trace1"}),
        no_agent_info,
        _step(agent_info={"err_msg": "second"}),
        _step(agent_info={"think": "fine"}),
    ]
    assert _extract_err_msg(episode_info) == ("second", None)


def _summary_exp_args():
    return ExpArgs(
        agent_args=MiniwobTestAgentArgs(),
        env_args=EnvArgs(task_name="miniwob.click-test", task_seed=42),
    )


def test_save_summary_info_err_msg_with_empty_episode(tmp_path):
    episode_info = []
    _summary_exp_args().save_summary_info(episode_info, tmp_path, "boom", "trace")

    # a placeholder StepInfo is appended to carry the error
    assert len(episode_info) == 1
    assert episode_info[0].agent_info["err_msg"] == "boom"
    assert episode_info[0].agent_info["stack_trace"] == "trace"

    summary = _read_summary(tmp_path)
    assert summary["err_msg"] == "boom"
    assert summary["stack_trace"] == "trace"
    assert summary["n_steps"] == 0
    assert summary["cum_reward"] == 0
    assert summary["stats.cum_steps"] == 1
    assert summary["terminated"] is None
    assert summary["truncated"] is None


def test_save_summary_info_lifts_agent_err_msg_and_aggregates(tmp_path):
    episode_info = [
        _step(step=0, terminated=False, truncated=False),
        _step(
            step=1,
            reward=0.25,
            raw_reward=None,
            stats={"step_elapsed": 1.5, "n_token_goal": 10},
            agent_info={"err_msg": "parse error", "stack_trace": "agent trace"},
            terminated=False,
            truncated=False,
        ),
        _step(
            step=2,
            reward=0.75,
            raw_reward=2,
            stats={"step_elapsed": 0.5, "n_token_goal": None},
            terminated=True,
            truncated=False,
        ),
    ]
    _summary_exp_args().save_summary_info(episode_info, tmp_path, None, None)

    summary = _read_summary(tmp_path)
    assert summary["err_msg"] == "parse error"
    assert summary["stack_trace"] == "agent trace"
    assert summary["n_steps"] == 2
    assert summary["cum_reward"] == 1.0
    assert summary["cum_raw_reward"] == 2
    assert summary["terminated"] is True
    assert summary["truncated"] is False
    assert summary["stats.cum_steps"] == 3
    assert summary["stats.cum_step_elapsed"] == 2.0
    assert summary["stats.max_step_elapsed"] == 1.5
    assert summary["stats.cum_n_token_goal"] == 10
    assert summary["stats.max_n_token_goal"] == 10

    exp_result = ExpResult(tmp_path)
    assert exp_result.status == "error"


def test_save_summary_info_explicit_err_msg_overrides_agent_info(tmp_path):
    episode_info = [
        _step(agent_info={"err_msg": "old", "stack_trace": "old trace"}),
        _step(terminated=False, truncated=False),
    ]
    _summary_exp_args().save_summary_info(episode_info, tmp_path, "env crash", "env trace")

    assert episode_info[-1].agent_info["err_msg"] == "env crash"
    summary = _read_summary(tmp_path)
    assert summary["err_msg"] == "env crash"
    assert summary["stack_trace"] == "env trace"
