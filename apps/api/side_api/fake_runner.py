"""FakeRunner: writes a realistic BrowserGym-like episode into the artifact layout.

Used in-process by the API when ``SIDE_FAKE_RUNNER=1`` and also runnable as a stand-in for
``side_runner`` (same CLI as the runner contract)::

    python -m side_api.fake_runner --run-id <id> --task <gym_id> --agent-json '{"type":"mock"}' \
        --max-steps 5 --data-dir ./.side-data [--goal ...] [--start-url ...]

Behaviour mirrors the ``mock`` agent: noop/scroll, then ``send_msg_to_user``. Goals containing
``[fail]`` end in ``failed``; goals containing ``[infeasible]`` end with ``report_infeasible``.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .png import Canvas
from .storage import RunPaths, append_jsonl, now_iso, read_json, read_jsonl, write_json_atomic

BENCH_COLORS = {
    "openended": (37, 99, 235),
    "miniwob": (5, 150, 105),
    "webarena": (217, 119, 6),
    "workarena": (124, 58, 237),
}


def screenshot_url(run_id: str, index: int) -> str:
    return f"/api/v1/runs/{run_id}/steps/{index}/screenshot"


def render_screenshot(path: Path, task_id: str, index: int, total: int, scroll: int) -> None:
    bench = task_id.removeprefix("browsergym/").split(".", 1)[0]
    accent = BENCH_COLORS.get(bench, (14, 116, 144))
    c = Canvas(640, 400, (248, 250, 252))
    # scrollable content (drawn first so the sticky header/chrome stay on top)
    for row in range(16):
        y = 100 + row * 26 - scroll
        if 84 <= y < 380:
            c.rect(24, y, 380 - (row * 37) % 140, 10, (203, 213, 225))
    # target element highlight (moves per step)
    bx, by = 440, 110 + (index * 57) % 180
    c.rect(bx - 3, by - 3, 166, 46, (250, 204, 21))
    c.rect(bx, by, 160, 40, accent)
    c.rect(bx + 20, by + 16, 120, 8, (255, 255, 255))
    # sticky page header
    c.rect(0, 36, 640, 48, accent)
    c.text(16, 50, f"STEP {index}/{total}", (255, 255, 255), scale=4)
    # browser chrome
    c.rect(0, 0, 640, 36, (226, 232, 240))
    for i, col in enumerate([(239, 68, 68), (234, 179, 8), (34, 197, 94)]):
        c.rect(12 + i * 18, 13, 10, 10, col)
    c.rect(80, 8, 480, 20, (255, 255, 255))
    c.rect(88, 15, 160, 6, (148, 163, 184))
    # progress bar
    c.rect(0, 392, 640, 8, (226, 232, 240))
    c.rect(0, 392, int(640 * index / max(total, 1)), 8, accent)
    path.parent.mkdir(parents=True, exist_ok=True)
    c.save(path)


def _plan(goal: str | None, max_steps: int) -> list[tuple[str, str]]:
    goal_text = goal or "the task"
    if goal and "[infeasible]" in goal:
        final = (
            f"report_infeasible({json.dumps('I cannot do this here.')})",
            "The requested element does not exist on this page.",
        )
    else:
        final = (
            f"send_msg_to_user({json.dumps(f'Done: {goal_text}')})",
            "The goal looks complete, I will report back to the user.",
        )
    plan = [
        ("noop(500)", "The page is still loading, let me wait for it."),
        ("scroll(0, 200)", "I need to see more of the page to locate the target element."),
        ("click('a42')", "The highlighted element matches the goal, I will click it."),
        final,
    ]
    if len(plan) > max_steps:
        plan = plan[: max_steps - 1] + [final] if max_steps > 1 else [final]
    return plan


class FakeEpisode:
    def __init__(
        self,
        data_dir: Path,
        run_id: str,
        task_id: str,
        agent: dict[str, Any],
        max_steps: int,
        goal: str | None = None,
        start_url: str | None = None,
        step_delay: float = 0.5,
        stop_event: threading.Event | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.paths = RunPaths(Path(data_dir), run_id)
        self.run_id = run_id
        self.task_id = task_id
        self.agent = agent
        self.max_steps = max_steps
        self.goal = goal
        self.start_url = start_url or "https://example.com/"
        self.step_delay = step_delay
        self.stop_event = stop_event or threading.Event()
        self.sleep = sleep
        self._inbox_seen = 0
        existing = read_json(self.paths.run_json) or {}
        self.run: dict[str, Any] = {
            "id": run_id,
            "task_id": task_id,
            "goal": goal,
            "agent": agent,
            "status": "queued",
            "reward": None,
            "n_steps": 0,
            "max_steps": max_steps,
            "created_at": now_iso(),
            "started_at": None,
            "finished_at": None,
            "error": None,
        } | existing

    # -- artifact writers -------------------------------------------------
    def _event(self, type_: str, **payload: Any) -> None:
        append_jsonl(
            self.paths.events,
            {"type": type_, "run_id": self.run_id, "timestamp": now_iso()} | payload,
        )

    def _chat(self, role: str, message: str) -> None:
        msg = {"role": role, "message": message, "timestamp": now_iso()}
        append_jsonl(self.paths.chat, msg)
        self._event("chat", chat=msg)

    def _status(self, status: str, **fields: Any) -> None:
        self.run.update(status=status, **fields)
        write_json_atomic(self.paths.run_json, self.run)
        self._event("status", status=status)

    def _step(self, index: int, action: str | None, thought: str | None, total: int, **kw) -> None:
        t0 = time.perf_counter()
        scroll = 200 if index >= 2 else 0
        render_screenshot(self.paths.step_png(index), self.task_id, index, total, scroll)
        url = self.start_url if index < 3 else self.start_url.rstrip("/") + "/done"
        detail = {
            "index": index,
            "action": action,
            "thought": thought,
            "url": url,
            "reward": kw.get("reward", 0.0),
            "terminated": kw.get("terminated", False),
            "truncated": kw.get("truncated", False),
            "last_action_error": None,
            "screenshot_url": screenshot_url(self.run_id, index),
            "elapsed_ms": round((time.perf_counter() - t0) * 1000 + 120.0, 1),
            "timestamp": now_iso(),
            "axtree_txt": (
                f"RootWebArea 'Fake page for {self.task_id}', focused\n"
                f"\t[a12] heading 'Step {index}'\n"
                "\t[a42] button 'Submit'\n"
                "\t[a57] textbox 'Search', clickable"
            ),
            "pruned_html": (
                f'<body><h1 bid="a12">Step {index}</h1>'
                '<input bid="a57" placeholder="Search"/><button bid="a42">Submit</button></body>'
            ),
            "focused_element_bid": "a42" if index >= 3 else None,
        }
        write_json_atomic(self.paths.step_json(index), detail)
        step = {
            k: v
            for k, v in detail.items()
            if k not in ("axtree_txt", "pruned_html", "focused_element_bid")
        }
        self._event("step", step=step)

    def _drain_inbox(self) -> None:
        messages = read_jsonl(self.paths.inbox)
        for msg in messages[self._inbox_seen :]:
            text = str(msg.get("message", ""))
            self._chat("user", text)
            self._chat("assistant", f"Noted: {text}")
        self._inbox_seen = len(messages)

    def _should_stop(self) -> bool:
        return self.stop_event.is_set() or self.paths.cancel.exists()

    # -- episode ----------------------------------------------------------
    def run_episode(self) -> str:
        try:
            return self._run()
        except Exception as e:  # noqa: BLE001 - surface any failure as a failed run
            self._status("failed", error=f"fake runner crashed: {e}", finished_at=now_iso())
            return "failed"

    def _run(self) -> str:
        self._status("running", started_at=now_iso())
        self._event("log", log=f"env reset: {self.task_id} (agent={self.agent.get('type')})")
        self._chat("assistant", "Hi! I am your UI assistant, I can perform web tasks for you.")
        if self.goal:
            self._chat("user", self.goal)
        plan = _plan(self.goal, self.max_steps)
        total = len(plan)
        self._step(0, None, None, total)
        for i, (action, thought) in enumerate(plan, start=1):
            self.sleep(self.step_delay)
            self._drain_inbox()
            if self._should_stop():
                self._event("log", log="cancel requested, stopping after current step")
                self._status("cancelled", finished_at=now_iso())
                return "cancelled"
            last = i == total
            reward = 1.0 if last and action.startswith("send_msg_to_user") else 0.0
            self._event("log", log=f"step {i}: {action}")
            self._step(i, action, thought, total, reward=reward, terminated=last)
            self.run["n_steps"] = i
            if action.startswith("send_msg_to_user"):
                self._chat("assistant", json.loads(action[len("send_msg_to_user(") : -1]))
            elif action.startswith("report_infeasible"):
                self._chat("infeasible", json.loads(action[len("report_infeasible(") : -1]))
        self._drain_inbox()
        if self.goal and "[fail]" in self.goal:
            self._status(
                "failed", error="simulated failure ([fail] in goal)", finished_at=now_iso()
            )
            return "failed"
        final_reward = 1.0 if plan[-1][0].startswith("send_msg_to_user") else 0.0
        self._status("succeeded", reward=final_reward, finished_at=now_iso())
        return "succeeded"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="side_api.fake_runner", description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--agent-json", required=True)
    p.add_argument("--max-steps", type=int, default=15)
    p.add_argument("--data-dir", required=True)
    p.add_argument("--goal")
    p.add_argument("--start-url")
    p.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--step-delay", type=float, default=0.5)
    a = p.parse_args(argv)
    status = FakeEpisode(
        Path(a.data_dir),
        a.run_id,
        a.task,
        json.loads(a.agent_json),
        a.max_steps,
        goal=a.goal,
        start_url=a.start_url,
        step_delay=a.step_delay,
    ).run_episode()
    return 0 if status in ("succeeded", "cancelled") else 1


if __name__ == "__main__":
    raise SystemExit(main())
