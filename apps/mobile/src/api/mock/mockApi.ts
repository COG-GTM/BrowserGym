import type { RunEventHandlers, SideApi } from '../client';
import { ApiError } from '../client';
import {
  isTerminal,
  type AgentConfig,
  type ChatMessage,
  type Run,
  type RunCreate,
  type RunEvent,
  type RunStatus,
  type Step,
  type StepDetail,
} from '../types';
import {
  CLICK_TEST_SCRIPT,
  MOCK_AGENTS,
  MOCK_SCREENSHOTS,
  MOCK_TASKS,
  openendedScript,
  taskScript,
  type MockScreenshotKey,
  type ScriptStep,
} from './fixtures';

export interface MockApiOptions {
  /** Delay between simulated agent steps. */
  stepIntervalMs?: number;
  /** Delay before a queued run starts. */
  startDelayMs?: number;
  /** Simulated network latency for every call. */
  latencyMs?: number;
  /** Seed the store with demo runs (incl. one live run). */
  seed?: boolean;
  now?: () => number;
}

interface RunState {
  run: Run;
  steps: StepDetail[];
  screenshots: (MockScreenshotKey | null)[];
  chat: ChatMessage[];
  script: ScriptStep[];
  inbox: string[];
  cancelRequested: boolean;
  /** Seeded live run steps slower so there is time to watch it. */
  slow?: boolean;
  timer?: ReturnType<typeof setTimeout>;
}

export const LIVE_RUN_ID = 'run_live_demo';

const DEFAULT_AGENT: AgentConfig = { type: 'mock', model: null, use_screenshot: false, use_axtree: true };

export class MockSideApi implements SideApi {
  readonly mode = 'mock' as const;
  private runs = new Map<string, RunState>();
  private order: string[] = [];
  private listeners = new Map<string, Set<RunEventHandlers>>();
  private devices: { expo_push_token: string; platform: string }[] = [];
  private seq = 0;
  private demoTimer?: ReturnType<typeof setTimeout>;
  private disposed = false;
  private readonly stepIntervalMs: number;
  private readonly startDelayMs: number;
  private readonly latencyMs: number;
  private readonly now: () => number;

  constructor(options: MockApiOptions = {}) {
    this.stepIntervalMs = options.stepIntervalMs ?? 2200;
    this.startDelayMs = options.startDelayMs ?? 900;
    this.latencyMs = options.latencyMs ?? 120;
    this.now = options.now ?? Date.now;
    if (options.seed ?? true) this.seed();
  }

  // ---- contract operations -------------------------------------------------

  async getHealth() {
    await this.delay();
    return { status: 'ok' as const, version: '0.1.0-mock' };
  }

  async listTasks(query: { benchmark?: string; q?: string } = {}) {
    await this.delay();
    const q = query.q?.trim().toLowerCase();
    return MOCK_TASKS.filter(
      (t) =>
        (!query.benchmark || t.benchmark === query.benchmark) &&
        (!q || `${t.id} ${t.title} ${t.description ?? ''}`.toLowerCase().includes(q)),
    );
  }

  async listAgents() {
    await this.delay();
    return MOCK_AGENTS;
  }

  async listRuns(query: { status?: RunStatus; limit?: number; cursor?: string } = {}) {
    await this.delay();
    const limit = Math.min(query.limit ?? 50, 200);
    const all = this.order
      .map((id) => this.runs.get(id)!.run)
      .filter((r) => !query.status || r.status === query.status);
    const start = query.cursor ? Number(query.cursor) || 0 : 0;
    const items = all.slice(start, start + limit).map(clone);
    const next = start + limit < all.length ? String(start + limit) : null;
    return { items, next_cursor: next };
  }

  async createRun(body: RunCreate) {
    await this.delay();
    const task = MOCK_TASKS.find((t) => t.id === body.task_id);
    if (!task) throw new ApiError(`Unknown task ${body.task_id}`, 422);
    if (task.id === 'browsergym/openended' && !body.goal?.trim()) {
      throw new ApiError('goal is required for browsergym/openended', 422);
    }
    const maxSteps = body.max_steps ?? 15;
    if (maxSteps < 1 || maxSteps > 100) throw new ApiError('max_steps must be between 1 and 100', 422);
    const id = `run_${this.now().toString(36)}${(++this.seq).toString(36)}`;
    const run: Run = {
      id,
      task_id: body.task_id,
      goal: body.goal ?? task.description ?? null,
      agent: { ...DEFAULT_AGENT, ...body.agent },
      status: 'queued',
      reward: null,
      n_steps: 0,
      max_steps: maxSteps,
      created_at: this.iso(),
      started_at: null,
      finished_at: null,
      error: null,
    };
    const script = taskScript(task.id, body.goal ?? '', body.start_url || 'https://example.com/') ?? [];
    const state = this.insert(run, script);
    if (task.requires_setup || script.length === 0) {
      const reason = task.requires_setup
        ? `${task.benchmark} requires external setup (env vars / servers)`
        : `No offline replay for ${task.id} in mock mode`;
      state.timer = setTimeout(() => this.finish(state, 'failed', reason), this.startDelayMs);
    } else {
      state.timer = setTimeout(() => this.start(state), this.startDelayMs);
    }
    return clone(run);
  }

