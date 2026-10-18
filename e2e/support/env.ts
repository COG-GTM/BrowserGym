/** Runtime configuration for the e2e suite (all overridable through env vars). */
export const MOCK_GATEWAY_URL = "http://127.0.0.1:4000";

/** Base URL of the Side API including the /api/v1 prefix. Defaults to the local contract mock. */
export const API_URL = (process.env.E2E_API_URL ?? `${MOCK_GATEWAY_URL}/api/v1`).replace(/\/+$/, "");

/** `mock` = Prism contract mock (stateless, example data); `live` = a real apps/api (stateful assertions enabled). */
export const API_MODE: "mock" | "live" = process.env.E2E_API_URL && process.env.E2E_API_MODE !== "mock" ? "live" : "mock";

/** Base URL of the Side web app (apps/web). */
export const WEB_URL = (process.env.E2E_BASE_URL ?? "http://localhost:3000").replace(/\/+$/, "");

/** Task the web journey creates a run for (must exist in the web app's task list / mock fixtures). */
export const WEB_TASK_ID = process.env.E2E_TASK_ID ?? "browsergym/miniwob.click-test";

/** Joins API_URL with a contract path such as `/runs/{run_id}`. */
export const api = (path: string) => `${API_URL}${path}`;
