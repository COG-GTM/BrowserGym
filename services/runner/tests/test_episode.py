"""End-to-end episodes in a real headless Chromium against a local static page."""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

from side_runner.agents import _REGISTRY
from side_runner.agents.openai_agent import OpenAIAgent
from side_runner.runner import EpisodeRunner, RunConfig, run_episode

from conftest import SITE_DIR, read_jsonl, validate_run_dir

pytestmark = pytest.mark.browser
OPENENDED = "browsergym/openended"


def _cfg(tmp_path, url, run_id="r1", agent=None, max_steps=10, **kw):
    return RunConfig(
        run_id=run_id,
        task=OPENENDED,
        agent=agent or {"type": "mock"},
        max_steps=max_steps,
        data_dir=str(tmp_path),
        goal=kw.pop("goal", "Look at the page and say done"),
        start_url=url,
        slow_mo=kw.pop("slow_mo", 0),
        **kw,
    )


def test_mock_episode_writes_valid_artifacts(tmp_path, site_url):
    assert run_episode(_cfg(tmp_path, site_url)) == "succeeded"
    run_dir = tmp_path / "runs" / "r1"
    art = validate_run_dir(run_dir)
    run, steps, chat, events = art["run"], art["steps"], art["chat"], art["events"]

    assert run["status"] == "succeeded" and run["error"] is None
    assert run["n_steps"] == 3 and run["max_steps"] == 10 and run["agent"]["type"] == "mock"
    assert run["started_at"] and run["finished_at"] and run["reward"] == 0.0

    assert [s["action"] for s in steps] == [
        None,
        "noop(200)",
        "scroll(0, 200)",
        "send_msg_to_user('done')",
    ]
    for s in steps:
        assert s["url"] == site_url
        assert s["elapsed_ms"] > 0
        assert "button 'Go'" in s["axtree_txt"] and 'id="go"' in s["pruned_html"]
        png = run_dir / "steps" / f"{s['index']}.png"
        assert Image.open(png).format == "PNG" and Image.open(png).size == (1280, 720)
        assert s["screenshot_url"] == f"/runs/r1/steps/{s['index']}/screenshot"
    assert not any(s["truncated"] for s in steps)

    assert [(m["role"], m["message"]) for m in chat][1:] == [
        ("user", "Look at the page and say done"),
        ("assistant", "done"),
    ]

    statuses = [e["status"] for e in events if e["type"] == "status"]
    assert statuses == ["queued", "running", "succeeded"]
    assert [e["step"]["index"] for e in events if e["type"] == "step"] == [0, 1, 2, 3]
    assert len([e for e in events if e["type"] == "chat"]) == len(chat)
    assert events[-1]["type"] == "status"
    assert not list(run_dir.rglob(".*.tmp"))


def test_inbox_messages_are_echoed_and_answered(tmp_path, site_url):
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "inbox.jsonl").write_text(
        json.dumps({"role": "user", "message": "hello agent", "timestamp": "2026-01-01T00:00:00Z"})
        + "\n"
    )
    assert run_episode(_cfg(tmp_path, site_url)) == "succeeded"
    art = validate_run_dir(run_dir)
    msgs = [(m["role"], m["message"]) for m in art["chat"]]
    assert ("user", "hello agent") in msgs
    assert msgs.index(("user", "hello agent")) < msgs.index(("assistant", "Received: hello agent"))
    assert art["steps"][1]["action"] == "send_msg_to_user('Received: hello agent')"


def test_user_exit_message_terminates_openended(tmp_path, site_url):
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "inbox.jsonl").write_text(json.dumps({"role": "user", "message": "exit"}) + "\n")
    assert run_episode(_cfg(tmp_path, site_url)) == "succeeded"
    art = validate_run_dir(run_dir)
    assert art["run"]["n_steps"] == 1 and art["steps"][1]["terminated"] is True


