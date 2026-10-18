"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import {
  getApi,
  isTerminal,
  type ChatMessage,
  type Run,
  type RunEvent,
  type Step,
  type StreamState,
} from "@/lib/api";

export interface RunLiveState {
  run: Run | null;
  steps: Step[];
  chat: ChatMessage[];
  logs: { timestamp: string; message: string }[];
  stream: StreamState | "idle";
  error: Error | null;
  loading: boolean;
  pending: RunEvent[];
  /** User messages accepted by POST /chat but not yet echoed into chat.jsonl by the runner. */
  outbox: ChatMessage[];
  /** chatKeys of echoes already used to confirm a send, so one echo never acknowledges two sends. */
  acked: string[];
}

type Action =
  | { type: "reset" }
  | { type: "loaded"; run: Run; steps: Step[]; chat: ChatMessage[] }
  | { type: "event"; event: RunEvent }
  | { type: "stream"; state: StreamState }
  | { type: "run"; run: Run }
  | { type: "chat"; message: ChatMessage }
  | { type: "error"; error: Error };

export const initialRunLiveState: RunLiveState = {
  run: null,
  steps: [],
  chat: [],
  logs: [],
  stream: "idle",
  error: null,
  loading: true,
  pending: [],
  outbox: [],
  acked: [],
};

const chatKey = (m: ChatMessage) => `${m.role}|${m.timestamp}|${m.message}`;

function mergeSteps(steps: Step[], incoming: Step[]): Step[] {
  const byIndex = new Map(steps.map((s) => [s.index, s]));
  for (const s of incoming) byIndex.set(s.index, s);
  return [...byIndex.values()].sort((a, b) => a.index - b.index);
}

function mergeChat(chat: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  const seen = new Set(chat.map(chatKey));
  const out = [...chat];
  for (const m of incoming) {
    if (seen.has(chatKey(m))) continue;
    seen.add(chatKey(m));
    out.push(m);
  }
  return out;
}

// The runner re-stamps echoed user messages, so match on text and a send time no later than the echo.
const ECHO_CLOCK_SKEW_MS = 2000;

function isEchoOf(echo: ChatMessage, sent: ChatMessage): boolean {
  return (
    echo.role === "user" &&
    echo.message === sent.message &&
    Date.parse(echo.timestamp) >= Date.parse(sent.timestamp) - ECHO_CLOCK_SKEW_MS
  );
}

/** Confirms pending sends with echoes the client hasn't seen before (`known` = chat already held). */
function confirmOutbox(
  state: Pick<RunLiveState, "outbox" | "acked">,
  incoming: ChatMessage[],
  known: ChatMessage[],
): Pick<RunLiveState, "outbox" | "acked"> {
  if (!state.outbox.length) return state;
  const seen = new Set([...known.map(chatKey), ...state.acked]);
  const outbox = [...state.outbox];
  const acked = [...state.acked];
  for (const m of incoming) {
    const key = chatKey(m);
    if (seen.has(key)) continue;
    const i = outbox.findIndex((sent) => isEchoOf(m, sent));
    if (i === -1) continue;
    outbox.splice(i, 1);
    acked.push(key);
    seen.add(key);
  }
  return { outbox, acked };
}

const byTime = (a: ChatMessage, b: ChatMessage) => Date.parse(a.timestamp) - Date.parse(b.timestamp);

function applyEvent(state: RunLiveState, event: RunEvent): RunLiveState {
  switch (event.type) {
    case "step": {
      if (!event.step) return state;
      const steps = mergeSteps(state.steps, [event.step]);
      const run = state.run
        ? { ...state.run, n_steps: Math.max(state.run.n_steps, event.step.index + 1) }
        : state.run;
      return { ...state, steps, run };
    }
    case "status": {
      if (!event.status || !state.run) return state;
      const run: Run = { ...state.run, status: event.status };
      if (event.status === "running" && !run.started_at) run.started_at = event.timestamp;
      if (isTerminal(event.status) && !run.finished_at) run.finished_at = event.timestamp;
      return { ...state, run };
    }
    case "chat":
      return event.chat
        ? { ...state, ...confirmOutbox(state, [event.chat], state.chat), chat: mergeChat(state.chat, [event.chat]) }
        : state;
    case "log":
      return event.log
        ? { ...state, logs: [...state.logs, { timestamp: event.timestamp, message: event.log }].slice(-200) }
        : state;
    default:
      return state;
  }
}

