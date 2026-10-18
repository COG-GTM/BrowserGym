# Side web app (`apps/web`)

Next.js (App Router) + TypeScript + Tailwind v4 + shadcn/ui front end for **Side**: launch BrowserGym
episodes, watch them live over SSE and replay their step traces.

## Quick start

```bash
cd apps/web
npm install
npm run dev:mock        # http://localhost:3000, no backend needed (NEXT_PUBLIC_SIDE_MOCK=1)
# or, against a running Side API:
NEXT_PUBLIC_SIDE_API_URL=http://localhost:8000/api/v1 npm run dev
```

| Variable | Default | Meaning |
| --- | --- | --- |
| `NEXT_PUBLIC_SIDE_MOCK` | unset | `1`/`true` serves in-browser fixtures (no network). |
| `NEXT_PUBLIC_SIDE_API_URL` | `http://localhost:8000/api/v1` | Side API base URL when mock mode is off. |

`NEXT_PUBLIC_*` values are inlined at build time, so set them for `npm run build` too.

## Scripts

| Script | What it does |
| --- | --- |
| `npm run gen:api` | Regenerate `src/lib/api/schema.d.ts` from `../../contracts/openapi.yaml` (openapi-typescript). |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` | ESLint (next/core-web-vitals + next/typescript) |
| `npm test` | Vitest: validates every mock fixture/SSE event against the OpenAPI schemas with AJV, plus HTTP client + SSE parsing tests. |
| `npm run build` | Production build. |

## Layout

```
src/
  app/                 routes: / (dashboard), /runs, /runs/new, /runs/[id], /tasks
  components/          app shell, status badges, run list, run-detail panels, shadcn/ui primitives (ui/)
  hooks/               SWR data hooks, useRunLive (SSE + initial fetch merge)
  lib/api/             schema.d.ts (generated), types.ts, client.ts (typed fetch), sse.ts (EventSource helper)
  lib/mock/            fixtures.ts + backend.ts — contract-shaped in-memory backend with a simulated live run
tests/                 contract conformance tests
```

### Live runs

`useRunLive(runId)` subscribes to `GET /runs/{id}/events` **before** fetching `run`, `steps` and `chat`, buffers
events that arrive during the initial fetch, then merges them (deduped by step index / chat timestamp). On a
terminal `status` event the stream is closed and the run is re-fetched for its final reward/error. `EventSource`
reconnects automatically; the UI shows the stream state.

### Mock mode

`lib/mock/backend.ts` implements the same `SideApi` interface as the HTTP client. It seeds ~40 historical runs,
a live run that is mid-episode on every page load (`/runs/run_live_demo`), and runs you create from **New run** progress
queued → running → succeeded/failed with a step every ~1.6 s, emitting `status`/`step`/`chat`/`log` events.
Cancel and chat work. Screenshots are generated SVGs of the simulated page, so everything works offline.
Benchmarks that need external setup (WebArena, WorkArena, …) fail fast in mock mode just like a runner without
that setup would. State lives in the browser tab and resets on reload.
