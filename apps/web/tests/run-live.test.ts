import { describe, expect, it } from "vitest";
import { initialRunLiveState, runLiveReducer } from "@/hooks/use-run-live";
import type { ChatMessage, Run } from "@/lib/api";

const run = { id: "r1", task_id: "browsergym/openended", status: "running", n_steps: 0 } as unknown as Run;
const loaded = runLiveReducer(initialRunLiveState, { type: "loaded", run, steps: [], chat: [] });
const sent: ChatMessage = { role: "user", message: "use the search box", timestamp: "2026-10-18T03:03:02.141Z" };
const echo: ChatMessage = { ...sent, timestamp: "2026-10-18T03:03:05.000Z" };
const users = (s: typeof loaded) => [...s.chat, ...s.outbox].filter((m) => m.role === "user");
const chatEvent = (chat: ChatMessage) =>
  ({ type: "event", event: { type: "chat", run_id: "r1", timestamp: chat.timestamp, chat } }) as const;

describe("useRunLive chat reconciliation", () => {
  it("loading applies the run and steps", () => {
    expect(loaded.run).toEqual(run);
    expect(loaded.loading).toBe(false);
  });

  it("replaces the POST /chat response with the runner's re-stamped echo (SSE)", () => {
    let s = runLiveReducer(loaded, { type: "chat", message: sent });
    expect(users(s)).toHaveLength(1);
    s = runLiveReducer(s, { type: "event", event: { type: "chat", run_id: "r1", timestamp: echo.timestamp, chat: echo } });
    expect(users(s)).toEqual([echo]);
  });

  it("ignores the POST response when the echo arrived first", () => {
    let s = runLiveReducer(loaded, { type: "event", event: { type: "chat", run_id: "r1", timestamp: echo.timestamp, chat: echo } });
    s = runLiveReducer(s, { type: "chat", message: sent });
    expect(users(s)).toEqual([echo]);
  });

  it("confirms pending messages from a reload", () => {
    let s = runLiveReducer(loaded, { type: "chat", message: sent });
    s = runLiveReducer(s, { type: "loaded", run, steps: [], chat: [echo] });
    expect(users(s)).toEqual([echo]);
  });

  it("does not treat an older identical message as the echo", () => {
    const older: ChatMessage = { ...sent, timestamp: "2026-10-18T02:00:00.000Z" };
    let s = runLiveReducer(initialRunLiveState, { type: "loaded", run, steps: [], chat: [older] });
    s = runLiveReducer(s, { type: "chat", message: sent });
    expect(users(s)).toEqual([older, sent]);
  });

  it("does not let one echo acknowledge a quick repeat of the same message", () => {
    let s = runLiveReducer(loaded, { type: "chat", message: sent });
    s = runLiveReducer(s, chatEvent({ ...sent, timestamp: "2026-10-18T03:03:02.500Z" }));
    const repeat: ChatMessage = { ...sent, timestamp: "2026-10-18T03:03:03.000Z" };
    s = runLiveReducer(s, { type: "chat", message: repeat });
    expect(users(s)).toHaveLength(2);
    // A replayed copy of the first echo (reload) must not confirm the repeat either.
    s = runLiveReducer(s, { type: "loaded", run, steps: [], chat: [{ ...sent, timestamp: "2026-10-18T03:03:02.500Z" }] });
    expect(s.outbox).toEqual([repeat]);
  });
});
