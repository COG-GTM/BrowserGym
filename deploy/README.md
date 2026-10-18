# Side — Docker & deployment

Container images and a local compose stack for Side (see `docs/side/ARCHITECTURE.md` and
`contracts/openapi.yaml`). All images build from the **repository root** as context.

| Service | Dockerfile | Sources | Base image | Port |
|---|---|---|---|---|
| `api` | `deploy/api/Dockerfile` | `apps/api` + `services/runner` + `browsergym/*` | `mcr.microsoft.com/playwright/python:v1.49.1-noble` (Python 3.12) | **8000** |
| `runner` | `deploy/runner/Dockerfile` | `services/runner` + `browsergym/*` | same Playwright image | — (one-shot) |
| `notifications` | `deploy/notifications/Dockerfile` | `services/notifications` | `python:3.12-slim-bookworm` | **8010** |
| `web` | `deploy/web/Dockerfile` | `apps/web` (+ root JS workspace, `packages/*`) | `node:22-bookworm-slim` | **3000** |

The API spawns one `python -m side_runner ...` subprocess per run, so the `api` image contains the
runner, BrowserGym and chromium too. The standalone `runner` image is for one-off/CLI runs and CI
smoke tests.

## Local up

```bash
cp deploy/.env.example deploy/.env        # optional, every value has a default
docker compose -f deploy/docker-compose.yml up --build -d
docker compose -f deploy/docker-compose.yml ps   # api / notifications / web -> (healthy)

curl localhost:8000/api/v1/health         # {"status":"ok",...}
open http://localhost:3000
```

Everything works offline with the `mock` agent; no API keys are required.

One-off runner commands (the `runner` service is behind the `tools` profile, not started by `up`):

```bash
# image smoke test: imports + a real headless BrowserGym episode step
docker compose -f deploy/docker-compose.yml run --rm runner python /opt/side/bin/smoke-runner.py

# run an episode by hand into the shared data volume
docker compose -f deploy/docker-compose.yml run --rm runner python -m side_runner \
  --run-id demo --task browsergym/openended --agent-json '{"type":"mock"}' \
  --max-steps 3 --data-dir /data --goal "say hi" --start-url https://example.com
```

Tear down (add `-v` to also delete run artifacts): `docker compose -f deploy/docker-compose.yml down`.

## Environment variables

| Variable | Used by | Default | Notes |
|---|---|---|---|
| `SIDE_DATA_DIR` | api, runner, notifications | `/data` | Shared named volume `side-data` (artifact layout in ARCHITECTURE.md). Not meant to be overridden in compose. |
| `SIDE_NOTIFY_URL` | api | `http://notifications:8010` | API POSTs `status` RunEvents to `${SIDE_NOTIFY_URL}/internal/run-events`. Set to an empty value to disable. |
| `SIDE_CORS_ORIGINS` | api | `http://localhost:${SIDE_WEB_PORT}` | Browser origins allowed to call the API (if apps/api supports it). |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | api, runner | empty | Only for `openai` / `anthropic` agents. |
| `MINIWOB_URL` | api, runner | baked in | MiniWoB++ HTML is bundled at `/opt/miniwob-plusplus` (same pinned commit as `make setup-miniwob`), so `browsergym/miniwob.*` tasks run offline. |
| `EXPO_ACCESS_TOKEN` | notifications | empty | Expo push access token (optional). |
| `NEXT_PUBLIC_SIDE_API_URL` | web (build arg) | `http://localhost:${SIDE_API_PORT}/api/v1` | Browser-side API base URL. Inlined at build time: rebuild `web` after changing. |
| `NEXT_PUBLIC_SIDE_MOCK` | web (build arg) | `0` | `1` = fixtures only, no backend. |
| `SIDE_API_URL` | web (runtime) | `http://api:8000/api/v1` | Server-side (SSR / route handlers) API base URL inside the compose network. |
| `SIDE_API_PORT` / `SIDE_NOTIFICATIONS_PORT` / `SIDE_WEB_PORT` | compose | `8000` / `8010` / `3000` | Host ports. The browser API URL and CORS origin defaults follow them. |
| `SIDE_BIND_ADDR` | compose | `127.0.0.1` | Host address the ports are published on. Use `0.0.0.0` to expose the stack to the network (there's no auth). |
| `FORWARDED_ALLOW_IPS` | api, notifications | `127.0.0.1` | uvicorn: proxies trusted for `X-Forwarded-*` headers. |
| `SIDE_IMAGE_PREFIX` / `SIDE_IMAGE_TAG` | compose | `side` / `local` | Image names `<prefix>-<service>:<tag>`. |
| `SIDE_API_APP` / `SIDE_NOTIFICATIONS_APP` | api / notifications | auto | Override the ASGI app (`module:attr`). By default `deploy/scripts/serve.py` picks the first importable of `side_api.main:app`, `side_api.app:app`, `api.main:app`, `app.main:app`, `main:app` (notifications: `side_notifications.*`, `notifications.main:app`, ...). |

## How the images find app sources

- Python apps (`apps/api`, `services/runner`, `services/notifications`): if the directory has a
  `pyproject.toml`/`setup.py` it is `pip install`ed, otherwise its `requirements.txt` is installed;
  the directory is also put on `PYTHONPATH`. BrowserGym is installed from this repo
  (`browsergym/core`, `experiments`, `miniwob` by default; build arg `BROWSERGYM_PACKAGES`)
  before the apps, so the apps resolve `browsergym-core` to the local version.
- Chromium: browsergym pins its own `playwright` version, so the image runs
  `playwright install chromium` for that version and removes the base image's other browsers.
- Web: `apps/web` must set `output: "standalone"` in `next.config`. If the repo root has a JS
  workspace (`package.json` `workspaces` or `pnpm-workspace.yaml`) dependencies are installed
  there with the matching lockfile (pnpm / yarn / npm), otherwise inside `apps/web`. Monorepo
  standalone output (`outputFileTracingRoot` = repo root) is handled.
- **Stubs**: if one of those directories is missing from the build context, the Dockerfile falls back
  to `deploy/stubs/<service>` (a minimal contract-shaped placeholder) and logs
  `side-deploy: ... using stub ...`. The chosen source is recorded in `/opt/side/<service>/.side-source`
  (`/app/.side-source` for web). Stubs exist only so the images and compose stack can be smoke-tested
  before the other workstreams land.

## CI — `.github/workflows/side-images.yml`

- Triggers on PRs to and pushes on `side/main` that touch Side/BrowserGym paths (and manually).
- `docker compose config` check, then a matrix build of `runner`, `api`, `notifications`, `web`
  with buildx + GitHub Actions cache (`type=gha`, one scope per image).
- Pull requests: build only (no push) and run the runner smoke test on the built image.
- Push on `side/main`: push to `ghcr.io/<owner>/side-<service>` tagged `latest` and `sha-<short>`
  using `GITHUB_TOKEN` with `packages: write`.

## Notes

- Chromium needs a bigger `/dev/shm`: compose sets `shm_size: 1gb` on `api` and `runner`
  (use `--shm-size=1g` with plain `docker run`).
- Containers run as non-root. api/runner (`pwuser`) and notifications (`side`) share UID/GID 1001, so the `side-data` volume stays writable whichever container initializes it first. The build fails if the Playwright base ever changes `pwuser`'s UID.
- The Playwright images are large (~1.2 GB compressed) because the base ships all browsers.
