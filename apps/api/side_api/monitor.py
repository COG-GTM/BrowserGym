"""RunManager: spawns runners and keeps the SQLite index in sync with each run's events.jsonl."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
import time
from collections import defaultdict

from sqlalchemy import Engine
from sqlmodel import select

from .config import Settings
from .db import RunRecord, session
from .notify import Notifier
from .runners import RunHandle, pid_alive, spawn, terminate_pid
from .schemas import TERMINAL_STATUSES, RunEvent
from .storage import RunPaths, append_jsonl, now_iso, read_json, write_json_atomic

log = logging.getLogger(__name__)

CANCEL_GRACE_SECONDS = 30.0


class RunManager:
    def __init__(self, settings: Settings, engine: Engine, notifier: Notifier):
        self.settings = settings
        self.engine = engine
        self.notifier = notifier
        self.handles: dict[str, RunHandle] = {}
        self.monitors: dict[str, asyncio.Task] = {}
        self.cancel_requested: dict[str, float] = {}
        self.loop: asyncio.AbstractEventLoop | None = None
        # Serialises liveness checks (worker threads) against deletion of the same run.
        self.run_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)

    def paths(self, run_id: str) -> RunPaths:
        return RunPaths(self.settings.data_dir, run_id)

    # -- lifecycle --------------------------------------------------------
    async def resume(self) -> None:
        self.loop = asyncio.get_running_loop()
        with session(self.engine) as s:
            ids = s.exec(
                select(RunRecord.id).where(RunRecord.status.in_(["queued", "running"]))  # type: ignore[attr-defined]
            ).all()
        for run_id in ids:
            # Statuses already in the log were forwarded by the previous API process.
            self._start_monitor(run_id, notify_after=_count_lines(self.paths(run_id).events))

    async def shutdown(self) -> None:
        for task in list(self.monitors.values()):
            task.cancel()
        for task in list(self.monitors.values()):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self.monitors.clear()
        await self.notifier.drain()

    # -- operations -------------------------------------------------------
    def start(self, record: RunRecord) -> None:
        """Write initial artifacts for a freshly persisted (queued) run, then launch its runner."""
        paths = self.paths(record.id)
        paths.steps_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(paths.run_json, record.to_run().model_dump(mode="json"))
        self.append_event(record.id, "status", status="queued")
        try:
            handle = spawn(self.settings, record, paths.runner_log)
        except OSError as e:
            self.finalize(record.id, "failed", error=f"failed to start runner: {e}")
        else:
            self.handles[record.id] = handle
            if handle.pid:
                with session(self.engine) as s:
                    rec = s.get(RunRecord, record.id)
                    if rec:
                        rec.pid = handle.pid
                        s.add(rec)
                        s.commit()
        self._start_monitor(record.id)

    def cancel(self, run_id: str) -> RunRecord | None:
        with session(self.engine) as s:
            rec = s.get(RunRecord, run_id)
        if rec is None or rec.status in TERMINAL_STATUSES:
            return rec
        paths = self.paths(run_id)
        paths.root.mkdir(parents=True, exist_ok=True)
        paths.cancel.write_text(now_iso(), encoding="utf-8")
        self.cancel_requested.setdefault(run_id, time.monotonic())
        handle = self.handles.get(run_id)
        alive = handle.is_alive() if handle else pid_alive(rec.pid)
        if rec.status == "queued" or not alive:
            if handle:
                handle.terminate()
            elif rec.pid and alive:
                terminate_pid(rec.pid, run_id)
            return self.finalize(run_id, "cancelled")
        return rec

    async def delete(self, run_id: str) -> None:
        handle = self.handles.pop(run_id, None)
        if handle and handle.is_alive():
            self.paths(run_id).cancel.touch()
            await asyncio.to_thread(handle.terminate)
        elif handle is None:
            # Runner may have been started by a previous API process (no in-memory handle).
            with session(self.engine) as s:
                rec = s.get(RunRecord, run_id)
            if rec and rec.pid and rec.status not in TERMINAL_STATUSES:
                await asyncio.to_thread(terminate_pid, rec.pid, run_id)
        task = self.monitors.pop(run_id, None)
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self.cancel_requested.pop(run_id, None)
        await asyncio.to_thread(self._delete_locked, run_id)

    def _delete_locked(self, run_id: str) -> None:
        with self.run_locks[run_id]:
            with session(self.engine) as s:
                rec = s.get(RunRecord, run_id)
                if rec:
                    s.delete(rec)
                    s.commit()
            self.paths(run_id).remove()
        self.run_locks.pop(run_id, None)

    def append_event(self, run_id: str, type_: str, **payload) -> dict:
        event = {"type": type_, "run_id": run_id, "timestamp": now_iso()} | payload
        append_jsonl(self.paths(run_id).events, event)
        return event

    def finalize(self, run_id: str, status: str, error: str | None = None) -> RunRecord | None:
        """API-side terminal transition (runner never started / died / cancelled while queued)."""
        with session(self.engine) as s:
            rec = s.get(RunRecord, run_id)
            if rec is None:
                return None
            if rec.status in TERMINAL_STATUSES:
                return rec
            rec.status = status
            rec.finished_at = now_iso()
            if error:
                rec.error = error
            s.add(rec)
            s.commit()
        write_json_atomic(self.paths(run_id).run_json, rec.to_run().model_dump(mode="json"))
        self.append_event(run_id, "status", status=status)
        return rec

    def refresh(self, run_id: str) -> None:
        """Pull runner-owned fields from run.json for a live run, so reads are never staler
        than the artifacts (the monitor only syncs every ``poll_interval``)."""
        with session(self.engine) as s:
            rec = s.get(RunRecord, run_id)
        if rec is not None and rec.status not in TERMINAL_STATUSES:
            self._sync_from_run_json(run_id)

    # -- monitoring -------------------------------------------------------
    def _start_monitor(self, run_id: str, notify_after: int = 0) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            if self.loop is None:
                raise
            self.loop.call_soon_threadsafe(self._start_monitor, run_id, notify_after)
            return
        if run_id not in self.monitors or self.monitors[run_id].done():
            self.monitors[run_id] = asyncio.create_task(
                self._monitor(run_id, notify_after), name=f"monitor-{run_id}"
            )

    async def _monitor(self, run_id: str, notify_after: int = 0) -> None:
        paths = self.paths(run_id)
        offset = 0
        buf = b""
        seen = 0
        try:
            while True:
                new_lines, offset, buf = _read_new_lines(paths.events, offset, buf)
                terminal = False
                for line in new_lines:
                    seen += 1
                    terminal |= self._handle_event(run_id, line, notify=seen > notify_after)
                if terminal:
                    await asyncio.sleep(1.0)
                    self._sync_from_run_json(run_id, keep_status=True)
                    return
                if not new_lines:
                    # May block (sleep / terminate grace period), keep it off the event loop.
                    await asyncio.to_thread(self._check_liveness, run_id)
                await asyncio.sleep(self.settings.poll_interval)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("monitor for run %s crashed", run_id)
        finally:
            self.handles.pop(run_id, None)
            self.cancel_requested.pop(run_id, None)
            if self.monitors.get(run_id) is asyncio.current_task():
                self.monitors.pop(run_id, None)

    def _handle_event(self, run_id: str, line: bytes, notify: bool = True) -> bool:
        try:
            event = RunEvent.model_validate(json.loads(line))
        except ValueError:
            log.warning("run %s: ignoring malformed event line", run_id)
            return False
        if event.type == "step" and event.step is not None:
            with session(self.engine) as s:
                rec = s.get(RunRecord, run_id)
                if rec and event.step.index > rec.n_steps:
                    rec.n_steps = event.step.index
                    s.add(rec)
                    s.commit()
            return False
        if event.type != "status" or event.status is None:
            return False
        self._sync_from_run_json(run_id, status=event.status)
        if notify:
            self.notifier.submit(event.to_json_dict())
        return event.status in TERMINAL_STATUSES

    def _sync_from_run_json(
        self, run_id: str, status: str | None = None, keep_status: bool = False
    ) -> None:
        data = read_json(self.paths(run_id).run_json) or {}
        with session(self.engine) as s:
            rec = s.get(RunRecord, run_id)
            if rec is None:
                return
            before = rec.status
            changed = rec.merge_run_json(data)
            if keep_status:
                rec.status = before
            if status is not None:
                rec.status = status
            if status in TERMINAL_STATUSES and not rec.finished_at:
                rec.finished_at = now_iso()
            if status == "running" and not rec.started_at:
                rec.started_at = now_iso()
            if changed or rec.status != before or status:
                s.add(rec)
                s.commit()

    def _check_liveness(self, run_id: str) -> None:
        with self.run_locks[run_id]:
            self._check_liveness_locked(run_id)

    def _check_liveness_locked(self, run_id: str) -> None:
        with session(self.engine) as s:
            rec = s.get(RunRecord, run_id)
        if rec is None or rec.status in TERMINAL_STATUSES:
            return
        handle = self.handles.get(run_id)
        requested = self.cancel_requested.get(run_id)
        if handle is not None:
            if (
                requested
                and time.monotonic() - requested > CANCEL_GRACE_SECONDS
                and handle.is_alive()
            ):
                handle.terminate()
                if not _has_unread_terminal(self.paths(run_id).events):
                    self.finalize(run_id, "cancelled")
                return
            if handle.is_alive():
                return
            # Give the runner's final writes a moment to land before declaring it dead.
            time.sleep(min(0.2, self.settings.poll_interval * 2))
            if _has_unread_terminal(self.paths(run_id).events):
                return
            code = handle.exit_code()
            if requested:
                self.finalize(run_id, "cancelled")
            else:
                tail = _tail(self.paths(run_id).runner_log)
                msg = f"runner exited with code {code} before reporting a final status"
                self.finalize(run_id, "failed", error=f"{msg}\n{tail}".strip())
        elif pid_alive(rec.pid):
            if requested and time.monotonic() - requested > CANCEL_GRACE_SECONDS:
                assert rec.pid is not None
                terminate_pid(rec.pid, run_id)
                if not _has_unread_terminal(self.paths(run_id).events):
                    self.finalize(run_id, "cancelled")
        else:
            if _has_unread_terminal(self.paths(run_id).events):
                return
            if requested:
                self.finalize(run_id, "cancelled")
                return
            self.finalize(
                run_id, "failed", error="runner process is no longer running (API restarted?)"
            )


def _read_new_lines(path, offset: int, buf: bytes) -> tuple[list[bytes], int, bytes]:
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            chunk = f.read()
    except FileNotFoundError:
        return [], offset, buf
    if not chunk:
        return [], offset, buf
    data = buf + chunk
    *complete, rest = data.split(b"\n")
    return [ln for ln in complete if ln.strip()], offset + len(chunk), rest


def _count_lines(path) -> int:
    try:
        return sum(1 for ln in path.read_bytes().split(b"\n") if ln.strip())
    except FileNotFoundError:
        return 0


def _has_unread_terminal(path) -> bool:
    try:
        lines = path.read_bytes().splitlines()
    except FileNotFoundError:
        return False
    for line in reversed(lines):
        with contextlib.suppress(ValueError):
            ev = json.loads(line)
            if ev.get("type") == "status":
                return ev.get("status") in TERMINAL_STATUSES
    return False


def _tail(path, n: int = 20) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return ""
    return "\n".join(lines[-n:])
