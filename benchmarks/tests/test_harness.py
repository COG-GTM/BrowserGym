"""Fast, browser-free tests for the benchmark harness."""

import json
import time
import urllib.request
from html.parser import HTMLParser

import pytest

from benchmarks import compare
from benchmarks.cli import main
from benchmarks.harness import Runner, format_seconds, measure, summarize
from benchmarks.pages import SIZES, generate_page, write_pages
from benchmarks.server import StaticServer


class _Counter(HTMLParser):
    VOID = {"meta", "input", "br", "img", "link"}

    def __init__(self):
        super().__init__()
        self.count = 0

    def handle_starttag(self, tag, attrs):
        self.count += 1


def _count_elements(html: str) -> int:
    c = _Counter()
    c.feed(html)
    return c.count


def test_summarize():
    s = summarize([3.0, 1.0, 2.0, 4.0])
    assert s["min"] == 1.0 and s["max"] == 4.0
    assert s["median"] == 2.5 and s["mean"] == 2.5
    assert s["p95"] == 4.0
    assert summarize([1.0])["stdev"] == 0.0
    with pytest.raises(ValueError):
        summarize([])


def test_measure_runs_setup_and_teardown_per_round():
    calls = []
    samples = measure(
        lambda st: calls.append(("fn", st)),
        rounds=3,
        warmup=2,
        setup=lambda: len(calls),
        teardown=lambda st: calls.append(("td", st)),
    )
    assert len(samples) == 3
    assert sum(1 for c in calls if c[0] == "fn") == 5
    assert sum(1 for c in calls if c[0] == "td") == 5


def test_runner_filter_and_rounds():
    r = Runner(scale=0.2, patterns=["obs.*[large]"], verbose=False)
    assert r.selected("obs", "axtree", "large")
    assert not r.selected("obs", "axtree", "small")
    assert r.rounds_for(20) == 4 and r.rounds_for(3) == 2
    assert r.bench("obs", "x", "small", lambda _: None, rounds=5) is None
    res = r.bench("obs", "x", "large", lambda _: None, rounds=5, warmup=0)
    assert res.id == "obs.x[large]" and res.rounds == 2
    assert Runner(rounds_override=7, verbose=False).rounds_for(100) == 7


@pytest.mark.parametrize("size", list(SIZES))
def test_page_sizes_close_to_target(size):
    target = SIZES[size]
    html = generate_page(target)
    assert html == generate_page(target)  # deterministic
    n = _count_elements(html)
    assert abs(n - target) <= max(12, 0.02 * target), (size, n)
    for marker in ('id="bench-input"', 'id="bench-button"', 'id="bench-link"'):
        assert marker in html


def test_static_server_serves_pages(tmp_path):
    paths = write_pages(tmp_path, {"tiny": 50})
    with StaticServer(tmp_path) as server:
        body = urllib.request.urlopen(server.url("tiny.html"), timeout=5).read().decode()
    assert body == paths["tiny"].read_text()


def _result_file(path, values):
    data = {
        "schema_version": 1,
        "metadata": {"cpu": "test", "python": "3"},
        "results": [
            {"id": k, "rounds": 3, "stats": {"median": v, "mean": v, "min": v, "p95": v}}
            for k, v in values.items()
        ],
    }
    path.write_text(json.dumps(data))
    return path


def test_compare_statuses():
    base = {
        "results": [
            {"id": i, "stats": {"median": v}}
            for i, v in [("a", 1.0), ("b", 1.0), ("c", 1.0), ("gone", 1.0)]
        ]
    }
    cur = {
        "results": [
            {"id": i, "stats": {"median": v}}
            for i, v in [("a", 1.1), ("b", 2.0), ("c", 0.5), ("new", 1.0)]
        ]
    }
    rows = {r.id: r for r in compare.compare(base, cur, threshold=0.25)}
    assert rows["a"].status == "ok"
    assert rows["b"].status == "regression" and rows["b"].ratio == pytest.approx(2.0)
    assert rows["c"].status == "improvement"
    assert rows["new"].status == "new" and rows["gone"].status == "missing"
    md = compare.to_markdown(list(rows.values()))
    assert "| `b` | 1.00 s | 2.00 s | +100.0% | **REGRESSION** |" in md


def test_compare_cli(tmp_path, capsys):
    base = _result_file(tmp_path / "base.json", {"x[small]": 0.010, "y[small]": 0.5})
    cur = _result_file(tmp_path / "cur.json", {"x[small]": 0.020, "y[small]": 0.5})
    out_md = tmp_path / "cmp.md"
    assert main(["compare", str(base), str(cur), "--markdown", str(out_md)]) == 0
    assert main(["compare", str(base), str(cur), "--fail-on-regression"]) == 1
    assert main(["compare", str(base), str(base), "--fail-on-regression"]) == 0
    assert "10.00 ms" in out_md.read_text()
    assert "REGRESSION" in capsys.readouterr().out


def test_format_seconds():
    assert format_seconds(None) == "-"
    assert format_seconds(2.5) == "2.50 s"
    assert format_seconds(0.0123) == "12.30 ms"
    assert format_seconds(0.0000123) == "12.3 µs"


def test_runner_watchdog_fires_on_slow_benchmark():
    fired = []
    runner = Runner(verbose=False, timeout=0.05, on_timeout=fired.append)
    runner.bench("g", "slow", "small", lambda _: time.sleep(0.1), rounds=1, warmup=0)
    runner.bench("g", "fast", "small", lambda _: None, rounds=2, warmup=0)
    time.sleep(0.1)
    assert fired == ["g.slow[small]"]
