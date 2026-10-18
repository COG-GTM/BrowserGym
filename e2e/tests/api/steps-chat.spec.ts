import { expect, test } from "@playwright/test";
import { callOp, createRunId, expectOp, waitForTerminal } from "../../support/api";
import { API_MODE } from "../../support/env";

const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

test.describe("steps", () => {
  let runId: string;
  test.beforeAll(async ({ request }) => {
    runId = await createRunId(request, { max_steps: 2 });
    if (API_MODE === "live") await waitForTerminal(request, runId);
  });

  test("listSteps: GET /runs/{run_id}/steps -> 200 Step[] in order", async ({ request }) => {
    const steps = await expectOp<any[]>(request, "listSteps", 200, { params: { run_id: runId } });
    expect(steps.length).toBeGreaterThan(0);
    if (API_MODE === "live") expect(steps.map((s) => s.index)).toEqual(steps.map((_, i) => i));
  });

  test("getStep: GET /runs/{run_id}/steps/0 -> 200 StepDetail", async ({ request }) => {
    const step = await expectOp(request, "getStep", 200, { params: { run_id: runId, index: 0 } });
    expect(step.index).toBe(0);
  });

  test("getStepScreenshot: GET /runs/{run_id}/steps/0/screenshot -> 200 image/png", async ({ request }) => {
    const { res } = await callOp(request, "getStepScreenshot", { params: { run_id: runId, index: 0 } });
    test.skip(API_MODE === "live" && res.status() === 404, "run has no screenshot (agent ran with use_screenshot=false)");
    expect(res.status()).toBe(200);
    expect(res.headers()["content-type"]).toContain("image/png");
    const body = await res.body();
    expect(body.subarray(0, 8).equals(PNG_SIGNATURE), "body is a PNG").toBe(true);
  });
});

test.describe("chat", () => {
  test("listChat: GET /runs/{run_id}/chat -> 200 ChatMessage[]", async ({ request }) => {
    const runId = await createRunId(request);
    const messages = await expectOp<any[]>(request, "listChat", 200, { params: { run_id: runId } });
    expect(Array.isArray(messages)).toBe(true);
  });

  test("sendChat: POST /runs/{run_id}/chat -> 201 ChatMessage(role=user)", async ({ request }) => {
    const runId = await createRunId(request, { max_steps: 20 });
    const message = `hello from e2e ${Date.now()}`;
    const msg = await expectOp(request, "sendChat", 201, { params: { run_id: runId }, body: { message } });
    if (API_MODE === "live") {
      expect(msg.role).toBe("user");
      expect(msg.message).toBe(message);
      const history = await expectOp<any[]>(request, "listChat", 200, { params: { run_id: runId } });
      expect(history.map((m) => m.message)).toContain(message);
      await expectOp(request, "cancelRun", 200, { params: { run_id: runId } });
    }
  });

  test("sendChat: empty message is rejected with 4xx", async ({ request }) => {
    const { res } = await callOp(request, "sendChat", { params: { run_id: "e2e-run" }, body: { message: "" } });
    expect(res.status()).toBeGreaterThanOrEqual(400);
    expect(res.status()).toBeLessThan(500);
  });
});