def test_existing_run_json_is_reused(tmp_path, site_url):
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    created = "2025-01-01T00:00:00Z"
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "id": "r1",
                "task_id": OPENENDED,
                "agent": {"type": "mock"},
                "status": "queued",
                "n_steps": 0,
                "created_at": created,
            }
        )
    )
    run_episode(_cfg(tmp_path, site_url, max_steps=1))
    art = validate_run_dir(run_dir)
    assert art["run"]["created_at"] == created
    assert [e["status"] for e in art["events"] if e["type"] == "status"] == ["running", "succeeded"]


def test_max_steps_truncates(tmp_path, site_url):
    assert run_episode(_cfg(tmp_path, site_url, max_steps=2)) == "succeeded"
    art = validate_run_dir(tmp_path / "runs" / "r1")
    assert art["run"]["n_steps"] == 2
    assert [s["truncated"] for s in art["steps"]] == [False, False, True]


def test_scripted_agent_and_action_errors(tmp_path, site_url):
    agent = {
        "type": "scripted",
        "actions": ["fill('11', 'hello side')", "click('12')", "click('does-not-exist')"],
    }
    assert run_episode(_cfg(tmp_path, site_url, agent=agent, timeout=1000)) == "succeeded"
    art = validate_run_dir(tmp_path / "runs" / "r1")
    steps = art["steps"]
    assert art["run"]["n_steps"] == 3
    assert steps[1]["last_action_error"] is None
    assert "Searched: hello side" in steps[2]["axtree_txt"]
    assert steps[3]["last_action_error"]


def test_agent_failure_marks_run_failed(tmp_path, site_url):
    status = run_episode(_cfg(tmp_path, site_url, agent={"type": "mock", "fail_at_step": 2}))
    assert status == "failed"
    art = validate_run_dir(tmp_path / "runs" / "r1")
    assert art["run"]["status"] == "failed" and art["run"]["n_steps"] == 1
    assert art["run"]["error"] == "RuntimeError: mock agent failure requested at step 2"
    assert any(e["type"] == "log" and "Traceback" in e["log"] for e in art["events"])
    assert art["chat"][-1]["role"] == "info" and "failed" in art["chat"][-1]["message"]


def test_bad_config_fails_before_browser(tmp_path):
    status = run_episode(_cfg(tmp_path, None))  # openended without start_url
    assert status == "failed"
    art = validate_run_dir(tmp_path / "runs" / "r1")
    assert "start-url" in art["run"]["error"]


def test_cancel_before_start(tmp_path, site_url):
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "CANCEL").touch()
    assert run_episode(_cfg(tmp_path, site_url)) == "cancelled"
    art = validate_run_dir(run_dir)
    assert art["run"]["n_steps"] == 0 and not list((run_dir / "steps").iterdir())
    assert [e["status"] for e in art["events"] if e["type"] == "status"] == ["queued", "cancelled"]


def test_cancel_mid_run(tmp_path, site_url):
    run_dir = tmp_path / "runs" / "r1"

    def cancel_after_first_action():
        deadline = time.time() + 60
        while time.time() < deadline:
            if (run_dir / "steps" / "1.json").exists():
                (run_dir / "CANCEL").touch()
                return
            time.sleep(0.05)

    t = threading.Thread(target=cancel_after_first_action)
    t.start()
    status = run_episode(
        _cfg(tmp_path, site_url, agent={"type": "mock", "delay_ms": 300}, max_steps=20)
    )
    t.join()
    assert status == "cancelled"
    art = validate_run_dir(run_dir)
    assert art["run"]["status"] == "cancelled" and art["run"]["finished_at"]
    assert 1 <= art["run"]["n_steps"] < 3
    assert art["chat"][-1] == {**art["chat"][-1], "role": "info", "message": "Run cancelled."}


