import { expect, test } from "@playwright/test";
import { requireWebApp } from "../../support/web";

requireWebApp();

const QUERY = process.env.E2E_TASK_QUERY ?? "click";

test.describe("tasks", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("nav-tasks").click();
    await expect(page.getByTestId("task-row").first()).toBeVisible();
  });

  test(`search narrows the list to matching tasks ("${QUERY}")`, async ({ page }) => {
    const rows = page.getByTestId("task-row");
    const total = await rows.count();
    await page.getByTestId("tasks-search-input").fill(QUERY);
    await expect(async () => {
      const texts = await rows.evaluateAll((els) => els.map((el) => `${el.getAttribute("data-task-id")} ${el.textContent}`.toLowerCase()));
      expect(texts.length).toBeGreaterThan(0);
      expect(texts.length).toBeLessThan(total);
      for (const t of texts) expect(t).toContain(QUERY.toLowerCase());
    }).toPass({ timeout: 10_000 });
  });

  test("no match shows the empty state; clearing restores the list", async ({ page }) => {
    const rows = page.getByTestId("task-row");
    const total = await rows.count();
    const search = page.getByTestId("tasks-search-input");
    await search.fill("zz-no-such-task-zz");
    await expect(rows).toHaveCount(0);
    await expect(page.getByTestId("tasks-empty")).toBeVisible();
    await search.fill("");
    await expect(rows).toHaveCount(total);
    await expect(page.getByTestId("tasks-empty")).toBeHidden();
  });
});
