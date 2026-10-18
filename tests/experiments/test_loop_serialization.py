import gzip
import logging
import pickle
import os
import shutil
from dataclasses import fields
from pathlib import Path

import numpy as np
import pytest

from browsergym.experiments import loop as exp_loop
from browsergym.experiments import utils as exp_utils
from browsergym.experiments.agent import AgentInfo
from browsergym.experiments.loop import (
    EnvArgs,
    ExpArgs,
    ExperimentLoadError,
    ExperimentSaveError,
    ExpResult,
    StepInfo,
    StepTimestamps,
)

from .legacy_fixtures import LEGACY_EXP_DIR, LegacyNoopAgentArgs


@pytest.fixture
def legacy_exp_dir(tmp_path: Path) -> Path:
    exp_dir = tmp_path / "legacy_exp"
    shutil.copytree(LEGACY_EXP_DIR, exp_dir)
    return exp_dir


def _load_step(path: Path) -> StepInfo:
    with gzip.open(path, "rb") as f:
        return pickle.load(f)


def test_load_legacy_step_info_pickle():
    """A StepInfo pickled by the pre-modernization code still loads with all its fields."""
    step_info = _load_step(LEGACY_EXP_DIR / "step_0.pkl.gz")

    assert isinstance(step_info, StepInfo)
    assert step_info.step == 0
    assert step_info.action == 'send_msg_to_user("hi")'
    assert step_info.reward == 0.0
    assert step_info.terminated is False
    assert step_info.stats == {"n_token_goal": 2, "step_elapsed": 0.5, "agent_elapsed": 0.25}
    assert step_info.task_info == {"step": 0}
    assert isinstance(step_info.profiling, StepTimestamps)
    assert step_info.profiling.env_start == 1.0
    assert isinstance(step_info.agent_info, AgentInfo)
    assert step_info.agent_info.think == "say hi"
    # screenshot is saved separately, goal_object is replaced by a placeholder
    assert "screenshot" not in step_info.obs
    assert step_info.obs["goal_object"] is None
    assert step_info.is_done is False


def test_legacy_exp_result(legacy_exp_dir: Path):
    exp_result = ExpResult(legacy_exp_dir)

    assert isinstance(exp_result.exp_args, ExpArgs)
    assert isinstance(exp_result.exp_args.agent_args, LegacyNoopAgentArgs)
    assert exp_result.exp_args.env_args == EnvArgs(task_name="openended", task_seed=7, max_steps=3)
    assert exp_result.exp_args.exp_dir == legacy_exp_dir

    steps = exp_result.steps_info
    assert [s.step for s in steps] == [0, 1]
    assert steps[1].terminated is True
    for step in steps:
        assert step.obs["goal_object"] == [{"type": "text", "text": "say hi"}]
        assert step.obs["screenshot"].shape == (4, 4, 3)
        assert step.obs["screenshot"][0, 0].tolist() == [255, 0, 0]

    assert exp_result.status == "done"
    record = exp_result.get_exp_record()
    assert record["env_args.task_name"] == "openended"
    assert record["n_steps"] == 1
    assert record["cum_reward"] == 1.0
    assert len(exp_result.screenshots) == 2

    exp_result.save_tape()
    assert (legacy_exp_dir / "tape.json").exists()
    with pytest.raises(FileExistsError):
        exp_result.save_tape()


def test_step_info_pickle_format_unchanged(tmp_path: Path):
    """Step files written by the current code have the same pickled state as legacy ones."""
    legacy = _load_step(LEGACY_EXP_DIR / "step_0.pkl.gz")

    step_info = StepInfo(step=0, obs={"goal": "say hi"}, action="noop()")
    step_info.agent_info = AgentInfo(think="t")
    step_info.save_step_info(tmp_path)
    reloaded = _load_step(tmp_path / "step_0.pkl.gz")

    assert set(vars(reloaded)) == set(vars(legacy)) == {f.name for f in fields(StepInfo)}
    assert set(vars(reloaded.profiling)) == set(vars(legacy.profiling))
    assert reloaded.obs == {"goal": "say hi"}
    assert reloaded.action == "noop()"
    assert reloaded.agent_info == AgentInfo(think="t")
    # the gzip header keeps the final file name, not the temporary one
    with open(tmp_path / "step_0.pkl.gz", "rb") as f:
        header = f.read(64)
    assert b"step_0.pkl\x00" in header


