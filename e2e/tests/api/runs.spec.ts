import { expect, test } from "@playwright/test";
import { createRunId, expectOp, mockRunCreate, preferStatus, TERMINAL_STATUSES, waitForTerminal } from "../../support/api";
import { schemaEnum } from "../../support/contract";
import { API_MODE } from "../../support/env";

test.describe("runs collection", () => {
  test("listRuns: GET /runs -> 200 {items: Run[], next_cursor}", async ({ request }) => {
    const page = await expectOp(request, "listRuns", 200);
    expect(Array.isArray(page.items)).toBe(true);
    if (API_MODE === "live") {
      const created = page.items.map((r: any) => Date.parse(r.created_at));
      expect(created, "runs are newest first").toEqual([...created].sort((a, b) => b - a));
    }
  });

  for (const status of schemaEnum("RunStatus")) {
    test(`listRuns: ?status=${status} only returns ${status} runs`, async ({ request }) => {
      const page = await expectOp(request, "listRuns", 200, { query: { status } });
      if (API_MODE === "live") for (const run of page.items) expect(run.status).toBe(status);
    });
  }

  test("listRuns: ?limit= and cursor pagination", async ({ request }) => {
    const first = await expectOp(request, "listRuns", 200, { query: { limit: 1 } });
    if (API_MODE === "mock") return;
    expect(first.items.length).toBeLessThanOrEqual(1);
    if (first.next_cursor) {
      const second = await expectOp(request, "listRuns", 200, { query: { limit: 1, cursor: first.next_cursor } });
      if (second.items.length) expect(second.items[0].id).not.toBe(first.items[0].id);
    }
  });

  test("createRun: POST /runs with the mock agent -> 201 Run(status=queued)", async ({ request }) => {
    const body = mockRunCreate();
    const run = await expectOp(request, "createRun", 201, { body });
    expect(run.status).toBe("queued");
    expect(run.n_steps).toBe(0);
    if (API_MODE === "live") {
      expect(run.task_id).toBe(body.task_id);
      expect(run.agent.type).toBe("mock");
      expect(run.goal).toBe(body.goal);
      expect(run.max_steps).toBe(body.max_steps);
    }
  });

  const invalidBodies: [string, unknown][] = [
    ["empty body", {}],
    ["missing agent", { task_id: "browsergym/openended" }],
    ["missing task_id", { agent: { type: "mock" } }],
    ["unknown agent type", { task_id: "browsergym/openended", agent: { type: "skynet" } }],
    ["max_steps below minimum", { task_id: "browsergym/openended", agent: { type: "mock" }, max_steps: 0 }],
    ["max_steps above maximum", { task_id: "browsergym/openended", agent: { type: "mock" }, max_steps: 101 }],
  ];
  for (const [name, body] of invalidBodies) {
    test(`createRun: ${name} -> 422 Error`, async ({ request }) => {
      const err = await expectOp(request, "createRun", 422, { body });
      expect(typeof err.detail).toBe("string");
    });
  }
});

test.describe("single run", () => {
  test("getRun: GET /runs/{run_id} -> 200 Run", async ({ request }) => {
    const runId = await createRunId(request);
    const run = await expectOp(request, "getRun", 200, { params: { run_id: runId } });
    if (API_MODE === "live") expect(run.id).toBe(runId);
  });

  test("getRun: unknown run -> 404 Error", async ({ request }) => {
    const err = await expectOp(request, "getRun", 404, { params: { run_id: "does-not-exist-e2e" }, headers: preferStatus(404) });
    expect(typeof err.detail).toBe("string");
  });

  test("cancelRun: POST /runs/{run_id}/cancel -> 200 Run", async ({ request }) => {
    const runId = await createRunId(request, { max_steps: 50 });
    const run = await expectOp(request, "cancelRun", 200, { params: { run_id: runId } });
    if (API_MODE === "live") {
      expect(run.id).toBe(runId);
      // Cancellation is cooperative (runner stops after the current step), so the run ends up cancelled
      // unless it already finished.
      const final = await waitForTerminal(request, runId);
      expect(TERMINAL_STATUSES).toContain(final.status);
      expect(final.finished_at).toBeTruthy();
    }
  });

  test("deleteRun: DELETE /runs/{run_id} -> 204, then getRun -> 404", async ({ request }) => {
    const runId = await createRunId(request);
    if (API_MODE === "live") await waitForTerminal(request, runId);
    await expectOp(request, "deleteRun", 204, { params: { run_id: runId } });
    if (API_MODE === "live") await expectOp(request, "getRun", 404, { params: { run_id: runId } });
  });
});
