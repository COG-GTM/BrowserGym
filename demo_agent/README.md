# BrowserGym demo agent

A basic reference agent that drives a BrowserGym environment with an LLM (OpenAI or Anthropic), or
with a deterministic offline mock LLM for demos and tests. For more capable agents see
[AgentLab](https://github.com/ServiceNow/AgentLab).

## Install

```sh
pip install -r requirements.txt     # or: conda env create -f environment.yml && conda activate demo-agent
playwright install chromium
```

## Quick start (no API key)

```sh
python run_demo.py --dry-run
```

`--dry-run` swaps the LLM for a deterministic mock (scroll, noop, then `send_msg_to_user` with a
summary of the page), runs headless on the bundled local page `pages/dry_run.html` with a fixed
goal, and makes no network calls. Results (screenshots, step pickles, `experiment.log`) are written
to `./results/<timestamp>_DemoAgentArgs_on_openended_<seed>/`.

## Running with a real LLM

```sh
export OPENAI_API_KEY=...                        # provider "openai" (default)
python run_demo.py                               # interactive chat on https://www.google.com

export ANTHROPIC_API_KEY=...
python run_demo.py run --provider anthropic --model claude-haiku-4-5 \
    --start-url https://example.com --goal "What is the page heading?" --headless
```

- Without `--goal`, the openended task opens a chat window and waits for your instructions.
- With `--goal`, the agent runs autonomously and stops after it answers you (`send_msg_to_user`).
- Any other BrowserGym task can be run with `--task <gym id>` (e.g. `miniwob.click-test`, with the
  matching benchmark package installed).

## CLI

```
python run_demo.py [run] [options]    # 'run' is the default subcommand
python run_demo.py models             # default models + pricing table used for cost logs
```

| Option | Env var | Default |
|---|---|---|
| `--provider {openai,anthropic,mock}` | `DEMO_AGENT_PROVIDER` | `openai` |
| `--model` | `DEMO_AGENT_MODEL` | `gpt-5-mini` / `claude-sonnet-4-5` / `mock-deterministic` |
| `--max-retries` | `DEMO_AGENT_MAX_RETRIES` | `4` |
| `--dry-run` | | off (mock LLM, local page, headless, 10 steps) |
| `--task` | | `openended` |
| `--start-url`, `--goal` | | `https://www.google.com`, none |
| `--max-steps`, `--seed` | | `100`, random |
| `--headless/--no-headless` | | headed (headless with `--dry-run`) |
| `--visual-effects/--no-visual-effects` | | on |
| `--use-axtree`, `--use-html`, `--use-screenshot` (and `--no-*`) | | axtree only |
| `--results-dir` | | `./results` |
| `--log-level` | `DEMO_AGENT_LOG_LEVEL` | `INFO` (`DEBUG` also logs full prompts) |

Old snake_case flags `--model_name`, `--task_name` and `--start_url` still work. The old
`--use_html true`-style boolean flags were replaced by `--use-html` / `--no-use-html`.

## Retries, tokens and cost

- Rate limits, timeouts, connection errors and 408/409/429/5xx responses are retried with
  exponential backoff and full jitter (`--max-retries`); other errors (e.g. 401) fail immediately.
- Every LLM call logs input/output tokens, latency, attempts and an estimated USD cost, plus running
  totals. Per-step values are stored in the step stats, so the final record shows
  `stats.cum_input_tokens`, `stats.cum_output_tokens` and `stats.cum_cost_usd`.
- Prices come from a small built-in table (`python run_demo.py models`). For other models set
  `DEMO_AGENT_PRICE_IN` / `DEMO_AGENT_PRICE_OUT` (USD per 1M tokens), otherwise cost is logged as
  `n/a`.

## Layout

| File | |
|---|---|
| `run_demo.py` | CLI |
| `agent.py` | `DemoAgent` / `DemoAgentArgs`: prompt building and action parsing |
| `llm.py` | OpenAI, Anthropic and mock providers, retries, token/cost tracking |
| `pages/dry_run.html` | offline page used by `--dry-run` |
| `tests/` | `pytest demo_agent/tests` (includes a headless end-to-end dry run) |