def test_unpickle_fills_fields_missing_from_old_versions():
    step_info = StepInfo(step=3)
    state = dict(vars(step_info))
    del state["profiling"], state["task_info"]

    restored = StepInfo.__new__(StepInfo)
    restored.__setstate__(state)

    assert restored.step == 3
    assert restored.task_info is None
    assert isinstance(restored.profiling, StepTimestamps)


def test_save_step_info_writes_screenshots_and_restores_obs(tmp_path: Path):
    screenshot = np.full((2, 3, 3), 7, dtype=np.uint8)
    goal_object = [{"type": "text", "text": "g"}]
    step_info = StepInfo(step=1, obs={"screenshot": screenshot, "goal_object": goal_object})

    step_info.save_step_info(tmp_path, save_json=True)

    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "goal_object.pkl.gz",
        "screenshot_step_1.png",
        "step_1.pkl.gz",
        "steps_info.json",
    ]
    # in-memory observation is left intact
    assert step_info.obs["screenshot"] is screenshot
    assert step_info.obs["goal_object"] is goal_object
    # saved step has screenshot stripped and goal_object placeholder
    saved = _load_step(tmp_path / "step_1.pkl.gz")
    assert saved.obs == {"goal_object": None}
    loaded = ExpResult(tmp_path).get_step_info(1)
    assert loaded.obs["goal_object"] == goal_object
    assert np.array_equal(loaded.obs["screenshot"], screenshot)


def test_save_step_info_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    screenshot = np.zeros((2, 2, 3), dtype=np.uint8)
    step_info = StepInfo(step=0, obs={"screenshot": screenshot, "goal": "g"}, action="noop()")
    step_info.save_step_info(tmp_path)
    original = (tmp_path / "step_0.pkl.gz").read_bytes()
    original_png = (tmp_path / "screenshot_step_0.png").read_bytes()

    def broken_dump(*args, **kwargs):
        raise RuntimeError("disk on fire")

    step_info.action = "click('a')"
    screenshot = np.full((2, 2, 3), 255, dtype=np.uint8)
    step_info.obs["screenshot"] = screenshot
    monkeypatch.setattr(pickle, "dump", broken_dump)
    with pytest.raises(ExperimentSaveError) as exc_info:
        step_info.save_step_info(tmp_path)
    monkeypatch.undo()

    msg = str(exc_info.value)
    assert "Could not save step 0" in msg
    assert "step_0.pkl.gz" in msg
    assert "RuntimeError: disk on fire" in msg
    # previous version untouched (step file and its screenshot), no temporary files left, obs restored
    assert (tmp_path / "step_0.pkl.gz").read_bytes() == original
    assert (tmp_path / "screenshot_step_0.png").read_bytes() == original_png
    assert not list(tmp_path.glob(".*.tmp"))
    assert step_info.obs["screenshot"] is screenshot


def test_save_step_info_missing_dir(tmp_path: Path):
    missing = tmp_path / "does" / "not" / "exist"
    with pytest.raises(ExperimentSaveError, match="does not exist"):
        StepInfo(step=0, obs={}).save_step_info(missing)


def test_saved_files_are_not_owner_only(tmp_path: Path):
    StepInfo(step=0, obs={}).save_step_info(tmp_path)
    assert (tmp_path / "step_0.pkl.gz").stat().st_mode & 0o044  # group/other readable (umask 022)


def test_saved_files_follow_current_umask(tmp_path: Path):
    old_umask = os.umask(0o077)
    try:
        StepInfo(step=0, obs={}).save_step_info(tmp_path)
    finally:
        os.umask(old_umask)
    assert (tmp_path / "step_0.pkl.gz").stat().st_mode & 0o777 == 0o600


