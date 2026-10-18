# Side — architecture & contracts

Side is a product layer on top of BrowserGym: launch BrowserGym episodes (agent + task),
watch them live, and replay their traces from the web or a phone.

All Side work lands on the `side/main` integration branch (PRs target `side/main`, not `main`).

## Layout (each directory is owned by one workstream)

| Path | What | Stack |
|---|---|---|
| `contracts/openapi.yaml` | **Source of truth** REST + SSE contract | OpenAPI 3.1 |
| `apps/api/` | Side API server implementing the contract | Python 3.11+, FastAPI, SQLite (SQLModel) |
| `services/runner/` | `side_runner` — executes one BrowserGym episode, writes the artifact layout | Python, browsergym |
| `services/notifications/` | Expo push notifications on run status changes | Python, FastAPI |
| `apps/web/` | Side web app | Next.js (App Router), TypeScript, Tailwind |
| `packages/trace-viewer/` | React components for step replay | React, TypeScript, Storybook |
| `packages/design-tokens/` | Side brand tokens → CSS vars, Tailwind preset, RN theme | Style Dictionary |
| `apps/mobile/` | Side mobile app | Expo (React Native), TypeScript, Expo Router |
| `deploy/` | Dockerfiles, docker-compose, image CI | Docker |
| `benchmarks/` | Performance benchmark harness for BrowserGym | Python, pytest-benchmark |
| `e2e/` | End-to-end tests for web + API | Playwright Test |

## Runner contract (`services/runner` <-> `apps/api`)

The API launches one runner process per run:

```
python -m side_runner --run-id <id> --task <gym_id> --agent-json '<AgentConfig JSON>' \
  --max-steps <n> --data-dir <SIDE_DATA_DIR> [--goal <text>] [--start-url <url>] [--headless/--no-headless]
```

Chat messages from users are delivered by appending JSON lines `{"role":"user","message":...,"timestamp":...}` to
`<data-dir>/runs/<id>/inbox.jsonl`; the runner polls it between steps.
Cancellation: the API creates `<data-dir>/runs/<id>/CANCEL`; the runner stops after the current step.

## Artifact layout (`SIDE_DATA_DIR`, default `./.side-data`)

```
runs/<run_id>/run.json          # Run object (contract schema), rewritten on every status change
runs/<run_id>/steps/<n>.json    # StepDetail object (contract schema), n = 0..N
runs/<run_id>/steps/<n>.png     # screenshot for step n (optional)
runs/<run_id>/chat.jsonl        # ChatMessage per line (assistant/info/infeasible + echoed user)
runs/<run_id>/events.jsonl      # RunEvent per line, append-only (API tails this for SSE)
runs/<run_id>/inbox.jsonl       # user -> agent messages
runs/<run_id>/CANCEL            # cancel marker
```

## Notifications contract

If `SIDE_NOTIFY_URL` is set, the API POSTs every `status` RunEvent as JSON to `${SIDE_NOTIFY_URL}/internal/run-events`.
`services/notifications` serves `POST /api/v1/devices` (contract) and `POST /internal/run-events`.

## Agents

`mock` — deterministic, no network (noop/scroll then `send_msg_to_user`), used by every test and demo.
`scripted` — replays a list of actions. `openai` / `anthropic` — LLM agents (need `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`).

## Mock mode

Every client (web, mobile, e2e) must run without a backend via `NEXT_PUBLIC_SIDE_MOCK=1` / `EXPO_PUBLIC_SIDE_MOCK=1`
using fixtures that conform to `contracts/openapi.yaml`. Default ports: API 8000, notifications 8010, web 3000.
