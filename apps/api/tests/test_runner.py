from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

from side_api.config import Settings
from side_api.db import RunRecord
from side_api.fake_runner import main as fake_runner_main
from side_api.runners import runner_command


def _record(**kw) -> RunRecord:
    base = dict(
        id="abc123",
        task_id="browsergym/openended",
        goal="Find the docs",
        start_url="https://example.com",
        agent_json=json.dumps({"type": "mock", "model": None}),
        status="queued",
        max_steps=7,
        headless=True,
        created_at="2026-01-01T00:00:00.000Z",
    )
    return RunRecord(**(base | kw))


def test_default_runner_command_follows_contract(tmp_path):
    cmd = runner_command(Settings(data_dir=tmp_path), _record())
    assert cmd[:3] == [sys.executable, "-m", "side_runner"]
    assert cmd[3:] == [
        "--run-id", "abc123",
        "--task", "browsergym/openended",
        "--agent-json", '{"type": "mock", "model": null}',
        "--max-steps", "7",
        "--data-dir", str(tmp_path.resolve()),
        "--goal", "Find the docs",
        "--start-url", "https://example.com",
        "--headless",
    ]  # fmt: skip


def test_runner_cmd_override_and_optional_args(tmp_path):
    settings = Settings(data_dir=tmp_path, runner_cmd="uv run --directory services/runner side-run")
    cmd = runner_command(settings, _record(goal=None, start_url=None, headless=False))
    assert cmd[:5] == ["uv", "run", "--directory", "services/runner", "side-run"]
    assert "--goal" not in cmd and "--start-url" not in cmd
    assert cmd[-1] == "--no-headless"


def test_subprocess_runner_via_side_runner_cmd(make_api, settings):
    """SIDE_RUNNER_CMD path: the API spawns a real process speaking the runner contract."""
    settings.fake_runner = False
    settings.runner_cmd = f"{shlex.quote(sys.executable)} -m side_api.fake_runner --step-delay 0.05"
    api = make_api(settings)
    run = api.create_run(goal="Subprocess goal")
    done = api.wait_for(run["id"])
    assert done["status"] == "succeeded" and done["n_steps"] == 4
    chat = api.get(f"/runs/{run['id']}/chat").json()
    assert chat[-1]["message"] == "Done: Subprocess goal"


def test_missing_runner_executable_fails_run(make_api, settings):
    settings.fake_runner = False
    settings.runner_cmd = "/definitely/not/a/runner"
    api = make_api(settings)
    done = api.wait_for(api.create_run()["id"])
    assert done["status"] == "failed"
    assert "failed to start runner" in done["error"]


def test_default_runner_not_installed_fails_cleanly(make_api, settings):
    settings.fake_runner = False
    api = make_api(settings)
    done = api.wait_for(api.create_run()["id"])
    assert done["status"] == "failed"
    assert "runner exited with code" in done["error"]


def test_fake_runner_cli(tmp_path):
    rc = fake_runner_main(
        [
            "--run-id", "cli1", "--task", "browsergym/miniwob.click-test",
            "--agent-json", '{"type": "mock"}', "--max-steps", "3",
            "--data-dir", str(tmp_path), "--step-delay", "0",
        ]
    )  # fmt: skip
    assert rc == 0
    root = Path(tmp_path, "runs", "cli1")
    run = json.loads((root / "run.json").read_text())
    assert run["status"] == "succeeded" and run["n_steps"] == 3
    assert (root / "steps" / "3.png").read_bytes().startswith(b"\x89PNG")
