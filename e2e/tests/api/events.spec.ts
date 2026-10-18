import { expect, test } from "@playwright/test";
import { createRunId } from "../../support/api";
import { expectResponseSchema, operation, schemaEnum } from "../../support/contract";
import { API_MODE, api } from "../../support/env";
import { readSse } from "../../support/sse";

const { path: PATH } = operation("streamRunEvents");
const TERMINAL = ["succeeded", "failed", "cancelled"];

async function streamAndValidate(runId: string) {
  const sse = await readSse(api(PATH.replace("{run_id}", encodeURIComponent(runId))), API_MODE === "live" ? 120_000 : 30_000);
  expect(sse.status, "streamRunEvents status").toBe(200);
  expect(sse.contentType ?? "").toContain("text/event-stream");
  expect(sse.frames.length, "stream emitted events").toBeGreaterThan(0);

  const events = sse.frames.map((frame, i) => {
    const data = JSON.parse(frame.data);
    expectResponseSchema(PATH, "get", 200, data, "text/event-stream");
    expect(frame.event, `frame ${i}: SSE event name equals RunEvent.type`).toBe(data.type);
    expect(data.run_id, `frame ${i}: run_id`).toBe(runId);
    expect(Number.isNaN(Date.parse(data.timestamp)), `frame ${i}: timestamp parses`).toBe(false);
    // The payload field named after the type must be present.
    expect(data[data.type], `frame ${i}: ${data.type} event carries a "${data.type}" payload`).toBeDefined();
    return data;
  });
  return { sse, events };
}

test.describe("streamRunEvents (SSE)", () => {
  test("GET /runs/{run_id}/events streams contract RunEvents and closes after a terminal status", async ({ request }) => {
    const runId = await createRunId(request, { max_steps: 3 });
    const { sse, events } = await streamAndValidate(runId);

    const types = new Set(events.map((e) => e.type));
    for (const t of types) expect(["status", "step", "chat", "log"]).toContain(t);
    expect(types.has("status")).toBe(true);
    expect(types.has("step")).toBe(true);

    const statuses = events.filter((e) => e.type === "status").map((e) => e.status);
    for (const s of statuses) expect(schemaEnum("RunStatus")).toContain(s);
    const last = events.at(-1);
    expect(last.type, "last event is a status event").toBe("status");
    expect(TERMINAL).toContain(last.status);
    expect(statuses.slice(0, -1).filter((s) => TERMINAL.includes(s)), "only the last status is terminal").toEqual([]);
    expect(sse.closedByServer, "server closed the stream after the terminal status").toBe(true);

    const indices = events.filter((e) => e.type === "step").map((e) => e.step.index);
    expect(indices, "step indices are contiguous from 0").toEqual(indices.map((_, i) => i));
  });

  test("failed run ends with status=failed", async () => {
    test.skip(API_MODE === "live", "needs a deterministic failing run; covered against the fixture server");
    const { events } = await streamAndValidate("fail-e2e");
    expect(events.at(-1).status).toBe("failed");
  });
});
