import dataclasses
import gzip
import json
import pickle
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from browsergym.experiments.agent import AgentInfo
from browsergym.experiments.loop import (
    AbstractAgentArgs,
    EnvArgs,
    ExpArgs,
    ExpResult,
    StepInfo,
    get_exp_result,
    yield_all_exp_results,
)

GOAL_OBJECT = [
    {"type": "text", "text": "Find the red shoes."},
    {"type": "image_url", "image_url": "data:image/png;base64,AAAA"},
]


@dataclasses.dataclass
class DummyAgentArgs(AbstractAgentArgs):
    def make_agent(self):
        raise NotImplementedError


def _screenshot(value):
    return np.full((4, 6, 3), value, dtype=np.uint8)


def _write_exp_args(exp_dir: Path):
    exp_args = ExpArgs(
        agent_args=DummyAgentArgs(agent_name="dummy_agent"),
        env_args=EnvArgs(task_name="miniwob.click-test", task_seed=42),
    )
    exp_args.exp_dir = exp_dir
    with open(exp_dir / "exp_args.pkl", "wb") as f:
        pickle.dump(exp_args, f)


def _write_summary(exp_dir: Path, summary):
    with open(exp_dir / "summary_info.json", "w") as f:
        if summary is not None:
            json.dump(summary, f)


def _make_exp_dir(root: Path, name="exp", agent_info=None, save_som=True, summary="done"):
    """Write an experiment directory the same way ExpArgs.run does: step 0 and 1
    carry actions, step 2 is the final observation with no action."""
    exp_dir = root / name
    exp_dir.mkdir(parents=True)
    _write_exp_args(exp_dir)

    if agent_info is None:
        agent_info = {"think": "I should click the button.", "extra_info": {}}

    actions = ['click("a12")', 'fill("b3", "hello")\nclick("b4")', None]
    for i, action in enumerate(actions):
        step_info = StepInfo(
            step=i,
            obs={
                "goal_object": list(GOAL_OBJECT),
                "axtree_txt": f"[a12] button 'Submit' step {i}",
                "screenshot": _screenshot(10 * i),
                "screenshot_som": _screenshot(10 * i + 1),
            },
            reward=1.0 if i == 2 else 0.0,
            terminated=i == 2,
            truncated=False,
            action=action,
            agent_info=agent_info if action is not None else {},
            stats={"n_token": 3} if action is not None else None,
        )
        step_info.save_step_info(exp_dir, save_screenshot=True, save_som=save_som)

    if summary == "done":
        _write_summary(
            exp_dir,
            {
                "n_steps": 2,
                "cum_reward": 1.0,
                "err_msg": None,
                "terminated": True,
                "truncated": False,
            },
        )
    return exp_dir


# --- save_step_info / get_step_info round trip ---


def test_save_step_info_writes_goal_object_once_with_placeholder(tmp_path):
    exp_dir = _make_exp_dir(tmp_path)

    assert (exp_dir / "goal_object.pkl.gz").exists()
    with gzip.open(exp_dir / "goal_object.pkl.gz", "rb") as f:
        assert pickle.load(f) == GOAL_OBJECT

    for step in range(3):
        with gzip.open(exp_dir / f"step_{step}.pkl.gz", "rb") as f:
            raw = pickle.load(f)
        assert raw.obs["goal_object"] is None
        assert "screenshot" not in raw.obs
        assert "screenshot_som" not in raw.obs


def test_get_step_info_restores_screenshots_and_goal_object(tmp_path):
    exp_dir = _make_exp_dir(tmp_path)
    exp_result = ExpResult(exp_dir)

    step_info = exp_result.get_step_info(1)

    assert step_info.step == 1
    assert step_info.action == 'fill("b3", "hello")\nclick("b4")'
    assert step_info.obs["goal_object"] == GOAL_OBJECT
    np.testing.assert_array_equal(step_info.obs["screenshot"], _screenshot(10))
    np.testing.assert_array_equal(step_info.obs["screenshot_som"], _screenshot(11))
    assert step_info.obs["screenshot"].dtype == np.uint8
    # cached on second access
    assert exp_result.get_step_info(1) is step_info


def test_get_step_info_without_som_screenshot(tmp_path):
    exp_dir = _make_exp_dir(tmp_path, save_som=False)

    obs = ExpResult(exp_dir).get_step_info(0).obs

    assert "screenshot" in obs
    assert "screenshot_som" not in obs


