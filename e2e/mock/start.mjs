// Starts the Prism contract mock (:4010) and the gateway (:4000) together. Ctrl+C stops both.
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const procs = [
  spawn("npx", ["prism", "mock", "../contracts/openapi.yaml", "--host", "127.0.0.1", "--port", "4010", "--errors"], { cwd: root, stdio: "inherit" }),
  spawn(process.execPath, ["mock/gateway.mjs"], { cwd: root, stdio: "inherit" }),
];
const stop = () => procs.forEach((p) => p.kill("SIGTERM"));
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
procs.forEach((p) => p.on("exit", (code) => { if (code) { stop(); process.exit(code); } }));
