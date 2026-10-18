"""Task and agent catalogs.

Tasks are enumerated from the gymnasium registry after importing the BrowserGym benchmark
packages that are installed. Without BrowserGym a small built-in catalog is served so the API
(and the FakeRunner) stay usable offline.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import os
import re
from functools import lru_cache

from .schemas import AgentInfo, Task

log = logging.getLogger(__name__)

BENCHMARK_MODULES = [
    "browsergym.core",
    "browsergym.miniwob",
    "browsergym.webarena",
    "browsergym.webarenalite",
    "browsergym.visualwebarena",
    "browsergym.workarena",
    "browsergym.assistantbench",
]

# Benchmarks that need external servers / instances regardless of local config.
SETUP_BENCHMARKS = {"webarena", "webarenalite", "visualwebarena", "workarena"}

BENCHMARK_TITLES = {
    "openended": "Open-ended",
    "miniwob": "MiniWoB++",
    "webarena": "WebArena",
    "webarenalite": "WebArena Lite",
    "visualwebarena": "VisualWebArena",
    "workarena": "WorkArena",
    "assistantbench": "AssistantBench",
}

FALLBACK_TASK_IDS = [
    "browsergym/openended",
    "browsergym/miniwob.click-test",
    "browsergym/miniwob.click-button",
    "browsergym/miniwob.click-checkboxes",
    "browsergym/miniwob.enter-text",
    "browsergym/miniwob.login-user",
    "browsergym/miniwob.choose-list",
    "browsergym/miniwob.book-flight",
    "browsergym/webarena.0",
    "browsergym/webarena.1",
    "browsergym/workarena.servicenow.order-standard-laptop",
    "browsergym/workarena.servicenow.create-incident",
]

AGENTS = [
    AgentInfo(type="mock", title="Mock agent (deterministic, offline)", models=[]),
    AgentInfo(type="scripted", title="Scripted agent (replays a list of actions)", models=[]),
    AgentInfo(
        type="openai",
        title="OpenAI LLM agent",
        models=["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"],
    ),
    AgentInfo(
        type="anthropic",
        title="Anthropic LLM agent",
        models=["claude-3-5-haiku-latest", "claude-3-5-sonnet-latest", "claude-3-7-sonnet-latest"],
    ),
]


def benchmark_of(task_id: str) -> str:
    name = task_id.removeprefix("browsergym/")
    return name.split(".", 1)[0]


def requires_setup(benchmark: str) -> bool:
    if benchmark in SETUP_BENCHMARKS:
        return True
    if benchmark == "miniwob":
        return not os.environ.get("MINIWOB_URL")
    return False


def title_of(task_id: str) -> str:
    name = task_id.removeprefix("browsergym/")
    benchmark, _, rest = name.partition(".")
    bench_title = BENCHMARK_TITLES.get(benchmark, benchmark)
    if not rest:
        return bench_title
    if rest.isdigit():
        return f"{bench_title} #{rest}"
    rest = rest.removeprefix("servicenow.")
    words = re.split(r"[-_.]+", rest)
    return f"{bench_title}: " + " ".join(w.capitalize() for w in words if w)


def _task_class(spec) -> type | None:
    """Best-effort extraction of the task class behind browsergym.core.register_task's lambda."""
    entry = getattr(spec, "entry_point", None)
    for cell in getattr(entry, "__closure__", None) or ():
        obj = cell.cell_contents
        for _ in range(4):
            if inspect.isclass(obj):
                return obj
            obj = getattr(obj, "func", None)
            if obj is None:
                break
    return None


def _description_of(spec) -> str | None:
    cls = _task_class(spec)
    doc = inspect.getdoc(cls) if cls is not None else None
    if not doc:
        return None
    first = doc.strip().split("\n\n", 1)[0].replace("\n", " ").strip()
    return first or None


def _make_task(task_id: str, description: str | None = None) -> Task:
    benchmark = benchmark_of(task_id)
    return Task(
        id=task_id,
        benchmark=benchmark,
        title=title_of(task_id),
        description=description,
        requires_setup=requires_setup(benchmark),
    )


@lru_cache(maxsize=1)
def _discover() -> tuple[Task, ...] | None:
    try:
        importlib.import_module("browsergym.core")
    except Exception as e:  # noqa: BLE001 - any import failure means "not installed"
        log.info("browsergym.core not importable (%s); using built-in task catalog", e)
        return None
    for mod in BENCHMARK_MODULES[1:]:
        try:
            importlib.import_module(mod)
        except Exception as e:  # noqa: BLE001
            log.debug("skipping %s: %s", mod, e)
    import gymnasium as gym

    tasks = [
        _make_task(env_id, _description_of(spec))
        for env_id, spec in gym.envs.registry.items()
        if env_id.startswith("browsergym/")
    ]
    tasks.sort(key=lambda t: (t.benchmark != "openended", t.benchmark, _natural_key(t.id)))
    return tuple(tasks)


def _natural_key(s: str) -> list:
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", s)]


def all_tasks() -> list[Task]:
    discovered = _discover()
    if discovered is not None:
        return list(discovered)
    return [_make_task(t) for t in FALLBACK_TASK_IDS]


def find_task(task_id: str) -> Task | None:
    return next((t for t in all_tasks() if t.id == task_id), None)


def list_tasks(benchmark: str | None = None, q: str | None = None) -> list[Task]:
    tasks = all_tasks()
    if benchmark:
        tasks = [t for t in tasks if t.benchmark == benchmark]
    if q:
        needle = q.lower()
        tasks = [
            t
            for t in tasks
            if needle in t.id.lower()
            or needle in t.title.lower()
            or needle in (t.description or "").lower()
        ]
    return tasks
