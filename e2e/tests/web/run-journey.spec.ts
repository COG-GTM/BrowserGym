import { expect, test } from "@playwright/test";
import { WEB_TASK_ID } from "../../support/env";
import { requireWebApp } from "../../support/web";

requireWebApp();

const TERMINAL = /^(succeeded|failed|cancelled)$/;

test("create run -> watch live -> open step -> send chat -> cancel", async ({ page }) => {
  await test.step("create a run with the mock agent", async () => {
    await page.goto("/");
    await page.getByTestId("nav-new-run").click();
    await expect(page.getByTestId("new-run-form")).toBeVisible();

    await page.getByTestId("task-search-input").fill(WEB_TASK_ID);
    await page.locator(`[data-testid="task-option"][data-task-id="${WEB_TASK_ID}"]`).first().click();
    await expect(page.getByTestId("selected-task")).toHaveAttribute("data-task-id", WEB_TASK_ID);

    await page.getByTestId("agent-select").selectOption("mock");
    const goal = page.getByTestId("goal-input");
    if (await goal.isVisible()) await goal.fill("Side e2e: click the button");
    const maxSteps = page.getByTestId("max-steps-input");
    if (await maxSteps.isVisible()) await maxSteps.fill("50");
    await page.getByTestId("create-run-submit").click();
  });

  const detail = page.getByTestId("run-detail");
  const status = page.getByTestId("run-status");
  const steps = page.getByTestId("step-item");

  await test.step("land on the run page", async () => {
    await expect(detail).toBeVisible();
    const runId = await detail.getAttribute("data-run-id");
    expect(runId, "run-detail exposes data-run-id").toBeTruthy();
    await expect(page).toHaveURL(new RegExp(`/runs/${runId}$`));
    await expect(status).toHaveAttribute("data-status", /^(queued|running|succeeded|failed|cancelled)$/);
  });

  await test.step("watch it live: steps stream in over SSE", async () => {
    await expect(steps.first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("live-indicator")).toBeVisible();
    await expect(status).toHaveAttribute("data-status", "running");
    await expect.poll(() => steps.count(), { message: "step list grows while the run is live", timeout: 30_000 }).toBeGreaterThan(1);
  });

  await test.step("open a step", async () => {
    await steps.first().click();
    const stepDetail = page.getByTestId("step-detail");
    await expect(stepDetail).toBeVisible();
    await expect(stepDetail).toHaveAttribute("data-step-index", "0");
    await expect(stepDetail.getByTestId("step-action")).not.toBeEmpty();
  });

  await test.step("send a chat message", async () => {
    const message = `hello from e2e ${Date.now()}`;
    await page.getByTestId("chat-input").fill(message);
    await page.getByTestId("chat-send").click();
    await expect(page.locator('[data-testid="chat-message"][data-role="user"]', { hasText: message })).toBeVisible();
    await expect(page.getByTestId("chat-input")).toHaveValue("");
  });

  await test.step("cancel the run", async () => {
    const current = await status.getAttribute("data-status");
    expect(current, "run is still live when we cancel (use a longer mock run if this fails)").not.toMatch(TERMINAL);
    await page.getByTestId("run-cancel").click();
    await expect(status).toHaveAttribute("data-status", "cancelled", { timeout: 30_000 });
    await expect(page.getByTestId("live-indicator")).toBeHidden();
    await expect(page.getByTestId("run-cancel")).toBeDisabled();
    const settled = await steps.count();
    await page.waitForTimeout(1_500);
    expect(await steps.count(), "no new steps after cancellation settles").toBeLessThanOrEqual(settled + 1);
  });
});
