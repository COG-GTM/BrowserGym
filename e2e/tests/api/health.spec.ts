import { expect, test } from "@playwright/test";
import { expectOp } from "../../support/api";

test("getHealth: GET /health -> 200 {status: ok}", async ({ request }) => {
  const body = await expectOp(request, "getHealth", 200);
  expect(body.status).toBe("ok");
});
