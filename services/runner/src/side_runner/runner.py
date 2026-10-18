"""Runs ONE BrowserGym episode and writes the Side artifact layout.

Step indexing: ``steps/0`` is the observation right after ``env.reset()`` (``action`` is null);
``steps/k`` (k >= 1) is the result of executing the k-th agent action. ``Run.n_steps`` is the
number of actions executed, so step files are ``0..n_steps``.
"""

import dataclasses
import importlib
import logging
import signal
import time
import traceback
from typing import Any, Optional

import gymnasium as gym

from .agents import Agent, create_agent
from .agents.base import AGENT_CONFIG_DEFAULTS
from .artifacts import RunStore
from .obs import build_step, preprocess_obs, step_summary
from .timeutil import iso

logger = logging.getLogger("side_runner")

OPENENDED = "browsergym/openended"
CHAT_ROLES = ("user", "assistant", "info", "infeasible")


@dataclasses.dataclass
class RunConfig:
    run_id: str
    task: str
    agent: dict[str, Any]
    max_steps: int
    data_dir: str
    goal: Optional[str] = None
    start_url: Optional[str] = None
    headless: bool = True
    seed: Optional[int] = None
    slow_mo: Optional[int] = None
    timeout: Optional[int] = None


class CancelledRun(Exception):
    pass


def import_task_package(task_id: str) -> None:
    """Import the browsergym benchmark package that registers ``task_id`` with gymnasium."""
    importlib.import_module("browsergym.core")
    if task_id == OPENENDED or not task_id.startswith("browsergym/"):
        return
    benchmark = task_id.split("/", 1)[1].split(".", 1)[0]
    try:
        importlib.import_module(f"browsergym.{benchmark}")
    except ImportError as e:
        raise RuntimeError(
            f"task {task_id!r} needs the browsergym-{benchmark} package ({e})"
        ) from e


