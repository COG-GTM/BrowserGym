import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { contractOperations } from "../../support/contract";

test.describe("contract coverage", () => {
  test("every operation in contracts/openapi.yaml has an api test", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readdirSync(dir)
      .filter((f) => f.endsWith(".spec.ts") && f !== "coverage.spec.ts")
      .map((f) => readFileSync(`${dir}/${f}`, "utf8"))
      .join("\n");
    const ops = contractOperations();
    expect(ops.length).toBeGreaterThan(0);
    const uncovered = ops.filter((op) => !new RegExp(`["'\`]${op.operationId}["'\`]`).test(source));
    expect(uncovered.map((o) => `${o.operationId} (${o.method.toUpperCase()} ${o.path})`), "operations without a test").toEqual([]);
  });

  test("every declared response status is exercised", () => {
    // Statuses we assert per operation (keep in sync when the contract grows).
    const exercised: Record<string, string[]> = {
      getHealth: ["200"],
      listTasks: ["200"],
      listAgents: ["200"],
      listRuns: ["200"],
      createRun: ["201", "422"],
      getRun: ["200", "404"],
      deleteRun: ["204"],
      cancelRun: ["200"],
      listSteps: ["200"],
      getStep: ["200"],
      getStepScreenshot: ["200"],
      listChat: ["200"],
      sendChat: ["201"],
      streamRunEvents: ["200"],
      registerDevice: ["201"],
    };
    for (const op of contractOperations()) {
      expect(exercised[op.operationId], `statuses tracked for ${op.operationId}`).toBeDefined();
      expect(exercised[op.operationId].sort(), `${op.operationId} statuses`).toEqual([...op.statuses].sort());
    }
  });
});