def test_get_step_info_with_no_obs(tmp_path):
    exp_dir = tmp_path / "exp"
    exp_dir.mkdir()
    StepInfo(step=0, obs=None, action='click("a")').save_step_info(exp_dir)

    step_info = ExpResult(exp_dir).get_step_info(0)

    assert step_info.obs is None
    assert not (exp_dir / "goal_object.pkl.gz").exists()


def test_steps_info_loads_all_steps_in_order(tmp_path):
    exp_dir = _make_exp_dir(tmp_path)

    steps_info = ExpResult(exp_dir).steps_info

    assert [s.step for s in steps_info] == [0, 1, 2]
    assert all(s.obs["goal_object"] == GOAL_OBJECT for s in steps_info)


def test_steps_info_tolerates_missing_step_file(tmp_path):
    exp_dir = _make_exp_dir(tmp_path)
    (exp_dir / "step_1.pkl.gz").unlink()

    steps_info = ExpResult(exp_dir).steps_info

    assert [s.step for s in steps_info] == [0, 2]


# --- screenshots ---


def test_get_screenshot_falls_back_to_jpg(tmp_path):
    exp_dir = _make_exp_dir(tmp_path)
    png = exp_dir / "screenshot_step_0.png"
    Image.open(png).convert("RGB").save(exp_dir / "screenshot_step_0.jpg")
    png.unlink()

    img = ExpResult(exp_dir).get_screenshot(0)

    assert img.size == (6, 4)


def test_get_screenshot_missing_raises(tmp_path):
    exp_dir = _make_exp_dir(tmp_path)

    with pytest.raises(FileNotFoundError):
        ExpResult(exp_dir).get_screenshot(99)


def test_get_screenshots_and_som(tmp_path):
    exp_dir = _make_exp_dir(tmp_path)
    exp_result = ExpResult(exp_dir)

    screenshots = exp_result.screenshots
    screenshots_som = exp_result.screenshots_som

    assert len(screenshots) == 3
    assert len(screenshots_som) == 3
    for i in range(3):
        np.testing.assert_array_equal(np.array(screenshots[i]), _screenshot(10 * i))
        np.testing.assert_array_equal(np.array(screenshots_som[i]), _screenshot(10 * i + 1))


def test_get_screenshots_leaves_gaps_as_none(tmp_path):
    exp_dir = _make_exp_dir(tmp_path)
    (exp_dir / "screenshot_step_1.png").unlink()

    screenshots = ExpResult(exp_dir).screenshots

    assert screenshots[1] is None
    assert screenshots[0] is not None and screenshots[2] is not None


# --- tape export ---


def test_tape_builds_observation_thought_and_action_steps(tmp_path):
    exp_dir = _make_exp_dir(tmp_path)

    tape = ExpResult(exp_dir).tape

    kinds = [(s["kind"], s["metadata"]["step"]) for s in tape["steps"]]
    assert kinds == [
        ("browsergym_observation", 0),
        ("browsergym_thought", 0),
        ("browsergym_action", 0),
        ("browsergym_observation", 1),
        ("browsergym_thought", 1),
        ("browsergym_action", 1),
        ("browsergym_action", 1),
        ("browsergym_observation", 2),
    ]

    actions = [
        (s["name"], s["arguments"]) for s in tape["steps"] if s["kind"] == "browsergym_action"
    ]
    assert actions == [("click", ["a12"]), ("fill", ["b3", "hello"]), ("click", ["b4"])]

    obs_step = tape["steps"][0]
    assert obs_step["screenshot"] == str(exp_dir / "screenshot_step_0.png")
    assert obs_step["screenshot_som"] == str(exp_dir / "screenshot_som_step_0.png")
    assert "screenshot" not in obs_step["obs"]
    assert "screenshot_som" not in obs_step["obs"]
    assert obs_step["obs"]["goal_object"] == GOAL_OBJECT

    assert tape["steps"][1]["text"] == "I should click the button."
    assert tape["steps"][2]["metadata"]["stats"] == {"n_token": 3}

    assert tape["metadata"]["author"] == "browsergym_agent_[dummy_agent]"
    assert tape["metadata"]["result"]["env_args.task_name"] == "miniwob.click-test"
    assert tape["metadata"]["result"]["cum_reward"] == 1.0


def test_tape_reuses_existing_tape_segment(tmp_path):
    segment = [{"kind": "custom", "metadata": {"step": 0}}]
    exp_dir = _make_exp_dir(tmp_path, agent_info={"extra_info": {"tape_segment": segment}})

    tape = ExpResult(exp_dir).tape

    # steps 0 and 1 reuse the segment, the final step has no agent_info and is rebuilt
    assert tape["steps"][:2] == segment * 2
    assert tape["steps"][2]["kind"] == "browsergym_observation"


