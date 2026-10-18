import { RUN_EVENT_TYPES, isTerminal, type RunEvent } from "./types";

export type StreamState = "connecting" | "open" | "reconnecting" | "closed";

export interface RunEventHandlers {
  onEvent: (event: RunEvent) => void;
  onStateChange?: (state: StreamState) => void;
}

export type Unsubscribe = () => void;

type EventSourceCtor = new (url: string) => EventSource;

export function parseRunEvent(data: string): RunEvent | null {
  try {
    const parsed = JSON.parse(data) as Partial<RunEvent>;
    if (!parsed || typeof parsed !== "object") return null;
    if (!parsed.type || !RUN_EVENT_TYPES.includes(parsed.type)) return null;
    if (typeof parsed.run_id !== "string" || typeof parsed.timestamp !== "string") return null;
    return parsed as RunEvent;
  } catch {
    return null;
  }
}

/**
 * Subscribe to `GET /runs/{id}/events`. Each SSE event is named after RunEvent.type;
 * the stream is closed client-side after a terminal `status` event so EventSource
 * does not auto-reconnect.
 */
export function openRunEventStream(
  url: string,
  handlers: RunEventHandlers,
  EventSourceImpl: EventSourceCtor | undefined = typeof EventSource !== "undefined" ? EventSource : undefined,
): Unsubscribe {
  if (!EventSourceImpl) {
    handlers.onStateChange?.("closed");
    return () => {};
  }
  const source = new EventSourceImpl(url);
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    source.close();
    handlers.onStateChange?.("closed");
  };

  handlers.onStateChange?.("connecting");
  source.onopen = () => handlers.onStateChange?.("open");
  source.onerror = () => {
    if (closed) return;
    // CONNECTING (0) means the browser is retrying; CLOSED (2) is final.
    if (source.readyState === 2) close();
    else handlers.onStateChange?.("reconnecting");
  };

  const listener = (msg: MessageEvent<string>) => {
    const event = parseRunEvent(msg.data);
    if (!event) return;
    handlers.onEvent(event);
    if (event.type === "status" && event.status && isTerminal(event.status)) close();
  };
  for (const type of RUN_EVENT_TYPES) source.addEventListener(type, listener as EventListener);
  source.onmessage = listener;

  return close;
}