class EpisodeRunner:
    def __init__(self, config: RunConfig):
        self.config = config
        self.store = RunStore(config.data_dir, config.run_id)
        self.run: dict[str, Any] = {}
        self.env = None
        self.agent: Optional[Agent] = None
        self.chat_cursor = 0
        self._signal_cancel = False

    # run.json / events
    def _init_run(self) -> None:
        cfg = self.config
        existing = self.store.read_run() or {}
        self.run = {
            **existing,
            "id": cfg.run_id,
            "task_id": cfg.task,
            "goal": cfg.goal,
            "agent": {**AGENT_CONFIG_DEFAULTS, **cfg.agent},
            "status": existing.get("status", "queued"),
            "reward": existing.get("reward"),
            "n_steps": 0,
            "max_steps": cfg.max_steps,
            "created_at": existing.get("created_at") or iso(),
            "started_at": None,
            "finished_at": None,
            "error": None,
        }
        self.store.write_run(self.run)
        if not existing:
            self.store.append_event("status", status="queued")

    def _set_status(self, status: str, **fields: Any) -> None:
        self.run.update(status=status, **fields)
        self.store.write_run(self.run)
        self.store.append_event("status", status=status)

    def _log(self, message: str) -> None:
        logger.info(message)
        self.store.append_event("log", log=message)

    def _chat(self, role: str, message: str, timestamp: Optional[str] = None) -> None:
        msg = {"role": role, "message": message, "timestamp": timestamp or iso()}
        self.store.append_chat(msg)
        self.store.append_event("chat", chat=msg)

    def _sync_chat(self) -> None:
        """Mirror new BrowserGym chat messages (assistant/infeasible/user) to chat.jsonl."""
        messages = self.env.unwrapped.chat.messages
        for m in messages[self.chat_cursor :]:
            if m["role"] in CHAT_ROLES:
                self._chat(m["role"], str(m["message"]), iso(m.get("timestamp")))
        self.chat_cursor = len(messages)

    # cancellation / inbox
    def _cancel_requested(self) -> bool:
        return self._signal_cancel or self.store.cancel_requested()

    def _on_signal(self, signum, frame) -> None:
        self._signal_cancel = True

    def _drain_inbox(self) -> None:
        for msg in self.store.read_new_inbox():
            text = msg.get("message") if isinstance(msg, dict) else None
            if not isinstance(text, str) or not text or msg.get("role", "user") != "user":
                self._log(f"ignoring invalid inbox line: {msg!r}")
                continue
            self.env.unwrapped.chat.add_message(role="user", msg=text)
        self._sync_chat()

    # steps
    def _record_step(self, index, obs, action, thought, reward, terminated, truncated, elapsed_ms):
        has_png = obs.get("screenshot") is not None
        if has_png:
            self.store.write_screenshot(index, obs["screenshot"])
        step = build_step(
            run_id=self.config.run_id,
            index=index,
            obs=obs,
            action=action,
            thought=thought,
            reward=reward,
            terminated=terminated,
            truncated=truncated,
            elapsed_ms=elapsed_ms,
            timestamp=iso(),
            has_screenshot=has_png,
        )
        self.store.write_step(step)
        self.run["n_steps"] = index
        self.store.write_run(self.run)
        self.store.append_event("step", step=step_summary(step))

    def _make_env(self):
        cfg = self.config
        import_task_package(cfg.task)
        task_kwargs: dict[str, Any] = {}
        if cfg.task == OPENENDED:
            if not cfg.start_url:
                raise ValueError("--start-url is required for browsergym/openended")
            task_kwargs = {"start_url": cfg.start_url, "goal": cfg.goal}
        elif cfg.goal or cfg.start_url:
            self._log(f"--goal/--start-url are ignored for task {cfg.task}")
        env_kwargs: dict[str, Any] = dict(
            headless=cfg.headless,
            action_mapping=self.agent.action_set.to_python_code,
            wait_for_user_message=False,
        )
        if task_kwargs:
            env_kwargs["task_kwargs"] = task_kwargs
        if cfg.slow_mo is not None:
            env_kwargs["slow_mo"] = cfg.slow_mo
        if cfg.timeout is not None:
            env_kwargs["timeout"] = cfg.timeout
        return gym.make(cfg.task, disable_env_checker=True, **env_kwargs)

    def _episode(self) -> None:
        cfg = self.config
        self.agent = create_agent(cfg.agent)
        self._set_status("running", started_at=iso())
        self._log(f"launching {cfg.task} with agent {cfg.agent['type']} (headless={cfg.headless})")
        self.env = self._make_env()

        t0 = time.perf_counter()
        obs, _ = self.env.reset(seed=cfg.seed)
        obs = preprocess_obs(obs)
        if not self.run.get("goal") and obs.get("goal"):
            self.run["goal"] = obs["goal"]  # task-provided goal (e.g. MiniWoB utterance)
        self._record_step(0, obs, None, None, 0.0, False, False, (time.perf_counter() - t0) * 1000)
        self._sync_chat()

        total_reward = 0.0
        for n in range(1, cfg.max_steps + 1):
            if self._cancel_requested():
                raise CancelledRun()
            self._drain_inbox()
            obs["chat_messages"] = tuple(dict(m) for m in self.env.unwrapped.chat.messages)

            t0 = time.perf_counter()
            out = self.agent.get_action(obs)
            raw_obs, reward, terminated, truncated, _ = self.env.step(out.action)
            obs = preprocess_obs(raw_obs)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            done = self.agent.episode_done(out, obs)

            total_reward += float(reward)
            self.run["reward"] = total_reward
            stop = terminated or truncated or done
            if n == cfg.max_steps and not stop:
                truncated = True
            self._record_step(
                n, obs, out.action, out.thought, reward, terminated, truncated, elapsed_ms
            )
            self._sync_chat()
            if terminated or truncated or done:
                break

        if self._cancel_requested():
            raise CancelledRun()
        self._log(f"episode finished after {self.run['n_steps']} steps, reward={total_reward}")

    def execute(self) -> str:
        """Run the episode; returns the terminal status."""
        self.store.ensure_dirs()
        self._init_run()
        previous_handlers = {
            sig: signal.signal(sig, self._on_signal) for sig in (signal.SIGTERM, signal.SIGINT)
        }
        status, error = "succeeded", None
        try:
            if self._cancel_requested():
                raise CancelledRun()
            self._episode()
        except CancelledRun:
            status = "cancelled"
        except Exception as e:  # noqa: BLE001 - every failure must land in run.json
            status, error = "failed", f"{type(e).__name__}: {e}"
            logger.exception("run failed")
            self.store.append_event("log", log=traceback.format_exc())
        finally:
            self._close()
            for sig, handler in previous_handlers.items():
                signal.signal(sig, handler)

        if status == "cancelled":
            self._chat("info", "Run cancelled.")
        elif status == "failed":
            self._chat("info", f"Run failed: {error}")
        self._set_status(status, finished_at=iso(), error=error)
        return status

    def _close(self) -> None:
        if self.env is not None:
            try:
                self._sync_chat()
            except Exception:  # noqa: BLE001
                pass
            try:
                self.env.close()
            except Exception:  # noqa: BLE001
                logger.warning("error while closing the environment", exc_info=True)
        if self.agent is not None:
            try:
                self.agent.close()
            except Exception:  # noqa: BLE001
                logger.warning("error while closing the agent", exc_info=True)


def run_episode(config: RunConfig) -> str:
    return EpisodeRunner(config).execute()
