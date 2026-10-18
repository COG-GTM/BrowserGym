import { expect, test } from "@playwright/test";
import { expectOp } from "../../support/api";
import { API_MODE } from "../../support/env";
import { contract } from "../../support/contract";

test.describe("tasks", () => {
  test("listTasks: GET /tasks -> 200 Task[]", async ({ request }) => {
    const tasks = await expectOp<any[]>(request, "listTasks", 200);
    expect(tasks.length).toBeGreaterThan(0);
    const ids = tasks.map((t) => t.id);
    expect(new Set(ids).size, "task ids are unique").toBe(ids.length);
    if (API_MODE === "live") expect(ids).toContain("browsergym/openended");
  });

  test("listTasks: ?benchmark= filters by benchmark", async ({ request }) => {
    const tasks = await expectOp<any[]>(request, "listTasks", 200, { query: { benchmark: "miniwob" } });
    for (const t of tasks) expect(t.benchmark).toBe("miniwob");
  });

  test("listTasks: ?q= searches id/title", async ({ request }) => {
    const tasks = await expectOp<any[]>(request, "listTasks", 200, { query: { q: "click" } });
    if (API_MODE === "live") {
      expect(tasks.length).toBeGreaterThan(0);
      for (const t of tasks) expect(`${t.id} ${t.title} ${t.description ?? ""}`.toLowerCase()).toContain("click");
    }
  });

  test("listTasks: unknown query returns an empty array, not an error", async ({ request }) => {
    const tasks = await expectOp<any[]>(request, "listTasks", 200, { query: { q: "zz-no-such-task-zz" } });
    if (API_MODE === "live") expect(tasks).toEqual([]);
  });
});

test.describe("agents", () => {
  test("listAgents: GET /agents -> 200 AgentInfo[] including the offline mock agent", async ({ request }) => {
    const agents = await expectOp<any[]>(request, "listAgents", 200);
    const types = agents.map((a) => a.type);
    expect(types).toContain("mock");
    const allowed = contract.components.schemas.AgentInfo.properties.type.enum as string[];
    for (const type of types) expect(allowed).toContain(type);
  });
});
