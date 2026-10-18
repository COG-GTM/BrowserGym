# BrowserGym performance benchmarks

Offline, deterministic benchmark harness for `browsergym-core` / `browsergym-experiments`.
Everything runs against synthetic static pages served from `127.0.0.1` with headless Chromium;
no network access, API keys or external benchmarks are needed.

## Quick start

```bash
pip install -e browsergym/core -e browsergym/experiments tqdm
playwright install chromium

# full suite (~10 min on an 8-core VM), writes JSON + prints a markdown table
python -m benchmarks run --json out.json

# compare against the stored baseline (exit 1 on regression with --fail-on-regression)
python -m benchmarks compare benchmarks/baselines/baseline.json out.json --markdown cmp.md

# re-render a results file
python -m benchmarks report out.json
```

Useful `run` flags:

| Flag | Meaning |
|---|---|
| `--suite {env,step,obs,steps_io}` | run only some suites (repeatable) |
| `--size {small,medium,large}` | run only some page sizes (repeatable) |
| `-k PATTERN` | glob/substring on benchmark ids, e.g. `-k 'obs.*[large]'` (repeatable) |
| `--profile quick` | ~20% of the rounds, for smoke runs |
| `--rounds N` | force N timed rounds per benchmark |
| `--timeout S` | abort with exit code 3 (partial JSON written) if one benchmark exceeds S seconds (default 900) |

`compare` flags: `--threshold 0.25` (relative change that counts as a regression / improvement),
`--stat {median,mean,min,p95}` (default `median`), `--markdown FILE`, `--fail-on-regression`.

## What is measured

Benchmark ids are `<group>.<name>[<size>]`. Synthetic pages (`benchmarks/pages.py`) target
**100 / 2,000 / 20,000** element nodes (`small` / `medium` / `large`); the measured DOM node
count is recorded in each result's `params.dom_nodes`.

| Group | Benchmarks |
|---|---|
| `env` | `make` (gym.make only), `reset` (cold: launch chromium, open page, first obs), `make_reset_close` |
| `step` | `env.step` for `noop(0)`, `click`, `fill`, `scroll`, `goto` (includes post-action obs extraction) |
| `obs` | `pre_extract` (bid marking), `post_extract`, `dom_snapshot`, `axtree`, `focused_bid`, `extra_properties`, `screenshot`, `get_obs` (full `BrowserEnv._get_obs`), `flatten_axtree`, `flatten_dom`, `prune_html`, `som_overlay` |
| `steps_io` | `StepInfo.save_step_info` (`save`, `save_json`) and `ExpResult.get_step_info` (`load`) |

Environment settings used everywhere (`benchmarks/context.py`): `browsergym/openended` task,
headless, viewport 1280x720, `pre_observation_delay=0` and
`HighLevelActionSet(demo_mode="off")` so timings reflect real work rather than fixed sleeps or
demo cursor animations.

Each benchmark runs untimed warmup round(s) then N timed rounds with the Python GC disabled;
per-round setup/teardown is excluded from timings. Results report min / median / mean / stdev / p95.

Browser-side `step` / `obs` rounds force a renderer GC (`HeapProfiler.collectGarbage`) in their
untimed setup. Without it, back-to-back `dom_snapshot` + `axtree` extractions on the 20k-node page
pile up renderer garbage (each round slower than the last) until the tab crashes after ~4 rounds,
and Playwright calls on a crashed page block forever. A `page.on("crash")` hook prints
`!! renderer crashed (...)` and the `--timeout` watchdog turns any remaining hang into a failure.

## Baseline

`benchmarks/baselines/baseline.json` was produced on the dev VM listed in its `metadata`
(CPU, Python, Playwright/Chromium versions, git SHA). Absolute numbers are machine-specific:
compare runs from the same machine class, and regenerate the baseline when the reference
hardware or Playwright version changes:

```bash
python -m benchmarks run --json benchmarks/baselines/baseline.json
```

## CI

`.github/workflows/benchmarks.yml` runs on `workflow_dispatch` and on pull requests labelled
`benchmark`. It uploads the results JSON and comparison markdown as an artifact and writes the
comparison table to the job summary. Because GitHub runners differ from the baseline machine,
regressions only fail the job when `fail_on_regression` is set on a manual run.

## Tests

```bash
pytest benchmarks/tests -q   # harness unit tests + a 1-round smoke run of the real suites
```
