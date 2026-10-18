"""Helpers for the artifact layout under SIDE_DATA_DIR (see docs/side/ARCHITECTURE.md)."""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_STEP_FILE = re.compile(r"^(\d+)\.json$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def is_safe_run_id(run_id: str) -> bool:
    return bool(_SAFE_ID.match(run_id))


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Complete JSON lines only; a trailing partial line (being written) is skipped."""
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.endswith("\n"):
                break
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


class RunPaths:
    def __init__(self, data_dir: Path, run_id: str):
        self.run_id = run_id
        self.root = data_dir / "runs" / run_id

    @property
    def run_json(self) -> Path:
        return self.root / "run.json"

    @property
    def steps_dir(self) -> Path:
        return self.root / "steps"

    def step_json(self, index: int) -> Path:
        return self.steps_dir / f"{index}.json"

    def step_png(self, index: int) -> Path:
        return self.steps_dir / f"{index}.png"

    @property
    def chat(self) -> Path:
        return self.root / "chat.jsonl"

    @property
    def events(self) -> Path:
        return self.root / "events.jsonl"

    @property
    def inbox(self) -> Path:
        return self.root / "inbox.jsonl"

    @property
    def cancel(self) -> Path:
        return self.root / "CANCEL"

    @property
    def runner_log(self) -> Path:
        return self.root / "runner.log"

    def step_indices(self) -> list[int]:
        if not self.steps_dir.is_dir():
            return []
        found = (_STEP_FILE.match(p.name) for p in self.steps_dir.iterdir())
        return sorted(int(m.group(1)) for m in found if m)

    def remove(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
