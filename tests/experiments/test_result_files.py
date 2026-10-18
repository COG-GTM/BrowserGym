import dataclasses
import gzip
import json
import os
import pickle

import pytest

from browsergym.experiments.loop import (
    AbstractAgentArgs,
    CorruptedResultFileError,
    EnvArgs,
    ExpArgs,
    ExpResult,
    StepInfo,
    _atomic_open,
)


@dataclasses.dataclass
class DummyAgentArgs(AbstractAgentArgs):
    def make_agent(self):
        raise NotImplementedError


def _exp_args(exp_dir):
    return ExpArgs(
        agent_args=DummyAgentArgs(agent_name="dummy"),
        env_args=EnvArgs(task_name="miniwob.click-test", task_seed=42),
        exp_dir=exp_dir,
    )


def _save_episode(exp_dir):
    steps = []
    for i in range(2):
        step = StepInfo(step=i, obs={"goal_object": [{"type": "text", "text": "goal"}]})
        step.agent_info = {}
        step.terminated = i == 1
        step.truncated = False
        step.save_step_info(exp_dir)
        steps.append(step)
    _exp_args(exp_dir).save_summary_info(steps, exp_dir, None, None)


def _leftover_tmp_files(exp_dir):
    return [p.name for p in exp_dir.iterdir() if p.name.endswith(".tmp")]


def test_result_files_roundtrip_without_tmp_leftovers(tmp_path):
    _save_episode(tmp_path)

    assert _leftover_tmp_files(tmp_path) == []
    result = ExpResult(tmp_path)
    assert result.status == "done"
    assert result.summary_info["n_steps"] == 1
    assert result.get_step_info(1).obs["goal_object"] == [{"type": "text", "text": "goal"}]
    assert len(result.steps_info) == 2


@pytest.mark.parametrize("keep_bytes", [0, 1, 10])
def test_truncated_summary_info_is_treated_as_missing(tmp_path, keep_bytes):
    _save_episode(tmp_path)
    summary_file = tmp_path / "summary_info.json"
    summary_file.write_bytes(summary_file.read_bytes()[:keep_bytes])

    result = ExpResult(tmp_path)
    with pytest.raises(CorruptedResultFileError):
        result.summary_info
    assert result.status == "incomplete"
    record = result.get_exp_record()
    assert record["exp_dir"] == tmp_path
    assert "n_steps" not in record


@pytest.mark.parametrize("file_name", ["step_1.pkl.gz", "goal_object.pkl.gz"])
def test_truncated_step_pickles_raise_corrupted_error(tmp_path, file_name):
    _save_episode(tmp_path)
    target = tmp_path / file_name
    target.write_bytes(target.read_bytes()[:20])

    with pytest.raises(CorruptedResultFileError) as exc_info:
        ExpResult(tmp_path).get_step_info(1)
    assert isinstance(exc_info.value, FileNotFoundError)
    assert file_name in str(exc_info.value)


def test_failed_write_keeps_previous_file_and_cleans_up(tmp_path):
    target = tmp_path / "summary_info.json"
    target.write_text(json.dumps({"n_steps": 3}))

    with pytest.raises(RuntimeError):
        with _atomic_open(target, "w") as f:
            f.write('{"n_steps": ')
            raise RuntimeError("interrupted")

    assert json.loads(target.read_text()) == {"n_steps": 3}
    assert _leftover_tmp_files(tmp_path) == []


def test_unpicklable_step_does_not_leave_partial_files(tmp_path):
    step = StepInfo(step=0, obs={"goal_object": [{"type": "text", "text": "goal"}]})
    step.agent_info = {"callback": lambda: None}

    with pytest.raises((pickle.PicklingError, AttributeError)):
        step.save_step_info(tmp_path)

    assert not (tmp_path / "step_0.pkl.gz").exists()
    with gzip.open(tmp_path / "goal_object.pkl.gz", "rb") as f:
        assert pickle.load(f) == [{"type": "text", "text": "goal"}]
    assert _leftover_tmp_files(tmp_path) == []


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires os.fork")
def test_process_killed_mid_write_never_exposes_partial_file(tmp_path):
    _save_episode(tmp_path)
    (tmp_path / "summary_info.json").unlink()
    (tmp_path / "goal_object.pkl.gz").unlink()

    pid = os.fork()
    if pid == 0:
        try:
            with _atomic_open(tmp_path / "summary_info.json", "w") as f:
                f.write('{"n_steps": 1, "cum_reward": ')
                f.flush()
                os._exit(0)
        finally:
            os._exit(1)
    os.waitpid(pid, 0)

    assert not (tmp_path / "summary_info.json").exists()
    result = ExpResult(tmp_path)
    assert result.status == "incomplete"
    # a fresh run rewrites goal_object since no (partial) file was left at the final path
    step = StepInfo(step=0, obs={"goal_object": [{"type": "text", "text": "goal"}]})
    step.save_step_info(tmp_path)
    assert result.get_step_info(1).obs["goal_object"] == [{"type": "text", "text": "goal"}]
