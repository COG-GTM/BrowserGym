# deploy/stubs — placeholder apps for local smoke testing only

The Dockerfiles in `deploy/` build the real sources from `apps/api`, `services/runner`,
`services/notifications` and `apps/web`. When one of those directories is missing from the
build context (e.g. on a fresh `side/main` before the workstreams land), the Dockerfile
falls back to the matching stub here and records the choice in `/opt/side/<name>/.side-source`
(`/app/.side-source` for web).

Stubs implement just enough of `contracts/openapi.yaml` / `docs/side/ARCHITECTURE.md` to
exercise the container wiring (health, API -> runner subprocess -> shared `SIDE_DATA_DIR`,
API -> notifications). They are not product code; never import them from apps/ or services/.