export function runLiveReducer(state: RunLiveState, action: Action): RunLiveState {
  switch (action.type) {
    case "reset":
      return initialRunLiveState;
    case "loaded": {
      let next: RunLiveState = {
        ...state,
        run: action.run,
        steps: mergeSteps(action.steps, state.steps),
        ...confirmOutbox(state, action.chat, state.chat),
        chat: mergeChat(action.chat, state.chat),
        loading: false,
        error: null,
        pending: [],
      };
      for (const e of state.pending) next = applyEvent(next, e);
      return next;
    }
    case "event":
      if (state.loading) return { ...state, pending: [...state.pending, action.event] };
      return applyEvent(state, action.event);
    case "stream":
      return { ...state, stream: action.state };
    case "run":
      return { ...state, run: action.run };
    case "chat":
    {
      // Already echoed (the SSE event beat the POST response): consume that echo instead of adding.
      const echo = state.chat.find((m) => isEchoOf(m, action.message) && !state.acked.includes(chatKey(m)));
      if (echo) return { ...state, acked: [...state.acked, chatKey(echo)] };
      return { ...state, outbox: [...state.outbox, action.message] };
    }
    case "error":
      return { ...state, error: action.error, loading: false };
  }
}

/**
 * Loads a run (run + steps + chat) and keeps it live via the SSE event stream until
 * a terminal status arrives, then re-fetches once to pick up reward/error/finished_at.
 */
export function useRunLive(runId: string) {
  const [state, dispatch] = useReducer(runLiveReducer, initialRunLiveState);
  // Results from a previous run id (client-side navigation mid-fetch) must not land in this run's state.
  const currentRunId = useRef(runId);
  const isCurrent = useCallback(() => currentRunId.current === runId, [runId]);

  const reload = useCallback(async () => {
    const api = getApi();
    const [run, steps, chat] = await Promise.all([api.getRun(runId), api.listSteps(runId), api.listChat(runId)]);
    if (isCurrent()) dispatch({ type: "loaded", run, steps, chat });
    return run;
  }, [runId, isCurrent]);

  useEffect(() => {
    const api = getApi();
    let cancelled = false;
    let unsubscribe: (() => void) | undefined;
    currentRunId.current = runId;
    dispatch({ type: "reset" });

    // Subscribe first (buffering events) so nothing emitted during the initial fetch is lost.
    const subscribe = () =>
      api.subscribeRunEvents(runId, {
        onEvent: (event) => {
          if (cancelled) return;
          dispatch({ type: "event", event });
          if (event.type === "status" && event.status && isTerminal(event.status)) {
            setTimeout(() => {
              if (!cancelled) reload().catch(() => {});
            }, 300);
          }
        },
        onStateChange: (s) => !cancelled && dispatch({ type: "stream", state: s }),
      });

    unsubscribe = subscribe();
    reload()
      .then((run) => {
        if (cancelled) return;
        if (isTerminal(run.status)) {
          unsubscribe?.();
          unsubscribe = undefined;
          dispatch({ type: "stream", state: "closed" });
        }
      })
      .catch((error: Error) => !cancelled && dispatch({ type: "error", error }));

    return () => {
      cancelled = true;
      unsubscribe?.();
    };
  }, [runId, reload]);

  const cancel = useCallback(async () => {
    const run = await getApi().cancelRun(runId);
    if (isCurrent()) dispatch({ type: "run", run });
  }, [runId, isCurrent]);

  const sendChat = useCallback(
    async (message: string) => {
      const msg = await getApi().sendChat(runId, message);
      if (isCurrent()) dispatch({ type: "chat", message: msg });
    },
    [runId, isCurrent],
  );

  const { outbox, ...rest } = state;
  // Pending sends are placed by send time; Array.prototype.sort is stable for equal timestamps.
  const chat = useMemo(
    () => (outbox.length ? [...rest.chat, ...outbox].sort(byTime) : rest.chat),
    [rest.chat, outbox],
  );
  return { ...rest, chat, cancel, sendChat, reload };
}