def test_temp_file_creation_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def no_space(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(exp_loop.os, "open", no_space)
    with pytest.raises(ExperimentSaveError) as exc_info:
        StepInfo(step=3, obs={}).save_step_info(tmp_path)
    monkeypatch.undo()

    msg = str(exc_info.value)
    assert "Could not save step 3" in msg
    assert "No space left on device" in msg
    assert not list(tmp_path.iterdir())


def test_corrupted_step_file_error(tmp_path: Path):
    (tmp_path / "step_0.pkl.gz").write_bytes(b"\x1f\x8b\x08\x00garbage")
    with pytest.raises(ExperimentLoadError, match="corrupted or truncated"):
        ExpResult(tmp_path).get_step_info(0)


def test_summary_info_written_atomically(tmp_path: Path):
    exp_args = ExpArgs(agent_args=LegacyNoopAgentArgs(), env_args=EnvArgs(task_name="openended"))
    steps = [StepInfo(step=0, terminated=False, truncated=False)]
    steps.append(StepInfo(step=1, reward=1.0, terminated=True, truncated=False))
    exp_args.save_summary_info(steps, tmp_path, None, None)

    summary = ExpResult(tmp_path).summary_info
    assert summary["n_steps"] == 1
    assert summary["cum_reward"] == 1.0
    assert summary["terminated"] is True
    assert [p.name for p in tmp_path.iterdir()] == ["summary_info.json"]


def test_error_message_recorded_on_agent_info(tmp_path: Path):
    """Error messages can be attached to AgentInfo objects (used to raise TypeError)."""
    exp_args = ExpArgs(agent_args=LegacyNoopAgentArgs(), env_args=EnvArgs(task_name="openended"))
    steps = [StepInfo(step=0, agent_info=AgentInfo())]
    exp_args.save_summary_info(steps, tmp_path, "boom", "trace")
    assert steps[0].agent_info["err_msg"] == "boom"
    assert ExpResult(tmp_path).status == "error"


def test_env_args_json_round_trip():
    env_args = EnvArgs(task_name="openended", task_seed=3, viewport={"width": 10, "height": 20})
    assert EnvArgs.from_json(env_args.to_json()) == env_args


@pytest.fixture
def clean_encoding_cache():
    exp_utils._encodings.clear()
    exp_utils._encoding_failures.clear()
    yield
    exp_utils._encodings.clear()
    exp_utils._encoding_failures.clear()


def test_count_tokens_offline_fallback(
    monkeypatch: pytest.MonkeyPatch, caplog, clean_encoding_cache
):
    def no_network(model):
        raise ConnectionError("offline")

    monkeypatch.setattr(exp_utils.tiktoken, "encoding_for_model", no_network)
    with caplog.at_level(logging.WARNING, logger=exp_utils.__name__):
        assert exp_utils.count_tokens("abcdefghi", model="fake-model") == 3
        assert exp_utils.count_messages_token(["abcd", {"content": "abcd"}], "fake-model") == 2
    assert sum("approximated" in r.getMessage() for r in caplog.records) == 1


def test_count_tokens_recovers_after_transient_failure(
    monkeypatch: pytest.MonkeyPatch, clean_encoding_cache
):
    class FakeEncoding:
        def encode(self, text):
            return list(text)

    calls = []

    def flaky(model):
        calls.append(model)
        if len(calls) == 1:
            raise ConnectionError("offline")
        return FakeEncoding()

    monkeypatch.setattr(exp_utils.tiktoken, "encoding_for_model", flaky)
    assert exp_utils.count_tokens("abcdefghi", model="fake-model") == 3  # approximation
    assert exp_utils.count_tokens("abcdefghi", model="fake-model") == 3  # within retry delay
    assert len(calls) == 1

    monkeypatch.setattr(exp_utils, "ENCODING_RETRY_DELAY", 0.0)
    assert exp_utils.count_tokens("abcdefghi", model="fake-model") == 9  # tokenizer loaded
    assert exp_utils.count_tokens("abcdefghi", model="fake-model") == 9  # cached
    assert len(calls) == 2
