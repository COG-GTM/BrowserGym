"""Browser session lifecycle for the MCP server.

Playwright's sync API (used by BrowserEnv) is bound to the thread that started it, and BrowserGym
shares one global Playwright instance per process. All browser work is therefore funnelled through a
single dedicated worker thread, while the MCP event loop stays responsive.
"""

import asyncio
import functools
import io
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional, TypeVar

import gymnasium as gym
import numpy as np

from browsergym.core.action.highlevel import HighLevelActionSet
from browsergym.core.env import BrowserEnv
from browsergym.utils.obs import flatten_axtree_to_str

from .config import ServerConfig
from .models import BrowserObservation, ChatMessage, PageInfo

logger = logging.getLogger(__name__)

T = TypeVar("T")

_worker: Optional[ThreadPoolExecutor] = None
_worker_lock = threading.Lock()
_worker_users = 0


def browser_worker() -> ThreadPoolExecutor:
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="browsergym-mcp")
        return _worker


async def run_in_browser_thread(fn: Callable[..., T], *args, **kwargs) -> T:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(browser_worker(), functools.partial(fn, *args, **kwargs))


def acquire_browser_worker() -> None:
    global _worker_users
    with _worker_lock:
        _worker_users += 1


def release_browser_worker() -> None:
    """Shut the worker down once the last server run using it has finished."""
    global _worker_users
    with _worker_lock:
        _worker_users = max(0, _worker_users - 1)
        if _worker_users == 0:
            _shutdown_worker_locked()


def shutdown_browser_worker() -> None:
    """Stop the global Playwright driver (if we started it) and the worker thread."""
    with _worker_lock:
        _shutdown_worker_locked()


def _shutdown_worker_locked() -> None:
    # Runs with _worker_lock held, so no new worker can be created (and pick up the old
    # thread-bound Playwright global) until the old driver has fully stopped.
    global _worker
    worker, _worker = _worker, None
    if worker is None:
        return

    def _stop_playwright():
        import browsergym.core as core

        if core._PLAYWRIGHT is not None:
            try:
                core._PLAYWRIGHT.stop()
            finally:
                core._set_global_playwright(None)

    try:
        worker.submit(_stop_playwright).result(timeout=30)
    except Exception:
        logger.exception("Failed to stop Playwright")
    worker.shutdown(wait=True)


