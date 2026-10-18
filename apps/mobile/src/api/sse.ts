import EventSource from 'react-native-sse';

import type { RunEventHandlers, Unsubscribe } from './client';
import { RUN_EVENT_TYPES, isTerminal, type RunEvent, type RunEventType } from './types';

export function parseRunEvent(data: string | null): RunEvent | null {
  if (!data) return null;
  try {
    const parsed = JSON.parse(data) as RunEvent;
    return parsed && typeof parsed.type === 'string' ? parsed : null;
  } catch {
    return null;
  }
}

export const RECONNECT_MS = 3000;

/**
 * Open the contract's SSE stream (`event:` = RunEvent.type, `data:` = JSON RunEvent).
 * After a dropped connection it reconnects every RECONNECT_MS until the run is terminal or the caller unsubscribes.
 */
export function openRunEventStream(url: string, handlers: RunEventHandlers): Unsubscribe {
  let source: EventSource<RunEventType>;
  let retry: ReturnType<typeof setTimeout> | undefined;
  let closed = false;
  let dropped = false;

  const teardown = () => {
    source.removeAllEventListeners();
    source.close();
  };

  const close = () => {
    if (closed) return;
    closed = true;
    if (retry) clearTimeout(retry);
    teardown();
    handlers.onClose?.();
  };

  const connect = () => {
    source = new EventSource<RunEventType>(url, { pollingInterval: 0 });
    source.addEventListener('open', () => {
      if (!dropped) return;
      dropped = false;
      handlers.onReconnect?.();
    });
    for (const type of RUN_EVENT_TYPES) {
      source.addEventListener(type, (event) => {
        const parsed = parseRunEvent(event.data);
        if (!parsed) return;
        handlers.onEvent(parsed);
        if (parsed.type === 'status' && parsed.status && isTerminal(parsed.status)) close();
      });
    }
    source.addEventListener('error', (event) => {
      if (closed) return;
      const message = 'message' in event ? event.message : 'stream timeout';
      handlers.onError?.(new Error(message || 'SSE stream error'));
      dropped = true;
      teardown();
      retry = setTimeout(() => {
        if (!closed) connect();
      }, RECONNECT_MS);
    });
  };

  connect();
  return close;
}
