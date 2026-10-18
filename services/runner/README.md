# side_runner

Executes **one** BrowserGym episode (task + agent) and writes the Side artifact layout described in
[`docs/side/ARCHITECTURE.md`](../../docs/side/ARCHITECTURE.md), using the schemas in
[`contracts/openapi.yaml`](../../contracts/openapi.yaml).

## Install

```bash
pip install -e ./browsergym/core            # local browsergym-core (or from PyPI)
pip install -e './services/runner[test]'     # extras: miniwob, openai, anthropic, test
playwright install chromium
```

## CLI (runner contract)

```bash
python -m side_runner --run-id <id> --task <gym_id> --agent-json '<AgentConfig JSON>' \
  --max-steps <n> --data-dir <SIDE_DATA_DIR> [--goal <text>] [--start-url <url>] [--headless/--no-headless]
```

Optional extras: `--seed`, `--slow-mo <ms>`, `--timeout <ms>` (Playwright overrides), `--log-level`.
`--data-dir` defaults to `$SIDE_DATA_DIR` or `./.side-data`. The `side-runner` console script is equivalent.

Exit code: `0` when the run ends `succeeded` or `cancelled`, `1` when `failed`, `2` on bad arguments.
The source of truth for the outcome is always `run.json`.

Example (offline):

```bash
python -m side_runner --run-id demo1 --task browsergym/openended --agent-json '{"type":"mock"}' \
  --max-steps 10 --data-dir ./.side-data --goal "Say done" --start-url https://example.com
```

## Artifacts

```
runs/<run_id>/run.json          Run; rewritten on every status change and after every step (n_steps, reward)
runs/<run_id>/steps/<n>.json    StepDetail
runs/<run_id>/steps/<n>.png     screenshot of step n (viewport)
runs/<run_id>/chat.jsonl        ChatMessage per line
runs/<run_id>/events.jsonl      RunEvent per line (status / step / chat / log)
runs/<run_id>/inbox.jsonl       read: {"role":"user","message":...,"timestamp":...}, polled between steps
runs/<run_id>/CANCEL            read: stop after the current step -> status cancelled
```

Semantics:

- **Steps.** `steps/0` is the observation right after `env.reset()` (`action: null`). `steps/k` (k >= 1) is
  the result of the k-th agent action: the action, the agent's `thought`, reward, flags,
  `last_action_error`, and the observation (URL, AXTree, pruned HTML, focused bid, screenshot) *after*
  executing it. `elapsed_ms` = agent decision + action execution + observation extraction (reset time
  for step 0). `Run.n_steps` = number of actions executed, so files are `0..n_steps`.
  `screenshot_url` is `/runs/<id>/steps/<n>/screenshot` (relative to the API base path).
  `step` events carry the `Step` view (no AXTree/HTML); the detail lives in `steps/<n>.json`.
- **Status.** `queued` (written only if `run.json` doesn't exist yet; an existing `run.json` from the API
  is reused and its `created_at` kept) -> `running` -> `succeeded | failed | cancelled`. `failed` carries
  `error` (`"<ExceptionType>: <message>"`) and the traceback is emitted as a `log` event.
  An episode ends when the task terminates, the agent says it is done (mock: after
  `send_msg_to_user('done')`; scripted: after the last action; LLM agents: after `send_msg_to_user` /
  `report_infeasible`), or `max_steps` is reached (last step has `truncated: true`; still `succeeded`).
- **Chat.** Mirrors the BrowserGym chat: greeting + goal at reset, `assistant` messages from
  `send_msg_to_user`, `infeasible` from `report_infeasible`, and echoed `user` messages from the inbox.
  The runner adds `info` messages when a run is cancelled or fails. On `browsergym/openended` a user
  message `exit` ends the episode (BrowserGym behaviour).
- **Cancel.** `CANCEL` (or SIGTERM/SIGINT) is checked between steps; a CANCEL present at start cancels the
  run before a browser is launched.

## Agents (`agent-json`)

All agents use BrowserGym's `HighLevelActionSet(subsets=["chat", "tab", "nav", "bid", "infeas"])`.

| type | config | notes |
|---|---|---|
| `mock` | optional `delay_ms`, `fail_at_step`, `final_message` | deterministic, offline: `noop(200)`, `scroll(0, 200)`, `send_msg_to_user('done')`; acknowledges inbox messages with `Received: <msg>` |
| `scripted` | `actions: ["click('a12')", ...]` | replays the actions then stops |
| `openai` | `model` (default `$SIDE_OPENAI_MODEL` or `gpt-4o-mini`), `use_axtree`, `use_screenshot` | needs `OPENAI_API_KEY`, extra `[openai]` |
| `anthropic` | `model` (default `$SIDE_ANTHROPIC_MODEL` or `claude-sonnet-4-5`), `use_axtree`, `use_screenshot` | needs `ANTHROPIC_API_KEY`, extra `[anthropic]` |

LLM agents prompt in the style of `demo_agent/` (goal, chat, open tabs, AXTree or pruned HTML,
optional screenshot, action space, history, last error) and execute the last fenced code block of the answer.
Register custom agents with `side_runner.agents.register_agent(type, factory)`.

## Tasks

Any registered BrowserGym gym id. The matching package is imported from the id
(`browsergym/miniwob.click-test` -> `browsergym.miniwob`). `browsergym/openended` requires `--start-url`.
MiniWoB needs `MINIWOB_URL` (`make setup-miniwob` at the repo root).

## Tests

```bash
cd services/runner && pytest -v           # browser tests run headless Chromium
MINIWOB_URL=file:///path/to/miniwob-plusplus/miniwob/html/miniwob/ pytest -v -m miniwob
```

Artifacts are validated against the component schemas of `contracts/openapi.yaml`.
