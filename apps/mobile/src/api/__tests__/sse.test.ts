import { RECONNECT_MS, openRunEventStream } from '../sse';

type Listener = (event: { data?: string | null; message?: string }) => void;

const instances: MockEventSource[] = [];

class MockEventSource {
  listeners: Record<string, Listener[]> = {};
  closed = false;
  constructor(public url: string) {
    instances.push(this);
  }
  addEventListener(type: string, fn: Listener) {
    (this.listeners[type] ??= []).push(fn);
  }
  removeAllEventListeners() {
    this.listeners = {};
  }
  close() {
    this.closed = true;
  }
  emit(type: string, event: { data?: string | null; message?: string } = {}) {
    for (const fn of this.listeners[type] ?? []) fn(event);
  }
}

jest.mock('react-native-sse', () => ({ __esModule: true, default: jest.fn((url: string) => new MockEventSource(url)) }));

const status = (s: string) => JSON.stringify({ type: 'status', run_id: 'r', timestamp: 't', status: s });

describe('openRunEventStream', () => {
  beforeEach(() => {
    instances.length = 0;
    jest.useFakeTimers();
  });
  afterEach(() => jest.useRealTimers());

  it('reconnects after a drop, signals onReconnect, and stops on a terminal status', () => {
    const handlers = { onEvent: jest.fn(), onError: jest.fn(), onClose: jest.fn(), onReconnect: jest.fn() };
    openRunEventStream('http://h/api/v1/runs/r/events', handlers);
    instances[0].emit('open');
    instances[0].emit('status', { data: status('running') });
    expect(handlers.onEvent).toHaveBeenCalledTimes(1);

    instances[0].emit('error', { message: 'network down' });
    expect(handlers.onError).toHaveBeenCalled();
    expect(instances[0].closed).toBe(true);
    jest.advanceTimersByTime(RECONNECT_MS);
    expect(instances).toHaveLength(2);

    instances[1].emit('open');
    expect(handlers.onReconnect).toHaveBeenCalledTimes(1);
    instances[1].emit('status', { data: status('succeeded') });
    expect(handlers.onClose).toHaveBeenCalledTimes(1);
    expect(instances[1].closed).toBe(true);
  });

  it('does not reconnect after unsubscribe', () => {
    const unsubscribe = openRunEventStream('http://h/x', { onEvent: jest.fn() });
    instances[0].emit('error', { message: 'boom' });
    unsubscribe();
    jest.advanceTimersByTime(RECONNECT_MS * 2);
    expect(instances).toHaveLength(1);
  });
});