  async getRun(runId: string) {
    await this.delay();
    return clone(this.get(runId).run);
  }

  async deleteRun(runId: string) {
    await this.delay();
    const state = this.runs.get(runId);
    if (state?.timer) clearTimeout(state.timer);
    this.runs.delete(runId);
    this.order = this.order.filter((id) => id !== runId);
    this.listeners.delete(runId);
  }

  async cancelRun(runId: string) {
    await this.delay();
    const state = this.get(runId);
    if (state.run.status === 'queued') {
      if (state.timer) clearTimeout(state.timer);
      this.finish(state, 'cancelled');
    } else if (state.run.status === 'running') {
      state.cancelRequested = true;
      this.emit(state, { type: 'log', log: 'Cancel requested; stopping after the current step.' });
    }
    return clone(state.run);
  }

  async listSteps(runId: string): Promise<Step[]> {
    await this.delay();
    return this.get(runId).steps.map(toStep);
  }

  async getStep(runId: string, index: number) {
    await this.delay();
    const step = this.get(runId).steps[index];
    if (!step) throw new ApiError(`Step ${index} not found`, 404);
    return clone(step);
  }

  async listChat(runId: string) {
    await this.delay();
    return this.get(runId).chat.map(clone);
  }

  async sendChat(runId: string, message: string) {
    await this.delay();
    if (!message.trim()) throw new ApiError('message must not be empty', 422);
    const state = this.get(runId);
    const msg: ChatMessage = { role: 'user', message, timestamp: this.iso() };
    state.chat.push(msg);
    if (state.run.status === 'running' || state.run.status === 'queued') state.inbox.push(message);
    this.emit(state, { type: 'chat', chat: msg });
    return clone(msg);
  }

  async registerDevice(body: { expo_push_token: string; platform: string }) {
    await this.delay();
    this.devices.push({ expo_push_token: body.expo_push_token, platform: body.platform });
  }

  get registeredDevices() {
    return [...this.devices];
  }

  screenshotSource(runId: string, step: Step) {
    if (!step.screenshot_url) return null;
    const key = this.runs.get(runId)?.screenshots[step.index];
    return key ? (MOCK_SCREENSHOTS[key] as number) : null;
  }

  subscribeRunEvents(runId: string, handlers: RunEventHandlers) {
    const state = this.runs.get(runId);
    let active = true;
    if (!state) {
      setTimeout(() => active && handlers.onError?.(new ApiError('Run not found', 404)), 0);
      return () => {
        active = false;
      };
    }
    if (isTerminal(state.run.status)) {
      // Like the real stream: replay the terminal status, then close.
      setTimeout(() => {
        if (!active) return;
        handlers.onEvent(this.event(state, { type: 'status', status: state.run.status }));
        handlers.onClose?.();
      }, 0);
      return () => {
        active = false;
      };
    }
    let set = this.listeners.get(runId);
    if (!set) this.listeners.set(runId, (set = new Set()));
    set.add(handlers);
    return () => {
      active = false;
      this.listeners.get(runId)?.delete(handlers);
    };
  }

  /** Stop every simulated timer (tests). */
  dispose() {
    this.disposed = true;
    if (this.demoTimer) clearTimeout(this.demoTimer);
    for (const state of this.runs.values()) if (state.timer) clearTimeout(state.timer);
    this.listeners.clear();
  }

  // ---- simulation -----------------------------------------------------------

  private start(state: RunState) {
    state.run.status = 'running';
    state.run.started_at = this.iso();
    this.emit(state, { type: 'status', status: 'running' });
    this.emit(state, { type: 'log', log: `Runner started ${state.run.task_id} with agent=${state.run.agent.type}` });
    this.tick(state);
  }

