// Side e2e mock gateway.
//
//   /api/v1/runs/{id}/events            -> fixture-driven fake SSE stream (mock/fixtures/events/*.json)
//   /api/v1/runs/{id}/steps/{n}/screenshot -> fixture PNG (Prism can only return a placeholder string)
//   /api/v1/*                           -> proxied to the Prism mock of contracts/openapi.yaml
//   everything else                     -> reference web UI (mock/reference-web), SPA fallback
//
// Env: GATEWAY_PORT (4000), PRISM_URL (http://127.0.0.1:4010), SSE_DELAY_MS (250).
import { createServer, request as httpRequest } from "node:http";
import { readFileSync, existsSync } from "node:fs";
import { dirname, extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.GATEWAY_PORT ?? 4000);
const PRISM_URL = new URL(process.env.PRISM_URL ?? "http://127.0.0.1:4010");
const DEFAULT_DELAY_MS = Number(process.env.SSE_DELAY_MS ?? 250);
const API_PREFIX = "/api/v1";
const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);
const WEB_ROOT = join(here, "reference-web");
const FIXTURES = join(here, "fixtures");
const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json", ".png": "image/png" };

function loadEventFixture(runId) {
  // Run ids starting with "fail" replay the failed fixture; a file named <run_id>.json wins over both.
  const candidates = [`${runId}.json`, runId.startsWith("fail") ? "failed.json" : null, "default.json"].filter(Boolean);
  for (const name of candidates) {
    const file = join(FIXTURES, "events", name);
    if (/^[\w.-]+$/.test(name) && existsSync(file)) return JSON.parse(readFileSync(file, "utf8")).events;
  }
  throw new Error("no default SSE fixture");
}

function streamEvents(req, res, runId, url) {
  const delay = Number(url.searchParams.get("delay_ms") ?? DEFAULT_DELAY_MS);
  const events = loadEventFixture(runId);
  res.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
    "Access-Control-Allow-Origin": "*",
  });
  res.write(": side e2e fake SSE\n\n");
  let i = 0;
  let timer;
  const next = () => {
    if (i >= events.length) return res.end();
    const fixture = events[i++];
    const timestamp = new Date().toISOString();
    const event = { ...fixture, run_id: runId, timestamp };
    if (event.step) event.step = { ...event.step, timestamp };
    if (event.chat) event.chat = { ...event.chat, timestamp };
    res.write(`id: ${i}\nevent: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`);
    if (event.type === "status" && TERMINAL.has(event.status)) return res.end();
    timer = setTimeout(next, delay);
  };
  req.on("close", () => clearTimeout(timer));
  next();
}

function proxyToPrism(req, res, apiPath) {
  const upstream = httpRequest(
    { host: PRISM_URL.hostname, port: PRISM_URL.port, method: req.method, path: apiPath, headers: { ...req.headers, host: PRISM_URL.host } },
    (up) => {
      res.writeHead(up.statusCode ?? 502, up.headers);
      up.pipe(res);
    },
  );
  upstream.on("error", (err) => {
    res.writeHead(502, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ detail: `Prism mock unreachable at ${PRISM_URL.href}: ${err.message}` }));
  });
  req.pipe(upstream);
}

function serveStatic(res, pathname) {
  const fixture = pathname.startsWith("/fixtures/");
  const root = fixture ? FIXTURES : WEB_ROOT;
  const rel = normalize(fixture ? pathname.slice("/fixtures/".length) : pathname).replace(/^(\.\.[/\\])+/, "");
  let file = join(root, rel);
  if (!file.startsWith(root) || !existsSync(file) || extname(file) === "") file = join(WEB_ROOT, "index.html");
  res.writeHead(200, { "Content-Type": MIME[extname(file)] ?? "application/octet-stream", "Cache-Control": "no-store" });
  res.end(readFileSync(file));
}

const server = createServer((req, res) => {
  const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);
  if (url.pathname === "/__gateway/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    return res.end(JSON.stringify({ status: "ok", prism: PRISM_URL.href }));
  }
  if (url.pathname.startsWith(API_PREFIX + "/")) {
    const apiPath = url.pathname.slice(API_PREFIX.length);
    const events = apiPath.match(/^\/runs\/([^/]+)\/events$/);
    if (events && req.method === "GET") return streamEvents(req, res, decodeURIComponent(events[1]), url);
    if (/^\/runs\/[^/]+\/steps\/\d+\/screenshot$/.test(apiPath) && req.method === "GET") {
      res.writeHead(200, { "Content-Type": "image/png" });
      return res.end(readFileSync(join(FIXTURES, "screenshot.png")));
    }
    return proxyToPrism(req, res, apiPath + url.search);
  }
  if (req.method === "GET") return serveStatic(res, url.pathname);
  res.writeHead(404, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ detail: "not found" }));
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`[side-e2e gateway] http://127.0.0.1:${PORT}  (api ${API_PREFIX} -> ${PRISM_URL.href}, SSE fixtures, reference web)`);
});
