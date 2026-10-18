# Side API (`apps/api`)

FastAPI server implementing [`contracts/openapi.yaml`](../../contracts/openapi.yaml) under `/api/v1`:
launch BrowserGym runs, stream them live over SSE, and replay their traces.

- **Run index**: SQLite via SQLModel (`$SIDE_DATA_DIR/side.db`) — list/filter/paginate runs.
- **Source of truth for traces**: the artifact layout from `docs/side/ARCHITECTURE.md`
  (`$SIDE_DATA_DIR/runs/<id>/{run.json,steps/<n>.json,steps/<n>.png,chat.jsonl,events.jsonl,inbox.jsonl,CANCEL}`).
- **Runner**: `POST /runs` persists the run, then spawns `python -m side_runner ...` per the runner
  contract (owned by `services/runner`). `SIDE_RUNNER_CMD` overrides the command;
  `SIDE_FAKE_RUNNER=1` uses the built-in in-process FakeRunner so everything works offline
  without browsergym/Playwright.

## Run

Requires Python 3.11+.

```bash
cd apps/api
python3.11 -m venv .venv && . .venv/bin/activate   # or: uv venv -p 3.12 .venv
pip install -e '.[dev]'                            # add '.[browsergym]' to list real gym ids

SIDE_FAKE_RUNNER=1 uvicorn side_api.main:app --port 8000
```

Open http://localhost:8000/api/v1/docs, or:

```bash
RUN=$(curl -s -X POST localhost:8000/api/v1/runs -H 'content-type: application/json' \
  -d '{"task_id":"browsergym/openended","agent":{"type":"mock"},"goal":"Find the pricing page","start_url":"https://example.com"}')
ID=$(echo "$RUN" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
curl -N localhost:8000/api/v1/runs/$ID/events          # SSE, closes after the terminal status
curl -o step2.png localhost:8000/api/v1/runs/$ID/steps/2/screenshot
curl -X POST localhost:8000/api/v1/runs/$ID/chat -H 'content-type: application/json' -d '{"message":"hi"}'
curl -X POST localhost:8000/api/v1/runs/$ID/cancel
```

Example SSE output (FakeRunner, trimmed):

```
id: 1
event: status
data: {"type":"status","run_id":"38af…","timestamp":"2026-10-18T02:42:24.525Z","status":"queued"}

id: 6
event: step
data: {"type":"step","run_id":"38af…","step":{"index":0,"action":null,…,"screenshot_url":"/api/v1/runs/38af…/steps/0/screenshot",…}}

id: 16
event: status
data: {"type":"status","run_id":"38af…","timestamp":"2026-10-18T02:42:26.553Z","status":"succeeded"}
```

## Configuration

| Env var | Default | Meaning |
| --- | --- | --- |
| `SIDE_DATA_DIR` | `./.side-data` | Artifact root (shared with the runner) and SQLite location |
| `SIDE_DB_URL` | `sqlite:///$SIDE_DATA_DIR/side.db` | Override the run-index DB URL |
| `SIDE_FAKE_RUNNER` | off | `1` = in-process FakeRunner (ignored if `SIDE_RUNNER_CMD` is set) |
| `SIDE_FAKE_STEP_DELAY` | `0.5` | Seconds between FakeRunner steps |
| `SIDE_RUNNER_CMD` | `python -m side_runner` | Runner command prefix; runner-contract args are appended |
| `SIDE_NOTIFY_URL` | unset | Empty/unset disables forwarding. If set, every `status` event is POSTed to `${SIDE_NOTIFY_URL}/internal/run-events`, and `POST /devices` is forwarded to `${SIDE_NOTIFY_URL}/api/v1/devices` |
| `SIDE_CORS_ORIGINS` | – | Extra comma-separated origins (localhost:3000 and Expo 8081/19000/19006 are always allowed) |
| `SIDE_CONTRACT_PATH` | auto (`contracts/openapi.yaml` in an ancestor dir) | Contract served at `/api/v1/openapi.json` |

LLM agents (`openai`, `anthropic`) are listed by `GET /agents`; the runner reads
`OPENAI_API_KEY` / `ANTHROPIC_API_KEY` from its environment — the API never sees or stores keys.

## FakeRunner

`side_api/fake_runner.py` writes the same artifacts a real runner would: `run.json`, per-step JSON
(with AXTree / pruned HTML), generated PNG screenshots, chat, and events. It mimics the `mock` agent
(`noop` → `scroll` → `click` → `send_msg_to_user`), honours `CANCEL`, and supports goal markers
`[fail]` (runner error) and `[infeasible]` (`report_infeasible`). It also runs as a subprocess speaking
the runner contract, handy for exercising the `SIDE_RUNNER_CMD` path:

```bash
SIDE_RUNNER_CMD="python -m side_api.fake_runner" uvicorn side_api.main:app --port 8000
```

### Running behind a proxy / in containers

- Uvicorn honours `X-Forwarded-*` headers from the IPs in `FORWARDED_ALLOW_IPS` (default `127.0.0.1`). The API itself never uses the client address, so this only affects request URLs and logs.
- The API runs as any UID (e.g. 1001 in `deploy/`). It needs write access to `SIDE_DATA_DIR`, where it creates `runs/` and the SQLite index (`side.db`, WAL mode) at startup.

## Tests

```bash
pytest -q          # every endpoint incl. SSE, against the FakeRunner; responses validated with openapi-core
ruff check . && ruff format --check . && mypy side_api
```

Responses are validated against `contracts/openapi.yaml` (`tests/conftest.py::Contract`); FastAPI
validation errors (`422`) are asserted separately where the contract doesn't declare them.
