import asyncio
import pathlib
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest import mock

import pytest

import browsergym.core
import browsergym.core.action.functions as fn_context
from browsergym.core.env import BrowserEnv

with mock.patch.object(sys, "argv", ["mcp_server", "--headless"]):
    from browsergym.utils import mcp_server

__DATA_DIR = pathlib.Path(__file__).resolve().parent / "data"
EXAMPLE_URL = f"file://{__DATA_DIR}/example.html"
LONG_PAGE_URL = f"file://{__DATA_DIR}/long_page.html"


@pytest.fixture
def fresh_global_playwright(monkeypatch):
    """Let the MCP server's Playwright thread start its own global Playwright instance."""
    monkeypatch.setattr(browsergym.core, "_PLAYWRIGHT", None)
    yield
    pw = browsergym.core._PLAYWRIGHT
    if pw is not None:
        mcp_server.PLAYWRIGHT_EXECUTOR.submit(pw.stop).result()


def _run_event_loop(scenario):
    """Run the scenario on its own event loop thread, like the MCP server's stdio loop.

    The pytest main thread may already host a running loop (e.g. a sync Playwright started by
    another test), where asyncio.run() is not allowed.
    """
    with ThreadPoolExecutor(max_workers=1) as loop_thread:
        return loop_thread.submit(lambda: asyncio.run(scenario())).result()


def _patch_mcp_context(monkeypatch, app_ctx):
    monkeypatch.setattr(
        mcp_server.mcp,
        "get_context",
        lambda: SimpleNamespace(request_context=SimpleNamespace(lifespan_context=app_ctx)),
    )


class RecordingEnv(BrowserEnv):
    """BrowserEnv stand-in that records which thread runs each env call."""

    def __init__(self):
        self.calls = []
        self.active_steps = 0
        self.max_active_steps = 0
        self.page = object()
        self.last_action = ""
        self.last_action_error = ""

    def _record(self, name):
        self.calls.append((name, threading.get_ident()))

    def reset(self, *args, **kwargs):
        self._record("reset")
        return {}, {}

    def close(self):
        self._record("close")

    def pre_step(self):
        self._record("pre_step")
        self.active_steps += 1
        self.max_active_steps = max(self.max_active_steps, self.active_steps)
        return {}, lambda *a, **k: None, lambda *a, **k: None

    def post_step(self, info, validate=True):
        time.sleep(0.01)
        self.active_steps -= 1
        self._record("post_step")
        return {"last_action_error": self.last_action_error}, 0, False, False, info


def test_env_and_actions_pinned_to_one_thread_and_serialized(monkeypatch):
    env = RecordingEnv()

    def fake_make(*args, **kwargs):
        env._record("make")
        return env

    def noop(wait_ms: float = 0):
        env._record("action")
        assert fn_context.page is env.page

    def failing(wait_ms: float = 0):
        env._record("action")
        raise ValueError("boom")

    monkeypatch.setattr(mcp_server.gym, "make", fake_make)
    monkeypatch.setattr(fn_context, "noop", noop)
    monkeypatch.setattr(fn_context, "failing", failing, raising=False)

    loop_thread_ids = set()

    async def scenario():
        loop_thread_ids.add(threading.get_ident())
        results = []
        for _ in range(2):
            async with mcp_server.app_lifespan(mcp_server.mcp) as app_ctx:
                _patch_mcp_context(monkeypatch, app_ctx)
                tool = mcp_server.fn_wrapper(noop, validate=False)
                failing_tool = mcp_server.fn_wrapper(failing, validate=False)
                results += await asyncio.gather(*[tool() for _ in range(8)], failing_tool())
        return results

    results = _run_event_loop(scenario)

    expected_errors = ([""] * 8 + ["ValueError: boom"]) * 2
    assert [obs["last_action_error"] for obs, *_ in results] == expected_errors
    names = [name for name, _ in env.calls]
    lifespan = ["make", "reset"] + ["pre_step", "action", "post_step"] * 9 + ["close"]
    assert names == lifespan * 2

    # Same thread across both lifespans, since the global Playwright instance outlives them.
    thread_ids = {ident for _, ident in env.calls}
    assert len(thread_ids) == 1
    assert not thread_ids & (loop_thread_ids | {threading.main_thread().ident})
    assert env.max_active_steps == 1


def test_concurrent_tool_calls_on_real_browser(monkeypatch, fresh_global_playwright):
    async def scenario():
        async with mcp_server.app_lifespan(mcp_server.mcp) as app_ctx:
            _patch_mcp_context(monkeypatch, app_ctx)
            goto = mcp_server.fn_wrapper(fn_context.goto, validate=False)
            scroll = mcp_server.fn_wrapper(fn_context.scroll, validate=False)
            noop = mcp_server.fn_wrapper(fn_context.noop, validate=False)

            obs, *_ = await goto(LONG_PAGE_URL)
            assert obs["last_action_error"] == ""
            assert obs["url"] == LONG_PAGE_URL

            results = await asyncio.gather(
                scroll(0, 200), noop(), scroll(0, 200), noop(), scroll(0, 200)
            )
            for obs, *_ in results:
                assert obs["last_action_error"] == ""
            page = app_ctx.gym.unwrapped.page
            scroll_y = await app_ctx.run(page.evaluate, "window.scrollY")
            assert scroll_y > 0

        # A restarted server reuses the same Playwright thread and global instance.
        async with mcp_server.app_lifespan(mcp_server.mcp) as app_ctx:
            _patch_mcp_context(monkeypatch, app_ctx)
            goto = mcp_server.fn_wrapper(fn_context.goto, validate=False)
            obs, *_ = await goto(EXAMPLE_URL)
            assert obs["last_action_error"] == ""
            assert obs["url"] == EXAMPLE_URL

    _run_event_loop(scenario)
