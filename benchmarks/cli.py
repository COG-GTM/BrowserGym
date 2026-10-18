"""``python -m benchmarks {run,compare,report}``."""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.metadata
import json
import logging
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from . import compare as compare_mod
from .harness import Runner

SCHEMA_VERSION = 1
PROFILES = {"full": 1.0, "quick": 0.2}


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def _git_sha() -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _version(dist: str) -> Optional[str]:
    try:
        return importlib.metadata.version(dist)
    except importlib.metadata.PackageNotFoundError:
        return None


def _measure_pages(ctx) -> Optional[str]:
    """Count DOM element nodes per page; returns the chromium version."""
    from browsergym.core import _get_global_playwright

    pw = _get_global_playwright()
    browser = pw.chromium.launch(headless=ctx.headless)
    try:
        page = browser.new_page()
        for size, info in ctx.pages.items():
            page.goto(info.url)
            ctx.measured_nodes[size] = page.evaluate(
                "() => document.getElementsByTagName('*').length"
            )
        return browser.version
    finally:
        browser.close()


def _results_doc(args, runner, ctx, chromium, sizes, suites, total, aborted=None) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "git_sha": _git_sha(),
        "python": platform.python_version(),
        "platform": f"{platform.system()}-{platform.release()}-{platform.machine()}",
        "cpu": _cpu_model(),
        "cpu_count": os.cpu_count(),
        "playwright": _version("playwright"),
        "chromium": chromium,
        "browsergym_core": _version("browsergym-core"),
        "profile": args.profile,
        "rounds_override": args.rounds,
        "suites": suites,
        "sizes": sizes,
        "dom_nodes": ctx.measured_nodes,
        "filter": args.filter,
        "headless": not args.headed,
        "aborted_at": aborted,
        "total_seconds": round(total, 2) if total is not None else None,
    }
    data = {
        "schema_version": SCHEMA_VERSION,
        "metadata": metadata,
        "results": [r.to_dict() for r in runner.results],
    }
    return data


def cmd_run(args: argparse.Namespace) -> int:
    from .context import Context, PageInfo
    from .pages import SIZES, write_pages
    from .server import StaticServer
    from .suites import SUITES

    # BrowserEnv warns on every reset that our viewport/timeout override the task's values
    logging.getLogger("browsergym").setLevel(logging.ERROR)
    sizes = {s: SIZES[s] for s in args.sizes}
    suites = args.suites or list(SUITES)
    runner = Runner(
        scale=PROFILES[args.profile],
        rounds_override=args.rounds,
        patterns=args.filter,
        timeout=args.timeout,
    )

    with tempfile.TemporaryDirectory(prefix="bgym-bench-") as tmp:
        tmp = Path(tmp)
        page_dir = tmp / "pages"
        write_pages(page_dir, sizes)
        with StaticServer(page_dir) as server:
            ctx = Context(
                pages={
                    s: PageInfo(size=s, target_nodes=n, url=server.url(f"{s}.html"))
                    for s, n in sizes.items()
                },
                workdir=tmp / "work",
                headless=not args.headed,
            )
            ctx.workdir.mkdir()
            chromium = _measure_pages(ctx)

            def abort(bench_id: str) -> None:
                print(
                    f"!! {bench_id} exceeded --timeout {args.timeout:g}s (renderer crash?), aborting",
                    file=sys.stderr,
                    flush=True,
                )
                if args.json:
                    doc = _results_doc(args, runner, ctx, chromium, sizes, suites, None, bench_id)
                    Path(args.json).write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
                os._exit(3)

            runner.on_timeout = abort
            print(
                f"pages: {ctx.measured_nodes} | profile={args.profile} suites={suites}",
                file=sys.stderr,
            )
            t0 = time.perf_counter()
            for name in suites:
                print(f"[{name}]", file=sys.stderr, flush=True)
                SUITES[name].run(runner, ctx)
            total = time.perf_counter() - t0

    data = _results_doc(args, runner, ctx, chromium, sizes, suites, total)
    if not runner.results:
        print("no benchmark matched the filter", file=sys.stderr)
        return 2
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(data, indent=2) + "\n", "utf-8")
        print(f"wrote {len(runner.results)} results to {args.json}", file=sys.stderr)
    print(compare_mod.report_markdown(data))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    baseline = compare_mod.load(args.baseline)
    current = compare_mod.load(args.current)
    rows = compare_mod.compare(baseline, current, threshold=args.threshold, stat=args.stat)
    md = compare_mod.to_markdown(
        rows,
        baseline_meta=baseline.get("metadata"),
        current_meta=current.get("metadata"),
        threshold=args.threshold,
        stat=args.stat,
    )
    if args.markdown:
        Path(args.markdown).write_text(md, "utf-8")
    print(md)
    if args.fail_on_regression and any(r.status == "regression" for r in rows):
        return 1
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    print(compare_mod.report_markdown(compare_mod.load(args.results)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    from .pages import SIZES

    parser = argparse.ArgumentParser(prog="python -m benchmarks", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the benchmark suite")
    run.add_argument("--json", help="write results to this JSON file")
    run.add_argument(
        "--suite",
        dest="suites",
        action="append",
        choices=["env", "step", "obs", "steps_io"],
        help="suite(s) to run (repeatable, default: all)",
    )
    run.add_argument(
        "--size",
        dest="sizes",
        action="append",
        choices=list(SIZES),
        help="page size(s) to use (repeatable, default: all)",
    )
    run.add_argument(
        "-k",
        "--filter",
        action="append",
        help="only run benchmark ids matching this glob/substring, e.g. 'obs.*[large]' (repeatable)",
    )
    run.add_argument(
        "--profile",
        choices=list(PROFILES),
        default="full",
        help="'quick' runs ~20%% of the rounds (smoke test)",
    )
    run.add_argument("--rounds", type=int, help="force this many timed rounds per benchmark")
    run.add_argument(
        "--timeout",
        type=float,
        default=900.0,
        help="abort (exit 3, partial JSON) if one benchmark takes longer than this many seconds",
    )
    run.add_argument("--headed", action="store_true", help="show the browser (debug only)")
    run.set_defaults(func=cmd_run)

    cmp = sub.add_parser("compare", help="markdown table of current vs baseline results")
    cmp.add_argument("baseline")
    cmp.add_argument("current")
    cmp.add_argument("--threshold", type=float, default=compare_mod.DEFAULT_THRESHOLD)
    cmp.add_argument(
        "--stat", default=compare_mod.DEFAULT_STAT, choices=["median", "mean", "min", "p95"]
    )
    cmp.add_argument("--markdown", help="also write the table to this file")
    cmp.add_argument(
        "--fail-on-regression", action="store_true", help="exit 1 if any regression is found"
    )
    cmp.set_defaults(func=cmd_compare)

    rep = sub.add_parser("report", help="markdown table for a single results file")
    rep.add_argument("results")
    rep.set_defaults(func=cmd_report)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    from .pages import SIZES

    args = build_parser().parse_args(argv)
    if args.command == "run":
        args.sizes = args.sizes or list(SIZES)
    return args.func(args)
