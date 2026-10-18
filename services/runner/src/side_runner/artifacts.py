"""Reading/writing the Side artifact layout (see docs/side/ARCHITECTURE.md).

runs/<run_id>/run.json          Run, rewritten on every status change (and after every step)
runs/<run_id>/steps/<n>.json    StepDetail, n = 0..N
runs/<run_id>/steps/<n>.png     screenshot for step n
runs/<run_id>/chat.jsonl        ChatMessage per line
runs/<run_id>/events.jsonl      RunEvent per line, append-only
runs/<run_id>/inbox.jsonl       user -> agent messages (written by the API)
runs/<run_id>/CANCEL            cancel marker (written by the API)
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image

from .timeutil import iso

TERMINAL_STATUSES = ("succeeded", "failed", "cancelled")


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=_json_default)


def _json_default(obj: Any):
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def atomic_write_text(path: Path, text: str) -> None:
    """Write via a temp file + rename so readers never observe a partial file."""
    tmp = path.with_name(f".{path.name}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def validate_run_id(run_id: str) -> str:
    """Run ids become a directory name under ``runs/``; reject anything path-like."""
    if not RUN_ID_RE.fullmatch(run_id) or ".." in run_id:
        raise ValueError(f"invalid run id {run_id!r}: expected [A-Za-z0-9][A-Za-z0-9._-]*")
    return run_id


class RunStore:
    def __init__(self, data_dir: str | os.PathLike, run_id: str):
        self.run_id = validate_run_id(run_id)
        self.run_dir = Path(data_dir) / "runs" / run_id
        self.steps_dir = self.run_dir / "steps"
        self.run_json = self.run_dir / "run.json"
        self.chat_jsonl = self.run_dir / "chat.jsonl"
        self.events_jsonl = self.run_dir / "events.jsonl"
        self.inbox_jsonl = self.run_dir / "inbox.jsonl"
        self.cancel_marker = self.run_dir / "CANCEL"
        self._inbox_offset = 0

    def ensure_dirs(self) -> None:
        self.steps_dir.mkdir(parents=True, exist_ok=True)

    # run.json
    def read_run(self) -> Optional[dict]:
        if not self.run_json.exists():
            return None
        try:
            return json.loads(self.run_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def write_run(self, run: dict) -> None:
        atomic_write_text(self.run_json, _dumps(run) + "\n")

    # steps
    def step_json_path(self, index: int) -> Path:
        return self.steps_dir / f"{index}.json"

    def step_png_path(self, index: int) -> Path:
        return self.steps_dir / f"{index}.png"

    def write_step(self, step: dict) -> None:
        atomic_write_text(self.step_json_path(step["index"]), _dumps(step) + "\n")

    def write_screenshot(self, index: int, screenshot: np.ndarray) -> Path:
        path = self.step_png_path(index)
        tmp = path.with_name(f".{path.name}.tmp")
        Image.fromarray(np.asarray(screenshot, dtype=np.uint8)).save(tmp, format="PNG")
        os.replace(tmp, path)
        return path

    # append-only jsonl
    @staticmethod
    def _append_jsonl(path: Path, obj: dict) -> None:
        line = (_dumps(obj) + "\n").encode("utf-8")
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, line)  # single write => one complete line per append
        finally:
            os.close(fd)

    def append_chat(self, message: dict) -> None:
        self._append_jsonl(self.chat_jsonl, message)

    def append_event(self, event_type: str, **payload: Any) -> dict:
        event = {"type": event_type, "run_id": self.run_id, "timestamp": iso(), **payload}
        self._append_jsonl(self.events_jsonl, event)
        return event

    # API -> runner signals
    def cancel_requested(self) -> bool:
        return self.cancel_marker.exists()

    def read_new_inbox(self) -> list[dict]:
        """Return complete inbox lines appended since the last call."""
        if not self.inbox_jsonl.exists():
            return []
        with open(self.inbox_jsonl, "rb") as f:
            f.seek(self._inbox_offset)
            data = f.read()
        end = data.rfind(b"\n")
        if end < 0:
            return []
        self._inbox_offset += end + 1
        messages = []
        for raw in data[: end + 1].splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                messages.append({"_invalid": raw.decode("utf-8", "replace")})
                continue
            messages.append(msg)
        return messages
