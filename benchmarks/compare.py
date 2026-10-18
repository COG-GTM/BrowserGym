"""Compare two benchmark result JSON files and render a markdown table."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .harness import format_seconds

DEFAULT_THRESHOLD = 0.25  # +/-25% on the chosen statistic
DEFAULT_STAT = "median"


@dataclass
class Row:
    id: str
    baseline: Optional[float]
    current: Optional[float]
    status: str  # "ok" | "regression" | "improvement" | "new" | "missing"

    @property
    def ratio(self) -> Optional[float]:
        if self.baseline in (None, 0) or self.current is None:
            return None
        return self.current / self.baseline


def load(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text("utf-8"))
    if "results" not in data:
        raise ValueError(f"{path}: not a benchmark result file (missing 'results')")
    return data


def _index(data: dict[str, Any], stat: str) -> dict[str, float]:
    return {r["id"]: r["stats"][stat] for r in data["results"]}


def compare(
    baseline: dict[str, Any],
    current: dict[str, Any],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    stat: str = DEFAULT_STAT,
) -> list[Row]:
    base, cur = _index(baseline, stat), _index(current, stat)
    order = [r["id"] for r in current["results"]] + [
        i for i in (r["id"] for r in baseline["results"]) if i not in cur
    ]
    rows = []
    for bench_id in order:
        b, c = base.get(bench_id), cur.get(bench_id)
        if b is None:
            status = "new"
        elif c is None:
            status = "missing"
        elif b > 0 and c / b > 1 + threshold:
            status = "regression"
        elif b > 0 and c / b < 1 - threshold:
            status = "improvement"
        else:
            status = "ok"
        rows.append(Row(bench_id, b, c, status))
    return rows


_STATUS_LABEL = {
    "ok": "ok",
    "regression": "**REGRESSION**",
    "improvement": "improvement",
    "new": "new",
    "missing": "missing",
}


def _env_line(meta: dict[str, Any]) -> str:
    keys = ("cpu", "cpu_count", "platform", "python", "playwright", "chromium", "git_sha")
    return ", ".join(f"{k}={meta[k]}" for k in keys if meta.get(k) not in (None, ""))


def to_markdown(
    rows: list[Row],
    *,
    baseline_meta: Optional[dict[str, Any]] = None,
    current_meta: Optional[dict[str, Any]] = None,
    threshold: float = DEFAULT_THRESHOLD,
    stat: str = DEFAULT_STAT,
) -> str:
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    summary = ", ".join(f"{counts[k]} {k}" for k in _STATUS_LABEL if counts.get(k))
    lines = [
        f"### BrowserGym benchmarks: {stat}, threshold ±{threshold:.0%}",
        "",
        f"Summary: {summary or 'no results'}",
        "",
    ]
    if baseline_meta:
        lines.append(f"- baseline: {_env_line(baseline_meta)}")
    if current_meta:
        lines.append(f"- current: {_env_line(current_meta)}")
    if baseline_meta or current_meta:
        lines.append("")
    lines += [
        "| Benchmark | Baseline | Current | Δ | Status |",
        "|---|---:|---:|---:|---|",
    ]
    for r in rows:
        delta = "-" if r.ratio is None else f"{(r.ratio - 1) * 100:+.1f}%"
        lines.append(
            f"| `{r.id}` | {format_seconds(r.baseline)} | {format_seconds(r.current)} "
            f"| {delta} | {_STATUS_LABEL[r.status]} |"
        )
    return "\n".join(lines) + "\n"


def report_markdown(data: dict[str, Any]) -> str:
    """Single-run table (no baseline)."""
    lines = [
        "### BrowserGym benchmarks",
        "",
        f"- env: {_env_line(data.get('metadata', {}))}",
        "",
        "| Benchmark | Median | Min | p95 | Rounds | Page |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in data["results"]:
        s, p = r["stats"], r.get("params", {})
        page = f"{p['dom_nodes']} nodes" if "dom_nodes" in p else ""
        lines.append(
            f"| `{r['id']}` | {format_seconds(s['median'])} | {format_seconds(s['min'])} "
            f"| {format_seconds(s['p95'])} | {r['rounds']} | {page} |"
        )
    return "\n".join(lines) + "\n"
