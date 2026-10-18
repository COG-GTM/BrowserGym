import { expect, test } from "@playwright/test";
import { callOp } from "../../support/api";
import { expectSchema } from "../../support/contract";

// registerDevice is served by services/notifications (proxied by the API or called directly).
test.describe("devices", () => {
  for (const platform of ["ios", "android"]) {
    test(`registerDevice: POST /devices (${platform}) -> 201`, async ({ request }) => {
      const body = { expo_push_token: `ExponentPushToken[e2e-${platform}]`, platform, run_ids: [] };
      expectSchema("DeviceRegistration", body, "test request body");
      const { res } = await callOp(request, "registerDevice", { body });
      expect(res.status()).toBe(201);
    });
  }

  test("registerDevice: unknown platform is rejected with 4xx", async ({ request }) => {
    const { res } = await callOp(request, "registerDevice", { body: { expo_push_token: "ExponentPushToken[x]", platform: "symbian" } });
    expect(res.status()).toBeGreaterThanOrEqual(400);
    expect(res.status()).toBeLessThan(500);
  });
});
