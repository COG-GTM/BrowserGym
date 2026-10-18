import { defineConfig, devices } from "@playwright/test";
import { API_URL, MOCK_GATEWAY_URL, WEB_URL } from "./support/env";

const CI = !!process.env.CI;
// Start the contract mock unless the suite targets a real API (E2E_API_URL) or E2E_NO_MOCK=1.
const startMock = !process.env.E2E_API_URL && !process.env.E2E_NO_MOCK;

export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  forbidOnly: CI,
  retries: CI ? 1 : 0,
  reporter: CI
    ? [["list"], ["github"], ["html", { open: "never" }], ["junit", { outputFile: "test-results/junit.xml" }]]
    : [["list"], ["html", { open: "never" }]],
  use: {
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "api",
      testDir: "./tests/api",
      use: { baseURL: `${API_URL}/`, extraHTTPHeaders: { Accept: "application/json" } },
    },
    {
      name: "web",
      testDir: "./tests/web",
      use: { ...devices["Desktop Chrome"], baseURL: WEB_URL, video: "retain-on-failure" },
    },
  ],
  webServer: startMock
    ? [
        {
          command: "npx prism mock ../contracts/openapi.yaml --host 127.0.0.1 --port 4010 --errors",
          url: "http://127.0.0.1:4010/health",
          reuseExistingServer: !CI,
          timeout: 60_000,
          stdout: "ignore",
          stderr: "pipe",
        },
        {
          command: "node mock/gateway.mjs",
          url: `${MOCK_GATEWAY_URL}/__gateway/health`,
          reuseExistingServer: !CI,
          env: { SSE_DELAY_MS: process.env.SSE_DELAY_MS ?? "50" },
          timeout: 30_000,
        },
      ]
    : undefined,
});
