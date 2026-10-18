"""Launching runner processes per the runner contract (docs/side/ARCHITECTURE.md)."""

from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
import sys
import threading
from pathlib import Path
from typing import Protocol

from .config import Settings
from .db import RunRecord
from .fake_runner import FakeEpisode

log = logging.getLogger(__name__)


class RunHandle(Protocol):
    pid: int | None

    def is_alive(self) -> bool: ...

    def exit_code(self) -> int | None: ...

    def terminate(self) -> None: ...


class SubprocessHandle:
    def __init__(self, proc: subprocess.Popen):
        self.proc = proc
        self.pid: int | None = proc.pid

    def is_alive(self) -> bool:
        return self.proc.poll() is None

    def exit_code(self) -> int | None:
        return self.proc.poll()

    def terminate(self) -> None:
        if self.is_alive():
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


class ThreadHandle:
    """In-process FakeRunner."""

    pid: int | None = None

    def __init__(self, episode: FakeEpisode):
        self.episode = episode
        self.thread = threading.Thread(
            target=episode.run_episode, name=f"fake-runner-{episode.run_id}", daemon=True
        )
        self.thread.start()

    def is_alive(self) -> bool:
        return self.thread.is_alive()

    def exit_code(self) -> int | None:
        return None if self.is_alive() else 0

    def terminate(self) -> None:
        self.episode.stop_event.set()
        self.thread.join(timeout=5)


def runner_args(record: RunRecord, data_dir: Path) -> list[str]:
    args = [
        "--run-id",
        record.id,
        "--task",
        record.task_id,
        "--agent-json",
        record.agent_json,
        "--max-steps",
        str(record.max_steps),
        "--data-dir",
        str(data_dir.resolve()),
    ]
    if record.goal:
        args += ["--goal", record.goal]
    if record.start_url:
        args += ["--start-url", record.start_url]
    args.append("--headless" if record.headless else "--no-headless")
    return args


def runner_command(settings: Settings, record: RunRecord) -> list[str]:
    base = (
        shlex.split(settings.runner_cmd)
        if settings.runner_cmd
        else [sys.executable, "-m", "side_runner"]
    )
    return base + runner_args(record, settings.data_dir)


def spawn(settings: Settings, record: RunRecord, log_path: Path) -> RunHandle:
    """Start the runner for ``record``. Raises OSError if the process cannot be started."""
    if settings.fake_runner and not settings.runner_cmd:
        episode = FakeEpisode(
            settings.data_dir,
            record.id,
            record.task_id,
            json.loads(record.agent_json),
            record.max_steps,
            goal=record.goal,
            start_url=record.start_url,
            step_delay=settings.fake_step_delay,
        )
        return ThreadHandle(episode)
    cmd = runner_command(settings, record)
    log.info("spawning runner for %s: %s", record.id, shlex.join(cmd[:3]) + " ...")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "ab") as log_file:
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=os.environ.copy(),
            start_new_session=True,
        )
    return SubprocessHandle(proc)


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
