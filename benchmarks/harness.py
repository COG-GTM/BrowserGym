"""Minimal timing harness: warmup + timed rounds with per-round setup/teardown."""

from __future__ import annotations

import fnmatch
import gc
import math
import statistics
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional


def summarize(samples: list[float]) -> dict[str, float]:
    """Summary statistics (seconds) for a list of timing samples."""
    if not samples:
        raise ValueError("no samples")
    ordered = sorted(samples)
    # nearest-rank p95
    p95 = ordered[min(len(ordered) - 1, max(0, math.ceil(0.95 * len(ordered)) - 1))]
    return {
        "min": ordered[0],
        "max": ordered[-1],
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "stdev": statistics.stdev(ordered) if len(ordered) > 1 else 0.0,
        "p95": p95,
    }


def measure(
    fn: Callable[[Any], Any],
    *,
    rounds: int,
    warmup: int = 1,
    setup: Optional[Callable[[], Any]] = None,
    teardown: Optional[Callable[[Any], Any]] = None,
) -> list[float]:
    """Time ``fn(state)`` for ``rounds`` rounds after ``warmup`` untimed rounds.

    ``setup()`` (untimed) returns the state passed to ``fn``; ``teardown(state)`` runs
    untimed after each round. The garbage collector is disabled while timing.
    """
    samples = []
    for i in range(warmup + rounds):
        state = setup() if setup else None
        gc_was_enabled = gc.isenabled()
        gc.collect()
        gc.disable()
        try:
            t0 = time.perf_counter()
            fn(state)
            elapsed = time.perf_counter() - t0
        finally:
            if gc_was_enabled:
                gc.enable()
            if teardown:
                teardown(state)
        if i >= warmup:
            samples.append(elapsed)
    return samples


@dataclass
class BenchResult:
    id: str
    group: str
    name: str
    size: str
    rounds: int
    warmup: int
    stats: dict[str, float]
    unit: str = "s"
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def format_seconds(value: Optional[float]) -> str:
    if value is None:
        return "-"
    if value >= 1:
        return f"{value:.2f} s"
    if value >= 1e-3:
        return f"{value * 1e3:.2f} ms"
    return f"{value * 1e6:.1f} µs"


class Runner:
    """Collects benchmark results, applying an id filter and a rounds scale."""

    def __init__(
        self,
        *,
        scale: float = 1.0,
        rounds_override: Optional[int] = None,
        patterns: Optional[list[str]] = None,
        verbose: bool = True,
        timeout: Optional[float] = None,
        on_timeout: Optional[Callable[[str], None]] = None,
    ):
        self.scale = scale
        self.rounds_override = rounds_override
        self.patterns = patterns or []
        self.verbose = verbose
        self.results: list[BenchResult] = []
        # watchdog: a crashed renderer makes Playwright calls block forever, so a benchmark that
        # exceeds `timeout` seconds calls `on_timeout(bench_id)` (which should exit the process)
        self.timeout = timeout
        self.on_timeout = on_timeout

    @staticmethod
    def make_id(group: str, name: str, size: str) -> str:
        return f"{group}.{name}[{size}]"

    def selected(self, group: str, name: str, size: str) -> bool:
        if not self.patterns:
            return True
        bench_id = self.make_id(group, name, size)
        # "[" starts a character class in fnmatch; ids use it literally ("obs.axtree[large]")
        return any(
            fnmatch.fnmatchcase(bench_id, p.replace("[", "[[]")) or p in bench_id
            for p in self.patterns
        )

    def any_selected(self, group: str, names: list[str], size: str) -> bool:
        return any(self.selected(group, n, size) for n in names)

    def rounds_for(self, base: int) -> int:
        if self.rounds_override is not None:
            return max(1, self.rounds_override)
        return max(2, int(round(base * self.scale)))

    def bench(
        self,
        group: str,
        name: str,
        size: str,
        fn: Callable[[Any], Any],
        *,
        rounds: int,
        warmup: int = 1,
        setup: Optional[Callable[[], Any]] = None,
        teardown: Optional[Callable[[Any], Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> Optional[BenchResult]:
        if not self.selected(group, name, size):
            return None
        n = self.rounds_for(rounds)
        bench_id = self.make_id(group, name, size)
        watchdog = None
        if self.timeout and self.on_timeout:
            watchdog = threading.Timer(self.timeout, self.on_timeout, args=(bench_id,))
            watchdog.daemon = True
            watchdog.start()
        try:
            samples = measure(fn, rounds=n, warmup=warmup, setup=setup, teardown=teardown)
        finally:
            if watchdog is not None:
                watchdog.cancel()
        result = BenchResult(
            id=bench_id,
            group=group,
            name=name,
            size=size,
            rounds=n,
            warmup=warmup,
            stats=summarize(samples),
            params=dict(params or {}),
        )
        self.results.append(result)
        if self.verbose:
            s = result.stats
            print(
                f"  {result.id:<42} median {format_seconds(s['median']):>10}  "
                f"min {format_seconds(s['min']):>10}  p95 {format_seconds(s['p95']):>10}  "
                f"(n={n})",
                file=sys.stderr,
                flush=True,
            )
        return result
