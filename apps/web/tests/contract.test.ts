import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import { parse } from "yaml";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createMockApi } from "@/lib/mock/backend";
import { buildPath, createHttpApi } from "@/lib/api/client";
import { parseRunEvent } from "@/lib/api/sse";
import type { RunEvent } from "@/lib/api/types";

const spec = parse(readFileSync(fileURLToPath(new URL("../../../contracts/openapi.yaml", import.meta.url)), "utf8"));
const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
ajv.addSchema({ ...spec, $id: "openapi" });

function expectSchema(name: string, value: unknown, array = false) {
  const ref = { $ref: `openapi#/components/schemas/${name}` };
  const validate = ajv.compile(array ? { type: "array", items: ref } : ref);
  const ok = validate(value);
  expect(validate.errors ?? [], `${name}: ${ajv.errorsText(validate.errors)}`).toEqual([]);
  expect(ok).toBe(true);
}

describe("mock fixtures conform to contracts/openapi.yaml", () => {
  const api = createMockApi({ latencyMs: 0, liveDemo: false });

  it("tasks and agents", async () => {
    expectSchema("Task", await api.listTasks(), true);
    expectSchema("AgentInfo", await api.listAgents(), true);
  });

  it("runs, steps, step detail and chat", async () => {
    const page = await api.listRuns({ limit: 200 });
    expect(page.items.length).toBeGreaterThan(20);
    expectSchema("Run", page.items, true);
    for (const run of page.items.slice(0, 10)) {
      const steps = await api.listSteps(run.id);
      expect(steps.length).toBe(run.n_steps);
      expectSchema("Step", steps, true);
      expectSchema("StepDetail", await api.getStep(run.id, 0));
      expectSchema("ChatMessage", await api.listChat(run.id), true);
    }
  });

  it("seeded run ids are stable across page loads", async () => {
    const a = createMockApi({ latencyMs: 0, liveDemo: false, now: () => Date.parse("2026-01-01T00:00:00Z") });
    const b = createMockApi({ latencyMs: 0, liveDemo: false, now: () => Date.parse("2026-03-01T12:34:56Z") });
    const ids = async (x: typeof a) => (await x.listRuns({ limit: 200 })).items.map((r) => r.id);
    expect(await ids(a)).toEqual(await ids(b));
  });

  it("lists runs newest first", async () => {
    const items = (await api.listRuns({ limit: 200 })).items.map((r) => Date.parse(r.created_at));
    expect(items).toEqual([...items].sort((a, b) => b - a));
  });

  it("filters and paginates runs with cursors", async () => {
    const first = await api.listRuns({ limit: 10 });
    expect(first.items).toHaveLength(10);
    expect(first.next_cursor).toBeTruthy();
    const second = await api.listRuns({ limit: 10, cursor: first.next_cursor! });
    expect(second.items[0].id).not.toBe(first.items[0].id);
    const failed = await api.listRuns({ status: "failed", limit: 200 });
    expect(failed.items.every((r) => r.status === "failed")).toBe(true);
  });

  it("validates RunCreate like the API (422s)", async () => {
    await expect(api.createRun({ task_id: "nope", agent: { type: "mock" } })).rejects.toMatchObject({ status: 422 });
    await expect(api.createRun({ task_id: "browsergym/openended", agent: { type: "mock" } })).rejects.toMatchObject({ status: 422 });
  });
});

describe("simulated live run", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("emits contract-conformant status/step/chat events and ends with a terminal status", async () => {
    const api = createMockApi({ latencyMs: 0, liveDemo: false, stepIntervalMs: 100 });
    const run = await api.createRun({ task_id: "browsergym/miniwob.click-test", agent: { type: "mock" }, max_steps: 10 });
    expectSchema("Run", run);
    expect(run.status).toBe("queued");
    const events: RunEvent[] = [];
    const states: string[] = [];
    api.subscribeRunEvents(run.id, { onEvent: (e) => events.push(e), onStateChange: (s) => states.push(s) });
    await vi.advanceTimersByTimeAsync(5000);
    expectSchema("RunEvent", events, true);
    const statuses = events.filter((e) => e.type === "status").map((e) => e.status);
    expect(statuses[0]).toBe("running");
    expect(statuses.at(-1)).toBe("succeeded");
    const stepEvents = events.filter((e) => e.type === "step");
    expect(stepEvents.length).toBeGreaterThanOrEqual(5);
    expect(stepEvents.map((e) => e.step!.index)).toEqual(stepEvents.map((_, i) => i));
    expect(states).toContain("closed");
    const final = await api.getRun(run.id);
    expect(final).toMatchObject({ status: "succeeded", reward: 1, n_steps: stepEvents.length });
    expect(api.screenshotSrc(run.id, stepEvents[0].step!)).toMatch(/^data:image\/svg\+xml/);
  });

  it("cancel and chat", async () => {
    const api = createMockApi({ latencyMs: 0, liveDemo: false, stepIntervalMs: 2000 });
    const run = await api.createRun({ task_id: "browsergym/openended", goal: "Say hi", agent: { type: "mock" } });
    await vi.advanceTimersByTimeAsync(1000);
    const msg = await api.sendChat(run.id, "please hurry");
    expectSchema("ChatMessage", msg);
    await vi.advanceTimersByTimeAsync(1200);
    expect((await api.getRun(run.id)).status).toBe("running");
    const chat = await api.listChat(run.id);
    expect(chat.some((m) => m.role === "assistant")).toBe(true);
    const cancelled = await api.cancelRun(run.id);
    expect(cancelled.status).toBe("cancelled");
    expectSchema("Run", cancelled);
  });
});

describe("http client", () => {
  it("builds contract paths", () => {
    expect(buildPath("/runs/{run_id}/steps/{index}", { run_id: "r 1", index: 3 })).toBe("/runs/r%201/steps/3");
  });

  it("calls the API with query params and surfaces error detail", async () => {
    const calls: string[] = [];
    const fetchImpl = (async (url: string) => {
      calls.push(url);
      if (url.includes("/runs/missing")) return new Response(JSON.stringify({ detail: "Run not found" }), { status: 404 });
      return new Response(JSON.stringify({ items: [], next_cursor: null }), { status: 200 });
    }) as unknown as typeof fetch;
    const api = createHttpApi("http://localhost:8000/api/v1", fetchImpl);
    await api.listRuns({ status: "running", limit: 20 });
    expect(calls[0]).toBe("http://localhost:8000/api/v1/runs?status=running&limit=20");
    await expect(api.getRun("missing")).rejects.toMatchObject({ status: 404, detail: "Run not found" });
    expect(api.screenshotSrc("r1", { index: 0, screenshot_url: "/runs/r1/steps/0/screenshot" })).toBe(
      "http://localhost:8000/api/v1/runs/r1/steps/0/screenshot",
    );
    expect(api.screenshotSrc("r1", { index: 0, screenshot_url: "/api/v1/runs/r1/steps/0/screenshot" })).toBe(
      "http://localhost:8000/api/v1/runs/r1/steps/0/screenshot",
    );
  });

  it("parses SSE payloads defensively", () => {
    expect(parseRunEvent('{"type":"step","run_id":"r","timestamp":"2026-01-01T00:00:00Z"}')).toMatchObject({ type: "step" });
    expect(parseRunEvent("not json")).toBeNull();
    expect(parseRunEvent('{"type":"bogus","run_id":"r","timestamp":"x"}')).toBeNull();
  });
});