  private tick(state: RunState) {
    if (!this.runs.has(state.run.id) || isTerminal(state.run.status)) return;
    const index = state.steps.length;
    const scripted = state.script[index];
    if (!scripted) {
      this.finish(state, 'succeeded');
      return;
    }
    const step: StepDetail = {
      index,
      action: scripted.action,
      thought: scripted.thought,
      url: scripted.url,
      reward: scripted.reward ?? 0,
      terminated: Boolean(scripted.terminated),
      truncated: false,
      last_action_error: scripted.error ?? null,
      screenshot_url: scripted.screenshot ? `/runs/${state.run.id}/steps/${index}/screenshot` : null,
      elapsed_ms: 650 + ((index * 337) % 900),
      timestamp: this.iso(),
      axtree_txt: `RootWebArea '${state.run.task_id}'\n  [a12] textbox 'Name'\n  [a17] textbox 'Email'\n  [a31] button 'Submit'`,
      pruned_html: null,
      focused_element_bid: null,
    };
    const atLimit = state.run.max_steps != null && index + 1 >= state.run.max_steps && !step.terminated;
    if (atLimit) step.truncated = true;
    state.steps.push(step);
    state.screenshots.push(scripted.screenshot);
    state.run.n_steps = state.steps.length;
    this.emit(state, { type: 'step', step: toStep(step) });

    const reply = state.inbox.shift();
    if (reply !== undefined) {
      this.pushChat(state, 'assistant', `Got it — “${reply}”. I'll take that into account on the next step.`);
    }
    if (scripted.chat) this.pushChat(state, 'assistant', scripted.chat);

    if (step.terminated) {
      state.run.reward = step.reward;
      this.finish(state, step.reward > 0 || !state.run.task_id.includes('miniwob') ? 'succeeded' : 'failed');
      return;
    }
    if (step.truncated) {
      state.run.reward = 0;
      this.finish(state, 'failed', `Truncated after max_steps=${state.run.max_steps}`);
      return;
    }
    if (state.cancelRequested) {
      this.finish(state, 'cancelled');
      return;
    }
    state.timer = setTimeout(() => this.tick(state), this.stepIntervalMs * (state.slow ? 2 : 1));
  }

  private finish(state: RunState, status: RunStatus, error?: string) {
    state.run.status = status;
    state.run.finished_at = this.iso();
    if (error) state.run.error = error;
    if (status === 'cancelled') this.pushChat(state, 'info', 'Run cancelled by user.');
    if (error) this.pushChat(state, 'info', error);
    this.emit(state, { type: 'status', status });
    this.listeners.delete(state.run.id);
    if (state.slow && !this.disposed) this.demoTimer = setTimeout(() => this.startLiveDemo(), this.stepIntervalMs * 3);
  }

  /** Keep a live demo run around in mock mode: a fresh one starts after the previous one ends. */
  private startLiveDemo() {
    if (this.disposed) return;
    const id = `${LIVE_RUN_ID}_${(++this.seq).toString(36)}`;
    const run: Run = {
      id,
      task_id: 'browsergym/miniwob.click-test',
      goal: MOCK_TASKS.find((t) => t.id === 'browsergym/miniwob.click-test')?.description ?? null,
      agent: { type: 'openai', model: 'gpt-4o', use_screenshot: true, use_axtree: true },
      status: 'queued',
      reward: null,
      n_steps: 0,
      max_steps: 15,
      created_at: this.iso(),
      started_at: null,
      finished_at: null,
      error: null,
    };
    const state = this.insert(run, CLICK_TEST_SCRIPT);
    state.slow = true;
    state.timer = setTimeout(() => this.start(state), this.startDelayMs);
  }

  private pushChat(state: RunState, role: ChatMessage['role'], message: string) {
    const msg: ChatMessage = { role, message, timestamp: this.iso() };
    state.chat.push(msg);
    this.emit(state, { type: 'chat', chat: msg });
  }

  private emit(state: RunState, partial: Omit<RunEvent, 'run_id' | 'timestamp'>) {
    const event = this.event(state, partial);
    for (const handlers of [...(this.listeners.get(state.run.id) ?? [])]) {
      handlers.onEvent(clone(event));
      if (event.type === 'status' && event.status && isTerminal(event.status)) handlers.onClose?.();
    }
  }

  private event(state: RunState, partial: Omit<RunEvent, 'run_id' | 'timestamp'>): RunEvent {
    return { ...partial, run_id: state.run.id, timestamp: this.iso() };
  }

  // ---- helpers ----------------------------------------------------------------

  private insert(run: Run, script: ScriptStep[]): RunState {
    const state: RunState = { run, steps: [], screenshots: [], chat: [], script, inbox: [], cancelRequested: false };
    this.runs.set(run.id, state);
    this.order.unshift(run.id);
    return state;
  }

  private get(runId: string): RunState {
    const state = this.runs.get(runId);
    if (!state) throw new ApiError(`Run ${runId} not found`, 404);
    return state;
  }

