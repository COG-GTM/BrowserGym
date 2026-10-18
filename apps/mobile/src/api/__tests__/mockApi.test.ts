import { LIVE_RUN_ID, MockSideApi } from '../mock/mockApi';
import type { RunEvent } from '../types';
import { runBody } from '@/test/render';

function fastApi() {
  return new MockSideApi({ latencyMs: 0, startDelayMs: 0, stepIntervalMs: 5 });
}

function waitForTerminal(api: MockSideApi, runId: string): Promise<RunEvent[]> {
  return new Promise((resolve, reject) => {
    const events: RunEvent[] = [];
    api.subscribeRunEvents(runId, {
      onEvent: (e) => events.push(e),
      onError: reject,
      onClose: () => resolve(events),
    });
  });
}

describe('MockSideApi', () => {
  let api: MockSideApi;
  beforeEach(() => {
    api = fastApi();
  });
  afterEach(() => api.dispose());

  it('seeds runs including a simulated live run and filters by status', async () => {
    const all = await api.listRuns();
    expect(all.items.length).toBeGreaterThan(3);
    expect(all.items.some((r) => r.id === LIVE_RUN_ID && r.status === 'running')).toBe(true);
    const succeeded = await api.listRuns({ status: 'succeeded' });
    expect(succeeded.items.length).toBeGreaterThan(0);
    expect(succeeded.items.every((r) => r.status === 'succeeded')).toBe(true);
  });

  it('paginates with next_cursor', async () => {
    const first = await api.listRuns({ limit: 2 });
    expect(first.items).toHaveLength(2);
    expect(first.next_cursor).not.toBeNull();
    const second = await api.listRuns({ limit: 2, cursor: first.next_cursor! });
    expect(second.items[0].id).not.toBe(first.items[0].id);
  });

  it('searches tasks', async () => {
    const tasks = await api.listTasks({ q: 'login' });
    expect(tasks.map((t) => t.id)).toContain('browsergym/miniwob.login-user');
  });

  it('runs a created episode to success, streaming status and step events in order', async () => {
    const run = await api.createRun(runBody('browsergym/miniwob.click-test', { max_steps: 10 }));
    expect(run.status).toBe('queued');
    const events = await waitForTerminal(api, run.id);
    const statuses = events.filter((e) => e.type === 'status').map((e) => e.status);
    expect(statuses[0]).toBe('running');
    expect(statuses.at(-1)).toBe('succeeded');
    const steps = events.filter((e) => e.type === 'step').map((e) => e.step!.index);
    expect(steps).toEqual([...steps].sort((a, b) => a - b));
    const final = await api.getRun(run.id);
    expect(final.reward).toBe(1);
    expect(final.n_steps).toBe(steps.length);
    expect(await api.listSteps(run.id)).toHaveLength(steps.length);
  });

  it('requires a goal for open-ended runs', async () => {
    await expect(api.createRun(runBody('browsergym/openended'))).rejects.toThrow(/goal/);
  });

  it('cancels a running run after the current step', async () => {
    const run = await api.createRun(runBody('browsergym/miniwob.click-test'));
    const done = waitForTerminal(api, run.id);
    await new Promise((r) => setTimeout(r, 8));
    await api.cancelRun(run.id);
    await done;
    expect((await api.getRun(run.id)).status).toBe('cancelled');
  });

  it('stores chat and replies from the agent', async () => {
    const msg = await api.sendChat(LIVE_RUN_ID, 'please hurry');
    expect(msg.role).toBe('user');
    const chat = await api.listChat(LIVE_RUN_ID);
    expect(chat.some((m) => m.message === 'please hurry')).toBe(true);
  });

  it('registers devices', async () => {
    await api.registerDevice({ expo_push_token: 'ExponentPushToken[x]', platform: 'android' });
    expect(api.registeredDevices).toEqual([{ expo_push_token: 'ExponentPushToken[x]', platform: 'android' }]);
  });
});