class BrowserSession:
    """One BrowserGym environment owned by one MCP client session.

    All methods ending in ``_sync`` must run on the browser worker thread.
    """

    def __init__(self, config: ServerConfig):
        self.config = config
        self.env: Optional[gym.Env] = None
        self.disposed = False
        self.task_id = config.task_id
        self.step_count = 0
        self.last_reward = 0.0
        self.last_terminated = False
        self.last_truncated = False
        self.action_set = HighLevelActionSet(
            subsets=list(config.subsets),
            demo_mode=config.demo_mode,
            strict=False,
            multiaction=False,
        )

    @property
    def started(self) -> bool:
        return self.env is not None

    @property
    def browser_env(self) -> BrowserEnv:
        assert self.env is not None
        return self.env.unwrapped  # type: ignore[return-value]

    def reset_sync(
        self,
        task_id: Optional[str] = None,
        start_url: Optional[str] = None,
        goal: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> BrowserObservation:
        self._check_not_disposed()
        self.close_sync()
        self.task_id = task_id or self.config.task_id
        task_kwargs: dict[str, Any] = {}
        if self.task_id == "browsergym/openended":
            task_kwargs["start_url"] = start_url or self.config.start_url
            if goal or self.config.goal:
                task_kwargs["goal"] = goal or self.config.goal
        elif start_url or goal:
            raise ValueError("start_url / goal can only be set for the browsergym/openended task")

        logger.info("Starting BrowserGym env %s", self.task_id)
        try:
            self.env = gym.make(
                self.task_id,
                headless=self.config.headless,
                timeout=self.config.timeout_ms,
                viewport={
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height,
                },
                record_video_dir=self.config.record_video_dir,
                action_mapping=self.action_set.to_python_code,
                task_kwargs=task_kwargs,
            )
            obs, _ = self.browser_env.reset(seed=seed)
            self.step_count = 0
            self.last_reward, self.last_terminated, self.last_truncated = 0.0, False, False
            return self._to_observation(obs, action=None)
        except BaseException:
            # never keep a half-initialized env around: the next call starts from scratch
            self.close_sync()
            raise

    def _check_not_disposed(self) -> None:
        if self.disposed:
            raise RuntimeError(
                "This browser session was closed; call the tool again to start a new one"
            )

    def ensure_started_sync(self) -> None:
        self._check_not_disposed()
        if not self.started:
            self.reset_sync()

    def step_sync(self, action: str) -> BrowserObservation:
        self.ensure_started_sync()
        obs, reward, terminated, truncated, _ = self.browser_env.step(action)
        self.step_count += 1
        self.last_reward = float(reward)
        self.last_terminated = bool(terminated)
        self.last_truncated = bool(truncated)
        return self._to_observation(obs, action=action)

    def observe_sync(self) -> BrowserObservation:
        self.ensure_started_sync()
        env = self.browser_env
        env._active_page_check()
        env._wait_dom_loaded()
        return self._to_observation(env._get_obs(), action=None)

    def close_sync(self) -> None:
        if self.env is None:
            return
        env, self.env = self.env, None
        try:
            env.close()
            logger.info("Closed BrowserGym env %s", self.task_id)
        except Exception:
            logger.exception("Error while closing BrowserGym env")

    def dispose_sync(self) -> None:
        """Close for good: work still queued for this session must not relaunch a browser."""
        self.disposed = True
        self.close_sync()

    def _to_observation(self, obs: dict, action: Optional[str]) -> BrowserObservation:
        self.last_obs = obs
        axtree = flatten_axtree_to_str(
            obs["axtree_object"], extra_properties=obs.get("extra_element_properties")
        )
        limit = self.config.max_axtree_chars
        if limit and len(axtree) > limit:
            axtree = axtree[:limit] + f"\n... [truncated {len(axtree) - limit} chars]"
        urls = list(obs.get("open_pages_urls", ()))
        titles = list(obs.get("open_pages_titles", ()))
        active = int(np.asarray(obs.get("active_page_index", [0])).reshape(-1)[0])
        return BrowserObservation(
            action=action,
            url=obs.get("url", ""),
            title=titles[active] if active < len(titles) else "",
            open_pages=[PageInfo(url=u, title=t) for u, t in zip(urls, titles)],
            active_page_index=active,
            axtree=axtree,
            focused_element_bid=obs.get("focused_element_bid") or None,
            last_action_error=obs.get("last_action_error", ""),
            goal=obs.get("goal", "") or "",
            chat_messages=[
                ChatMessage(role=m["role"], message=str(m["message"]), timestamp=m.get("timestamp"))
                for m in obs.get("chat_messages", ())
            ],
            reward=self.last_reward,
            terminated=self.last_terminated,
            truncated=self.last_truncated,
            step=self.step_count,
            task_id=self.task_id,
        )

    def screenshot_png_sync(self) -> Optional[bytes]:
        screenshot = getattr(self, "last_obs", {}).get("screenshot")
        if screenshot is None:
            return None
        from PIL import Image

        buf = io.BytesIO()
        Image.fromarray(np.asarray(screenshot)).save(buf, format="PNG", optimize=True)
        return buf.getvalue()


class SessionScope:
    """Browser sessions created within one MCP server run (one client session for stdio and
    stateful Streamable HTTP). Everything still open is closed when the run ends."""

    def __init__(self, config: ServerConfig):
        self.config = config
        self._sessions: dict[int, BrowserSession] = {}
        self._lock = asyncio.Lock()

    def __len__(self) -> int:
        return len(self._sessions)

    async def get(self, key: int) -> BrowserSession:
        async with self._lock:
            session = self._sessions.get(key)
            if session is None:
                session = BrowserSession(self.config)
                self._sessions[key] = session
            return session

    async def close(self, key: int) -> bool:
        async with self._lock:
            session = self._sessions.pop(key, None)
        if session is None:
            return False
        await run_in_browser_thread(session.dispose_sync)
        return True

    async def close_all(self) -> None:
        async with self._lock:
            sessions, self._sessions = list(self._sessions.values()), {}
        for session in sessions:
            await run_in_browser_thread(session.dispose_sync)
