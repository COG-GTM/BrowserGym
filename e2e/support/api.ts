import { expect, type APIRequestContext, type APIResponse } from "@playwright/test";
import { API_MODE, api } from "./env";
import { expectResponseSchema, expectSchema, operation, type Method } from "./contract";

/** Calls a contract operation by operationId, filling `{param}` placeholders. Ties each test to the contract. */
export async function callOp(
  request: APIRequestContext,
  operationId: string,
  opts: { params?: Record<string, string | number>; query?: Record<string, string | number>; body?: unknown; headers?: Record<string, string> } = {},
): Promise<{ res: APIResponse; path: string; method: Method }> {
  const { path, method } = operation(operationId);
  const concrete = path.replace(/\{(\w+)\}/g, (_, name) => {
    const value = opts.params?.[name];
    if (value === undefined) throw new Error(`${operationId}: missing path param ${name}`);
    return encodeURIComponent(String(value));
  });
  const res = await request.fetch(api(concrete), {
    method: method.toUpperCase(),
    params: opts.query,
    data: opts.body,
    headers: opts.headers,
    failOnStatusCode: false,
  });
  return { res, path, method };
}

/** Calls an operation, asserts the status code and validates the JSON body against the contract. */
export async function expectOp<T = any>(
  request: APIRequestContext,
  operationId: string,
  status: number,
  opts: Parameters<typeof callOp>[2] = {},
): Promise<T> {
  const { res, path, method } = await callOp(request, operationId, opts);
  const text = await res.text();
  expect(res.status(), `${operationId} ${method.toUpperCase()} ${path} -> ${res.status()} ${text.slice(0, 500)}`).toBe(status);
  if (status === 204) {
    expect(text, "204 responses have no body").toBe("");
    return undefined as T;
  }
  expect(res.headers()["content-type"] ?? "").toContain("application/json");
  const body = JSON.parse(text);
  expectResponseSchema(path, method, status, body);
  return body as T;
}

/** Prism picks a response by the `Prefer` header; a real API ignores it. */
export const preferStatus = (code: number) => (API_MODE === "mock" ? { Prefer: `code=${code}` } : undefined);

export const TERMINAL_STATUSES = ["succeeded", "failed", "cancelled"];

/** RunCreate body for a deterministic offline run with the `mock` agent. */
export function mockRunCreate(overrides: Record<string, unknown> = {}) {
  const body = {
    task_id: process.env.E2E_RUN_TASK_ID ?? "browsergym/openended",
    agent: { type: "mock" },
    goal: "Side e2e smoke test",
    start_url: process.env.E2E_RUN_START_URL ?? "about:blank",
    max_steps: 3,
    headless: true,
    ...overrides,
  };
  expectSchema("RunCreate", body, "test request body");
  return body;
}

/** In live mode creates a real mock-agent run; in mock mode returns a fixed id (Prism is stateless). */
export async function createRunId(request: APIRequestContext, overrides: Record<string, unknown> = {}): Promise<string> {
  if (API_MODE === "mock") return "e2e-run";
  const run = await expectOp(request, "createRun", 201, { body: mockRunCreate(overrides) });
  return run.id;
}

/** Live mode only: polls getRun until the run reaches a terminal status. */
export async function waitForTerminal(request: APIRequestContext, runId: string, timeout = 90_000) {
  let last: any;
  await expect
    .poll(
      async () => {
        last = await expectOp(request, "getRun", 200, { params: { run_id: runId } });
        return last.status;
      },
      { timeout, message: `run ${runId} reaches a terminal status` },
    )
    .toMatch(new RegExp(`^(${TERMINAL_STATUSES.join("|")})$`));
  return last;
}
