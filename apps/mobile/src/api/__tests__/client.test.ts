import { createHttpApi, normalizeBaseUrl, resolveUrl } from '../client';
import { parseRunEvent } from '../sse';

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('HTTP client', () => {
  it('normalizes base URLs and resolves relative artifact URLs', () => {
    expect(normalizeBaseUrl('http://localhost:8000/api/v1/')).toBe('http://localhost:8000/api/v1');
    expect(resolveUrl('http://h:8000/api/v1', '/api/v1/runs/r/steps/0/screenshot')).toBe(
      'http://h:8000/api/v1/runs/r/steps/0/screenshot',
    );
    expect(resolveUrl('http://h:8000/api/v1', 'https://cdn/x.png')).toBe('https://cdn/x.png');
  });

  it('calls contract paths with query params and JSON bodies', async () => {
    const calls: { url: string; method: string; body?: string }[] = [];
    const fetchImpl = (async (input: Request | string, init?: RequestInit) => {
      const req = input instanceof Request ? input : new Request(input, init);
      calls.push({ url: req.url, method: req.method, body: req.method === 'GET' ? undefined : await req.text() });
      if (req.url.includes('/runs?')) return jsonResponse({ items: [], next_cursor: null });
      if (req.url.endsWith('/chat')) return jsonResponse({ role: 'user', message: 'hi', timestamp: '2026-01-01T00:00:00Z' }, 201);
      if (req.url.endsWith('/devices')) return new Response(null, { status: 204 });
      return jsonResponse({ detail: 'nope' }, 404);
    }) as typeof fetch;
    const api = createHttpApi('http://host:8000/api/v1/', fetchImpl);

    await expect(api.listRuns({ status: 'running', limit: 5 })).resolves.toEqual({ items: [], next_cursor: null });
    await api.sendChat('run_1', 'hi');
    await api.registerDevice({ expo_push_token: 'ExponentPushToken[a]', platform: 'ios', run_ids: [] });
    await expect(api.getRun('missing')).rejects.toThrow();

    expect(calls[0].url).toBe('http://host:8000/api/v1/runs?status=running&limit=5');
    expect(calls[1]).toMatchObject({ url: 'http://host:8000/api/v1/runs/run_1/chat', method: 'POST' });
    expect(JSON.parse(calls[1].body!)).toEqual({ message: 'hi' });
    expect(calls[2]).toMatchObject({ url: 'http://host:8000/api/v1/devices', method: 'POST' });
    expect(JSON.parse(calls[2].body!)).toEqual({ expo_push_token: 'ExponentPushToken[a]', platform: 'ios', run_ids: [] });
  });
});

describe('parseRunEvent', () => {
  it('parses RunEvent JSON and rejects garbage', () => {
    expect(parseRunEvent('{"type":"status","run_id":"r","seq":1,"timestamp":"t","status":"running"}')).toMatchObject({
      type: 'status',
      status: 'running',
    });
    expect(parseRunEvent('not json')).toBeNull();
    expect(parseRunEvent('{"foo":1}')).toBeNull();
    expect(parseRunEvent(null)).toBeNull();
  });
});