def test_cli_end_to_end_file_url(tmp_path):
    url = (SITE_DIR / "index.html").resolve().as_uri()
    cmd = [
        sys.executable,
        "-m",
        "side_runner",
        "--run-id",
        "cli1",
        "--task",
        OPENENDED,
        "--agent-json",
        json.dumps({"type": "mock"}),
        "--max-steps",
        "5",
        "--data-dir",
        str(tmp_path),
        "--goal",
        "Say done",
        "--start-url",
        url,
        "--headless",
        "--slow-mo",
        "0",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == {
        "run_id": "cli1",
        "status": "succeeded",
    }
    art = validate_run_dir(tmp_path / "runs" / "cli1")
    assert art["run"]["n_steps"] == 3 and art["steps"][0]["url"] == url


def test_cli_rejects_bad_agent_json(tmp_path):
    cmd = [
        sys.executable,
        "-m",
        "side_runner",
        "--run-id",
        "x",
        "--task",
        OPENENDED,
        "--agent-json",
        "{not json",
        "--max-steps",
        "1",
        "--data-dir",
        str(tmp_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2 and "agent-json" in proc.stderr


class _FlakyLLM(OpenAIAgent):
    """First answers with a broken terminal action, then a valid one."""

    answers = ["```send_msg_to_user()```", "```send_msg_to_user('ok')```"]

    def complete(self, system, content):
        return self.answers[len(self.history)]

    def close(self):
        raise RuntimeError("close failed")


def test_failed_terminal_action_continues_and_close_errors_are_contained(
    tmp_path, site_url, monkeypatch
):
    monkeypatch.setitem(_REGISTRY, "openai", lambda cfg: _FlakyLLM(cfg, client=object()))
    agent = {"type": "openai"}
    assert run_episode(_cfg(tmp_path, site_url, agent=agent)) == "succeeded"
    art = validate_run_dir(tmp_path / "runs" / "r1")
    assert art["run"]["n_steps"] == 2
    assert art["steps"][1]["last_action_error"] and not art["steps"][2]["last_action_error"]
    assert ("assistant", "ok") in [(m["role"], m["message"]) for m in art["chat"]]


def test_cli_rejects_path_like_run_id(tmp_path):
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "side_runner",
            "--run-id",
            "../evil",
            "--task",
            OPENENDED,
            "--agent-json",
            '{"type":"mock"}',
            "--data-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2 and "invalid run id" in proc.stderr
    assert not (tmp_path / "evil").exists() and not (tmp_path.parent / "evil").exists()


@pytest.mark.parametrize(
    "agent,max_steps,cancel,expected",
    [
        ({"type": "scripted", "actions": ["noop(300)"] * 3}, 10, False, "succeeded"),
        ({"type": "mock"}, 3, False, "succeeded"),  # max-steps truncation
        ({"type": "mock", "fail_at_step": 3}, 10, False, "failed"),
        ({"type": "mock", "delay_ms": 100}, 50, True, "cancelled"),
    ],
    ids=["success", "max-steps", "failure", "cancel"],
)
def test_inbox_flood_reaches_chat_on_every_exit_path(
    tmp_path, site_url, monkeypatch, agent, max_steps, cancel, expected
):
    """A chat message every 50 ms: nothing written before the runner finishes may be lost."""
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    inbox = run_dir / "inbox.jsonl"
    lock, finishing, written = threading.Lock(), threading.Event(), []

    original_flush = EpisodeRunner._flush_inbox

    def flush(self):
        with lock:  # every message appended before the final inbox read must survive
            finishing.set()
        original_flush(self)

    monkeypatch.setattr(EpisodeRunner, "_flush_inbox", flush)

    def flood():
        deadline = time.time() + 60
        while time.time() < deadline:
            with lock:
                if finishing.is_set():
                    return
                msg = f"flood-{len(written)}"
                with open(inbox, "a") as f:
                    f.write(json.dumps({"role": "user", "message": msg}) + "\n")
                written.append(msg)
            if cancel and (run_dir / "steps" / "2.json").exists():
                (run_dir / "CANCEL").touch()
            time.sleep(0.05)

    t = threading.Thread(target=flood)
    t.start()
    status = run_episode(_cfg(tmp_path, site_url, agent=agent, max_steps=max_steps))
    t.join()
    assert status == expected
    art = validate_run_dir(run_dir)
    chat_users = [
        m["message"]
        for m in art["chat"]
        if m["role"] == "user" and m["message"].startswith("flood-")
    ]
    assert len(written) >= 5 and chat_users == written
