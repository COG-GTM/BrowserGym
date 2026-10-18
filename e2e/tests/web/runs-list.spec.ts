import { expect, test } from "@playwright/test";
import { requireWebApp } from "../../support/web";

requireWebApp();

test.describe("runs list", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("nav-runs").click();
    await expect(page.getByTestId("runs-status-filter")).toBeVisible();
  });

  test("filter by every status", async ({ page }) => {
    const filter = page.getByTestId("runs-status-filter");
    const rows = page.getByTestId("run-row");
    await expect(rows.first()).toBeVisible();
    const total = await rows.count();

    const values = await filter.locator("option").evaluateAll((opts) => opts.map((o) => (o as HTMLOptionElement).value));
    expect(values, "filter offers an 'all' option plus every RunStatus").toEqual(
      expect.arrayContaining(["", "queued", "running", "succeeded", "failed", "cancelled"]),
    );

    let seen = 0;
    for (const value of values.filter(Boolean)) {
      await test.step(`status=${value}`, async () => {
        await filter.selectOption(value);
        await expect(async () => {
          const statuses = await rows.evaluateAll((els) => els.map((el) => el.getAttribute("data-status")));
          if (statuses.length === 0) await expect(page.getByTestId("runs-empty")).toBeVisible({ timeout: 500 });
          expect(statuses.every((s) => s === value), `rows for ${value}: ${statuses.join(",")}`).toBe(true);
          seen += statuses.length;
        }).toPass({ timeout: 10_000 });
      });
    }
    expect(seen, "per-status counts add up to at most the full list").toBeLessThanOrEqual(total);

    await filter.selectOption("");
    await expect(rows).toHaveCount(total);
  });

  test("clicking a run opens its detail page", async ({ page }) => {
    const row = page.getByTestId("run-row").first();
    const runId = await row.getAttribute("data-run-id");
    expect(runId).toBeTruthy();
    await row.click();
    await expect(page.getByTestId("run-detail")).toHaveAttribute("data-run-id", runId!);
    await expect(page.getByTestId("run-status")).toHaveAttribute("data-status", /^(queued|running|succeeded|failed|cancelled)$/);
  });
});
