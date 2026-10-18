"""Server-Sent Events stream of a run's events.jsonl."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable

from starlette.requests import Request

from .schemas import TERMINAL_STATUSES, RunEvent
from .storage import RunPaths, now_iso

STALL_SECONDS = 2.0


def format_sse(event: dict, event_id: int | None = None) -> str:
    out = ""
    if event_id is not None:
        out += f"id: {event_id}\n"
    out += f"event: {event['type']}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"
    return out


def normalize_event(raw: dict, run_id: str, paths: RunPaths) -> dict | None:
    try:
        event = RunEvent.model_validate(raw)
    except ValueError:
        return None
    if event.step is not None:
        has_png = paths.step_png(event.step.index).is_file()
        event.step.screenshot_url = (
            f"/api/v1/runs/{run_id}/steps/{event.step.index}/screenshot" if has_png else None
        )
    return event.to_json_dict()


def _is_terminal(raw: object) -> bool:
    return (
        isinstance(raw, dict)
        and raw.get("type") == "status"
        and isinstance(raw.get("status"), str)
        and raw.get("status") in TERMINAL_STATUSES
    )


async def event_stream(
    request: Request,
    paths: RunPaths,
    run_id: str,
    current_status: Callable[[], str | None],
    poll_interval: float,
    heartbeat: float,
    last_event_id: int = 0,
) -> AsyncIterator[str]:
    """Replay events.jsonl from ``last_event_id`` then follow it; ends after a terminal status."""
    offset = 0
    buf = b""
    line_no = 0
    last_sent = time.monotonic()
    last_data = time.monotonic()
    yield "retry: 2000\n\n"
    while True:
        try:
            with open(paths.events, "rb") as f:
                f.seek(offset)
                chunk = f.read()
        except FileNotFoundError:
            chunk = b""
        if chunk:
            offset += len(chunk)
            last_data = time.monotonic()
            data = buf + chunk
            *lines, buf = data.split(b"\n")
            for line in lines:
                if not line.strip():
                    continue
                line_no += 1
                try:
                    raw = json.loads(line)
                except ValueError:
                    continue
                if line_no <= last_event_id:
                    if _is_terminal(raw):
                        return  # client already has the terminal status
                    continue
                event = normalize_event(raw, run_id, paths)
                if event is None:
                    continue
                yield format_sse(event, line_no)
                last_sent = time.monotonic()
                if event["type"] == "status" and event.get("status") in TERMINAL_STATUSES:
                    return
        else:
            now = time.monotonic()
            status = current_status()
            if status is None:
                return  # run deleted
            if status in TERMINAL_STATUSES and now - last_data > STALL_SECONDS:
                # Run is over but no terminal status line was written; synthesize one and close.
                event = {
                    "type": "status",
                    "run_id": run_id,
                    "timestamp": now_iso(),
                    "status": status,
                }
                yield format_sse(event)
                return
            if now - last_sent > heartbeat:
                yield ": ping\n\n"
                last_sent = now
            if await request.is_disconnected():
                return
            await asyncio.sleep(poll_interval)
