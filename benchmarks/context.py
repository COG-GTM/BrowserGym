"""Shared configuration handed to every suite."""

from __future__ import annotations

import functools
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

VIEWPORT = {"width": 1280, "height": 720}
TIMEOUT_MS = 30_000


@functools.lru_cache(maxsize=None)
def _action_mapping():
    from browsergym.core.action.highlevel import HighLevelActionSet

    return HighLevelActionSet(demo_mode="off").to_python_code


@dataclass
class PageInfo:
    size: str
    target_nodes: int
    url: str


@dataclass
class Context:
    pages: dict[str, PageInfo]
    workdir: Path
    headless: bool = True
    pre_observation_delay: float = 0.0
    measured_nodes: dict[str, int] = field(default_factory=dict)

    def env_kwargs(self, url: str) -> dict[str, Any]:
        return dict(
            task_kwargs={"start_url": url},
            headless=self.headless,
            viewport=VIEWPORT,
            timeout=TIMEOUT_MS,
            pre_observation_delay=self.pre_observation_delay,
            # HighLevelActionSet() defaults to demo_mode=None, which animates a cursor and adds
            # ~1 s of sleeps per bid action; benchmark the raw action cost instead.
            action_mapping=_action_mapping(),
        )

    def make_env(self, url: str):
        import gymnasium as gym

        import browsergym.core  # noqa: F401  (registers browsergym/openended)

        return gym.make("browsergym/openended", **self.env_kwargs(url))

    def page_params(self, size: str) -> dict[str, Any]:
        info = self.pages[size]
        params: dict[str, Any] = {"target_nodes": info.target_nodes}
        if size in self.measured_nodes:
            params["dom_nodes"] = self.measured_nodes[size]
        return params


def collect_garbage(page) -> None:
    """Force a renderer GC (untimed per-round setup).

    Back-to-back DOM snapshot / AXTree extractions on the 20k-node page pile up renderer garbage
    until the tab crashes, after which Playwright calls never return. Collecting between rounds
    keeps every round in the same steady state.
    """
    cdp = page.context.new_cdp_session(page)
    try:
        cdp.send("HeapProfiler.collectGarbage")
    finally:
        cdp.detach()


def watch_crashes(page, label: str) -> None:
    page.on("crash", lambda _: print(f"!! renderer crashed ({label})", file=sys.stderr, flush=True))
