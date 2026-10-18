import { test } from "@playwright/test";
import { WEB_URL } from "./env";

let probe: Promise<string | null> | undefined;
let warned = false;

/** Resolves to a human-readable reason if the web app at E2E_BASE_URL can't be reached, else null. */
export function webUnreachableReason(): Promise<string | null> {
  probe ??= (async () => {
    try {
      const res = await fetch(WEB_URL, { signal: AbortSignal.timeout(5_000), redirect: "follow" });
      if (res.status >= 500) return `E2E_BASE_URL ${WEB_URL} answered HTTP ${res.status}`;
      return null;
    } catch (err) {
      const cause = (err as { cause?: { code?: string } }).cause?.code ?? (err as Error).message;
      return (
        `Side web app unreachable at E2E_BASE_URL=${WEB_URL} (${cause}). ` +
        "Start apps/web (e.g. NEXT_PUBLIC_SIDE_MOCK=1 npm run dev) or run `npm run test:web:reference` to use the e2e reference UI."
      );
    }
  })();
  return probe;
}

/** Call at the top of every web spec: skips the whole file with a clear message if the web app is down. */
export function requireWebApp() {
  test.beforeAll(async () => {
    const reason = await webUnreachableReason();
    if (reason && !warned) {
      warned = true;
      console.warn(`[side-e2e] skipping web tests: ${reason}`);
    }
    test.skip(reason !== null, reason ?? "");
  });
}
