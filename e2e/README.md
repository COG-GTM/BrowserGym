# Side e2e

End-to-end tests for Side (web + API) with [Playwright Test](https://playwright.dev/docs/test-intro), written against
[`contracts/openapi.yaml`](../contracts/openapi.yaml) and runnable today without a backend.

| Project | What | Target |
|---|---|---|
| `api` | Contract tests: every operation, every declared status code, ajv (JSON Schema 2020-12) validation of every response against the contract, SSE event shapes and stream lifecycle, mock-fixture conformance | `E2E_API_URL` (default: local contract mock) |
| `web` | User journeys via `data-testid`: create run → watch live → open step → send chat → cancel; runs list filtering; tasks search | `E2E_BASE_URL` (default `http://localhost:3000`); skipped with a clear message if unreachable |

## Quick start

```bash
cd e2e
npm ci
npx playwright install chromium   # only needed for the web project

npm run test:api                  # starts the contract mock automatically, runs the api project
npm run test:web                  # against apps/web on :3000 (skips if it isn't running)
npm run test:web:reference        # web journeys against the bundled reference UI (see below)
npm run report                    # open the HTML report
```

### Against a real backend

```bash
E2E_API_URL=http://localhost:8000/api/v1 npm run test:api        # live mode: also asserts state (create→get, cancel, delete→404, chat echo, filtering)
E2E_BASE_URL=http://localhost:3000 npm run test:web
```

| Env var | Default | Meaning |
|---|---|---|
| `E2E_API_URL` | `http://127.0.0.1:4000/api/v1` | API base incl. `/api/v1`. Setting it disables the auto-started mock and enables **live** assertions. |
| `E2E_API_MODE` | `mock` unless `E2E_API_URL` is set | Force `mock` to point at an externally started mock. |
| `E2E_NO_MOCK` | unset | Don't auto-start the mock (e.g. you run `npm run mock` yourself). |
| `E2E_RUN_TASK_ID` / `E2E_RUN_START_URL` | `browsergym/openended` / `about:blank` | Task used for live-mode runs (mock agent, offline). |
| `E2E_BASE_URL` | `http://localhost:3000` | Side web app. |
| `E2E_TASK_ID` | `browsergym/miniwob.click-test` | Task the web journey creates a run for. |
| `E2E_TASK_QUERY` | `click` | Search term for the tasks journey (must match some but not all tasks). |
| `SSE_DELAY_MS` | `50` (tests) / `250` (manual) | Delay between fake SSE events. |

## Mock (`e2e/mock/`)

`npm run mock` starts both pieces (Playwright starts them automatically for tests):

- **Prism** (`@stoplight/prism-cli`) on `:4010` mocking `contracts/openapi.yaml` (request validation → 422, `Prefer: code=404` to pick a status).
- **Gateway** (`mock/gateway.mjs`) on `:4000`:
  - `GET /api/v1/runs/{id}/events` → fixture-driven fake SSE server replaying `mock/fixtures/events/*.json`
    (`<run_id>.json` if present, `failed.json` for ids starting with `fail`, else `default.json`; `run_id`/`timestamp` filled in;
    `event:` = `RunEvent.type`; closes after the terminal `status`). `?delay_ms=` overrides the pacing.
  - `GET /api/v1/runs/{id}/steps/{n}/screenshot` → a real PNG fixture.
  - other `/api/v1/*` → proxied to Prism.
  - everything else → the **reference UI** (`mock/reference-web/`), a ~250-line vanilla JS app that implements the
    `data-testid` contract below. It exists only so the web journeys are executable before `apps/web` lands; it is not the product.

`mock/fixtures/{tasks,agents,runs}.json` are contract-valid sample data (checked by `tests/api/fixtures.spec.ts`); `apps/web` /
`apps/mobile` mock mode may reuse them.

## `data-testid` contract for apps/web

The web project only uses these selectors (plus URL `/runs/<id>` after creating a run). Navigation starts at `/` and goes
through the nav links, so other route names are free. Attributes in brackets are required on the same element.

| Area | `data-testid` | Element / notes |
|---|---|---|
| Global nav | `nav-runs`, `nav-tasks`, `nav-new-run` | links, present on every page |
| Runs list | `runs-status-filter` | **native `<select>`**: option `""` = all, plus one option per `RunStatus` value |
| | `runs-list` | list/table container |
| | `run-row` `[data-run-id, data-status]` | one per run; click → run detail |
| | `run-row-status` | status badge inside a row |
| | `runs-empty` | shown when the filter matches nothing |
| New run | `new-run-form` | the form |
| | `task-search-input` | text input filtering task options |
| | `task-option` `[data-task-id]` | clickable task option |
| | `selected-task` `[data-task-id]` | reflects the chosen task |
| | `agent-select` | **native `<select>`**, option values = `AgentConfig.type` (`mock`, …) |
| | `goal-input`, `start-url-input`, `max-steps-input` | optional inputs (filled when visible) |
| | `create-run-submit` | submit; navigates to `/runs/<id>` |
| Run detail | `run-detail` `[data-run-id]` | page root |
| | `run-status` `[data-status]` | live `RunStatus` |
| | `live-indicator` | visible only while the SSE stream is connected and the run is non-terminal |
| | `step-list` | container |
| | `step-item` `[data-step-index]` | one per step, appended live from SSE `step` events; click opens detail |
| | `step-detail` `[data-step-index]` | selected step panel |
| | `step-action` | action string inside `step-detail` (non-empty) |
| | `step-thought`, `step-screenshot` | optional, inside `step-detail` |
| | `chat-panel` | container |
| | `chat-message` `[data-role]` | one per `ChatMessage`; `data-role` = `user`/`assistant`/`info`/`infeasible`; a sent message appears immediately (optimistic or echoed) |
| | `chat-input`, `chat-send` | input is cleared after sending |
| | `run-cancel` | button; after click `run-status` becomes `cancelled`, button disabled, `live-indicator` hidden |
| Tasks | `tasks-search-input` | text input (searches id/title/description) |
| | `task-row` `[data-task-id, data-benchmark]` | one per task |
| | `tasks-empty` | shown when the search matches nothing |

Mock-mode expectations for apps/web (`NEXT_PUBLIC_SIDE_MOCK=1`): at least one run in the list; a task with id
`E2E_TASK_ID`; the `mock` agent; a newly created mock run stays non-terminal for ≥ ~5 s and emits ≥ 2 steps so the journey
can watch and cancel it.

## Layout

```
e2e/
  playwright.config.ts        projects api + web, auto-starts the mock
  support/                    env, contract (ajv), api helpers, SSE parser, web reachability guard
  tests/api/                  contract tests (coverage.spec.ts fails if an operation/status is untested)
  tests/web/                  user journeys
  mock/                       gateway.mjs, start.mjs, fixtures/, reference-web/
```

CI: [`.github/workflows/side-e2e.yml`](../.github/workflows/side-e2e.yml) runs the `api` project against the mock and uploads the HTML report.
