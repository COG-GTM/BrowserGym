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

/** Open the contract's SSE stream (`event:` = RunEvent.type, `data:` = JSON RunEvent). */
export function openRunEventStream(url: string, handlers: RunEventHandlers): Unsubscribe {
  const source = new EventSource<RunEventType>(url, { pollingInterval: 0 });
  let closed = false;

  const close = () => {
    if (closed) return;
    closed = true;
    source.removeAllEventListeners();
    source.close();
    handlers.onClose?.();
  };

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
  });

  return close;
}
