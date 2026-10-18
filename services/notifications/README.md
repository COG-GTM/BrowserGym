# side-notifications

Push notification backend for the Side mobile app. It stores Expo push tokens and, when the Side
API reports a terminal run status (`succeeded` / `failed` / `cancelled`), sends an Expo push
notification to every subscribed device.

Python 3.11+, FastAPI, SQLite (stdlib `sqlite3`), httpx. Default port **8010**.

## Run

```bash
cd services/notifications
uv venv -p 3.12 .venv && uv pip install -p .venv -e '.[dev]'   # or: python3.11 -m venv .venv && .venv/bin/pip install -e '.[dev]'

# offline / local dev: log push payloads instead of calling Expo
SIDE_PUSH_DRY_RUN=1 .venv/bin/python -m side_notifications          # http://localhost:8010
```

Point the API at it with `SIDE_NOTIFY_URL=http://localhost:8010` (see `docs/side/ARCHITECTURE.md`).

### Try it

```bash
# register a device (contract: POST /api/v1/devices, DeviceRegistration)
curl -s -XPOST localhost:8010/api/v1/devices -H 'content-type: application/json' \
  -d '{"expo_push_token":"ExponentPushToken[demo-123]","platform":"ios","run_ids":["run_abc"]}'

# what the API sends on a status change
curl -s -XPOST localhost:8010/internal/run-events -H 'content-type: application/json' \
  -d '{"type":"status","run_id":"run_abc","status":"succeeded","timestamp":"2026-10-18T02:40:00Z"}'
# -> {"accepted":true,"action":"queued","recipients":1,"reason":null}
# server log: DRY RUN (SIDE_PUSH_DRY_RUN=1): would POST 1 message(s) to https://exp.host/--/api/v2/push/send [...]

curl -s localhost:8010/internal/deliveries?run_id=run_abc
curl -s -XDELETE 'localhost:8010/api/v1/devices/ExponentPushToken%5Bdemo-123%5D'
```

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/health`, `/api/v1/health` | `{"status":"ok","version":...,"dry_run":...}` |
| POST | `/api/v1/devices` | `DeviceRegistration` → `201`. Re-registering a token **replaces** its platform and `run_ids`. `run_ids: []` (or omitted) = all runs. Tokens must look like `ExponentPushToken[...]` / `ExpoPushToken[...]`, else `422`. |
| DELETE | `/api/v1/devices/{token}` | URL-encode the token. Idempotent `204`. |
| POST | `/internal/run-events` | `RunEvent` JSON → `202 {"accepted","action","recipients","reason"}`. `action` is `queued` (terminal status, push sent in the background), `ignored` (non-status / non-terminal), or `duplicate` (this `run_id`+`status` was already notified). |
| POST | `/internal/receipts/check?min_age_s=` | Check Expo receipts for pending tickets now (also runs periodically). |
| GET | `/internal/deliveries?run_id=&limit=` | Delivery log (`dry_run` / `pending` / `ok` / `error` / `expired`). |

`/internal/*` requires header `X-Side-Notify-Secret: $SIDE_NOTIFY_SECRET` when that env var is set.
If it is unset the service logs a warning at startup; only run it that way on a private network
(e.g. the docker-compose network next to the API).

Device endpoints are unauthenticated (Side has no user auth yet): an Expo push token acts as a
bearer credential for its own registration.

## Push behaviour

- Message: `title` "Run succeeded|failed|cancelled", `body` "Run <id> <status>. Tap to replay the trace.",
  `data = {"type":"run_status","run_id","status","url":"side://runs/<id>"}` (deep link base via
  `SIDE_DEEP_LINK_BASE`), `sound: default`, `priority: high`.
- Batched to 100 messages per request to `https://exp.host/--/api/v2/push/send`.
- Retries 429 / any 5xx / transport errors with exponential backoff (honours `Retry-After`); other
  4xx are not retried. A batch that still fails is recorded as `error: RequestFailed` (tokens kept)
  and the run's dedupe claim is released, so a re-sent event retries just the tokens that never got
  a ticket (no double pushes).
- Tickets with `DeviceNotRegistered` prune the device immediately. Successful tickets are stored as
  `pending`; a background loop fetches receipts (`/push/getReceipts`, 1000 ids/request) for tickets
  older than `SIDE_PUSH_RECEIPT_MIN_AGE`, marks them `ok`/`error`, prunes `DeviceNotRegistered`
  tokens, and expires tickets whose receipt never shows up within 24h (only after a successful
  lookup; a failed receipts request just leaves tickets pending).
- Known limitation: background delivery is in-process (FastAPI `BackgroundTasks`). If the process
  dies between the 202 and the push, that event stays claimed and is not retried.

## Configuration

| Env | Default | |
|---|---|---|
| `SIDE_PUSH_DRY_RUN` | `0` | `1` = log payloads, never call Expo (tests always use dry run or mock Expo) |
| `SIDE_NOTIFY_SECRET` | unset | shared secret for `/internal/*` |
| `SIDE_NOTIFY_DB` | `$SIDE_DATA_DIR/notifications.db` (`./.side-data/notifications.db`) | SQLite file, or `:memory:` |
| `SIDE_NOTIFY_HOST` / `SIDE_NOTIFY_PORT` | `0.0.0.0` / `8010` | |
| `EXPO_ACCESS_TOKEN` | unset | sent as `Authorization: Bearer` if Expo enhanced push security is on |
| `SIDE_PUSH_MAX_RETRIES` | `3` | retries per request |
| `SIDE_PUSH_BACKOFF_BASE` / `SIDE_PUSH_BACKOFF_MAX` | `0.5` / `8` | seconds |
| `SIDE_PUSH_RECEIPT_INTERVAL` | `60` | seconds between receipt checks (`0` disables) |
| `SIDE_PUSH_RECEIPT_MIN_AGE` | `900` | only check tickets at least this old (Expo recommends ~15 min) |
| `SIDE_DEEP_LINK_BASE` | `side://runs/` | |
| `SIDE_CORS_ORIGINS` | unset (CORS off) | comma-separated origins; native apps don't need CORS |
| `SIDE_LOG_LEVEL` | `INFO` | |

## Tests

```bash
.venv/bin/pytest -q          # Expo is mocked with respx; nothing hits the network
.venv/bin/ruff check . && .venv/bin/black --check .
```