@pytest.mark.parametrize(
    "agent_info",
    [
        {"think": "t"},  # dict without extra_info
        AgentInfo(think="t"),  # AgentInfo with extra_info=None
    ],
    ids=["dict_without_extra_info", "agentinfo_extra_info_none"],
)
def test_tape_without_extra_info(tmp_path, agent_info):
    exp_dir = _make_exp_dir(tmp_path, agent_info=agent_info)

    tape = ExpResult(exp_dir).tape

    assert [s["kind"] for s in tape["steps"]].count("browsergym_action") == 3
    assert [s["kind"] for s in tape["steps"]].count("browsergym_thought") == 2


def test_save_tape(tmp_path):
    exp_dir = _make_exp_dir(tmp_path)
    exp_result = ExpResult(exp_dir)

    exp_result.save_tape()

    with open(exp_dir / "tape.json") as f:
        saved = json.load(f)
    assert len(saved["steps"]) == 8
    assert saved["metadata"]["author"] == "browsergym_agent_[dummy_agent]"
    assert saved["metadata"]["result"]["exp_dir"] == str(exp_dir)
    assert saved["steps"][0]["obs"]["goal_object"] == GOAL_OBJECT

    with pytest.raises(FileExistsError):
        exp_result.save_tape()


# --- summary / status ---


def test_summary_info_empty_file_raises(tmp_path):
    exp_dir = _make_exp_dir(tmp_path, summary=None)
    _write_summary(exp_dir, None)

    with pytest.raises(FileNotFoundError):
        ExpResult(exp_dir).summary_info


@pytest.mark.parametrize(
    "summary, expected",
    [
        ("missing", "incomplete"),
        ("empty", "incomplete"),
        ({"err_msg": "boom", "terminated": True}, "error"),
        ({"err_msg": None, "terminated": True, "truncated": False}, "done"),
        ({"err_msg": None, "terminated": False, "truncated": True}, "done"),
        ({"err_msg": None, "terminated": False, "truncated": False}, "incomplete"),
        ({}, "incomplete"),
    ],
    ids=["no_summary", "empty_summary", "err_msg", "terminated", "truncated", "neither", "no_keys"],
)
def test_status(tmp_path, summary, expected):
    exp_dir = _make_exp_dir(tmp_path, summary=None)
    if summary == "empty":
        _write_summary(exp_dir, None)
    elif summary != "missing":
        _write_summary(exp_dir, summary)

    assert ExpResult(exp_dir).status == expected


def test_get_exp_record_without_summary(tmp_path):
    exp_dir = _make_exp_dir(tmp_path, summary=None)

    record = ExpResult(exp_dir).get_exp_record()

    assert record["exp_dir"] == exp_dir
    assert record["env_args.task_name"] == "miniwob.click-test"
    assert "n_steps" not in record


# --- discovery ---


def test_yield_all_exp_results_skips_hidden_dirs(tmp_path):
    _make_exp_dir(tmp_path, "visible")
    _make_exp_dir(tmp_path / "nested", "also_visible")
    _make_exp_dir(tmp_path, "_hidden")
    _make_exp_dir(tmp_path, ".dot_hidden")

    names = {r.exp_dir.name for r in yield_all_exp_results(tmp_path, progress_fn=None)}
    assert names == {"visible", "also_visible"}

    names = {
        r.exp_dir.name
        for r in yield_all_exp_results(tmp_path, progress_fn=None, load_hidden=True)
    }
    assert names == {"visible", "also_visible", "_hidden", ".dot_hidden"}


def test_yield_all_exp_results_accepts_list_of_dirs(tmp_path):
    _make_exp_dir(tmp_path / "a", "exp_a")
    _make_exp_dir(tmp_path / "b", "exp_b")

    results = yield_all_exp_results([tmp_path / "a", tmp_path / "b"], progress_fn=None)

    assert {r.exp_dir.name for r in results} == {"exp_a", "exp_b"}


def test_yield_all_exp_results_cache(tmp_path):
    exp_dir = _make_exp_dir(tmp_path)

    (cached,) = yield_all_exp_results(tmp_path, progress_fn=None)
    assert cached is get_exp_result(exp_dir)

    (uncached,) = yield_all_exp_results(tmp_path, progress_fn=None, use_cache=False)
    assert uncached is not cached
    assert uncached.exp_dir == exp_dir


def test_exp_args_exp_dir_follows_moved_directory(tmp_path):
    exp_dir = _make_exp_dir(tmp_path, "original")
    moved = exp_dir.rename(tmp_path / "moved")

    assert ExpResult(moved).exp_args.exp_dir == moved
