import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { expectSchema } from "../../support/contract";

// The mock fixtures double as sample data for apps/web and apps/mobile mock mode, so keep them on-contract.
const dir = fileURLToPath(new URL("../../mock/fixtures/", import.meta.url));
const read = (rel: string) => JSON.parse(readFileSync(dir + rel, "utf8"));

test.describe("mock fixtures conform to the contract", () => {
  test("tasks.json is Task[]", () => {
    const tasks = read("tasks.json");
    expect(tasks.length).toBeGreaterThan(3);
    tasks.forEach((t: unknown, i: number) => expectSchema("Task", t, `tasks.json[${i}]`));
  });

  test("agents.json is AgentInfo[]", () => {
    read("agents.json").forEach((a: unknown, i: number) => expectSchema("AgentInfo", a, `agents.json[${i}]`));
  });

  test("runs.json is Run[] covering every status", () => {
    const runs = read("runs.json");
    runs.forEach((r: unknown, i: number) => expectSchema("Run", r, `runs.json[${i}]`));
    expect(new Set(runs.map((r: any) => r.status))).toEqual(new Set(["queued", "running", "succeeded", "failed", "cancelled"]));
  });

  for (const file of readdirSync(dir + "events").filter((f) => f.endsWith(".json"))) {
    test(`events/${file} is RunEvent[] once run_id/timestamp are filled in`, () => {
      const timestamp = new Date().toISOString();
      read(`events/${file}`).events.forEach((e: any, i: number) => {
        const event = { ...e, run_id: "fixture", timestamp };
        if (event.step) event.step = { ...event.step, timestamp };
        if (event.chat) event.chat = { ...event.chat, timestamp };
        expectSchema("RunEvent", event, `events/${file}[${i}]`);
      });
    });
  }
});
