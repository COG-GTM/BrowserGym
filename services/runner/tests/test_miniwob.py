import os

import pytest

from side_runner.runner import RunConfig, run_episode

from conftest import validate_run_dir

pytestmark = [
    pytest.mark.browser,
    pytest.mark.miniwob,
    pytest.mark.skipif(
        not os.environ.get("MINIWOB_URL"), reason="MINIWOB_URL not set (make setup-miniwob)"
    ),
]


def _run(tmp_path, agent, task="browsergym/miniwob.click-test", max_steps=3):
    cfg = RunConfig(
        run_id="mw", task=task, agent=agent, max_steps=max_steps, data_dir=str(tmp_path), seed=0
    )
    return run_episode(cfg), validate_run_dir(tmp_path / "runs" / "mw")


def test_miniwob_click_test_scripted_success(tmp_path):
    status, art = _run(tmp_path, {"type": "scripted", "actions": ["click('13')"]})
    assert status == "succeeded"
    assert art["run"]["reward"] == 1.0 and art["run"]["goal"] == "Click the button."
    assert art["steps"][1]["terminated"] is True and art["steps"][1]["reward"] == 1.0


def test_miniwob_mock_agent(tmp_path):
    status, art = _run(tmp_path, {"type": "mock"}, max_steps=5)
    assert status == "succeeded"
    assert art["run"]["n_steps"] >= 1 and art["run"]["reward"] in (0.0, -1.0, 1.0)