  private iso(offsetMs = 0) {
    return new Date(this.now() + offsetMs).toISOString();
  }

  private delay() {
    return this.latencyMs > 0 ? new Promise<void>((r) => setTimeout(r, this.latencyMs)) : Promise.resolve();
  }

  /** Demo history (oldest first) plus one run that is live right now. */
  private seed() {
    const min = 60_000;
    const hist = (
      id: string,
      taskId: string,
      agent: AgentConfig,
      status: RunStatus,
      agoMin: number,
      opts: { script?: ScriptStep[]; reward?: number | null; error?: string; goal?: string; maxSteps?: number } = {},
    ) => {
      const created = -agoMin * min;
      const script = opts.script ?? [];
      const run: Run = {
        id,
        task_id: taskId,
        goal: opts.goal ?? MOCK_TASKS.find((t) => t.id === taskId)?.description ?? null,
        agent,
        status,
        reward: opts.reward ?? null,
        n_steps: script.length,
        max_steps: opts.maxSteps ?? 15,
        created_at: this.iso(created),
        started_at: status === 'queued' ? null : this.iso(created + 4000),
        finished_at: isTerminal(status) ? this.iso(created + 4000 + script.length * 2600 + 1500) : null,
        error: opts.error ?? null,
      };
      const state = this.insert(run, script);
      script.forEach((s, index) => {
        state.steps.push({
          index,
          action: s.action,
          thought: s.thought,
          url: s.url,
          reward: s.reward ?? 0,
          terminated: Boolean(s.terminated),
          truncated: false,
          last_action_error: s.error ?? null,
          screenshot_url: s.screenshot ? `/runs/${id}/steps/${index}/screenshot` : null,
          elapsed_ms: 700 + index * 120,
          timestamp: this.iso(created + 4000 + index * 2600),
          axtree_txt: null,
          pruned_html: null,
          focused_element_bid: null,
        });
        state.screenshots.push(s.screenshot);
        if (s.chat) state.chat.push({ role: 'assistant', message: s.chat, timestamp: this.iso(created + 4000 + index * 2600) });
      });
      if (opts.error) state.chat.push({ role: 'info', message: opts.error, timestamp: run.finished_at ?? this.iso(created) });
      return state;
    };

    const gpt: AgentConfig = { type: 'openai', model: 'gpt-4o', use_screenshot: true, use_axtree: true };
    const claude: AgentConfig = { type: 'anthropic', model: 'claude-sonnet-4-5', use_screenshot: false, use_axtree: true };

    hist('run_wa310', 'browsergym/webarena.310', gpt, 'failed', 60 * 26, {
      error: 'WA_SHOPPING_ADMIN is not set; webarena requires external servers.',
    });
    hist('run_bookflight', 'browsergym/miniwob.book-flight', gpt, 'failed', 60 * 5, {
      script: CLICK_TEST_SCRIPT.slice(0, 3).map((s) => ({ ...s, chat: undefined })),
      reward: 0,
      maxSteps: 3,
      error: 'Truncated after max_steps=3',
    });
    hist('run_seq', 'browsergym/miniwob.click-button-sequence', claude, 'succeeded', 60 * 3, {
      script: CLICK_TEST_SCRIPT,
      reward: 1,
    });
    hist('run_example', 'browsergym/openended', claude, 'cancelled', 95, {
      script: openendedScript('Summarise example.com', 'https://example.com/').slice(0, 2),
      goal: 'Summarise example.com',
    });
    hist('run_clicktest', 'browsergym/miniwob.click-test', DEFAULT_AGENT, 'succeeded', 22, {
      script: CLICK_TEST_SCRIPT,
      reward: 1,
    });
    hist('run_login_queued', 'browsergym/miniwob.login-user', { ...DEFAULT_AGENT, type: 'scripted' }, 'queued', 1);

    const live = hist(LIVE_RUN_ID, 'browsergym/miniwob.click-test', gpt, 'running', 0.5, {
      script: CLICK_TEST_SCRIPT.slice(0, 1),
    });
    live.run.n_steps = live.steps.length;
    live.run.finished_at = null;
    live.script = CLICK_TEST_SCRIPT;
    // The live run keeps stepping on its own; the UI follows it over the (mock) SSE stream.
    live.timer = setTimeout(() => this.tick(live), this.stepIntervalMs * 2);
    live.slow = true;
  }
}

function toStep(detail: StepDetail): Step {
  const { axtree_txt: _a, pruned_html: _p, focused_element_bid: _f, ...step } = detail;
  return { ...step };
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}
