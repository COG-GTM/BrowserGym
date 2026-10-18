import { ApiError, type SideApi } from "../api/client";
import type { RunEventHandlers } from "../api/sse";
import {
  AGENTS,
  TASKS,
  buildStep,
  episodeScript,
  findTask,
  rng,
  screenshotSvg,
  seedHistory,
  svgDataUri,
  type EpisodeScript,
  type MockStep,
} from "./fixtures";
import {
  OPENENDED_TASK_ID,
  isTerminal,
  type ChatMessage,
  type Run,
  type RunCreate,
  type RunEvent,
  type RunStatus,
  type Step,
  type StepDetail,
} from "../api/types";

export interface MockOptions {
  /** Artificial network latency in ms (default 180). */
  latencyMs?: number;
  /** Interval between simulated steps in ms (default 1600). */
  stepIntervalMs?: number;
  /** Seed history size (default 42). */
  seedCount?: number;
  /** Start the built-in live demo run (default true). */
  liveDemo?: boolean;
  now?: () => number;
}

interface RunState {
  run: Run;
  steps: MockStep[];
  chat: ChatMessage[];
  script: EpisodeScript;
  plan?: { target: number; outcome: RunStatus; error?: string };
  timer?: ReturnType<typeof setTimeout>;
}

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

function stripStep(step: MockStep): Step {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { _frame, axtree_txt, pruned_html, focused_element_bid, ...rest } = step;
  return clone(rest);
}

function stripDetail(step: MockStep): StepDetail {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { _frame, ...rest } = step;
  return clone(rest);
}

export const LIVE_DEMO_RUN_ID = "run_live_demo";

export class MockBackend {
  private runs: RunState[] = [];
  private listeners = new Map<string, Set<RunEventHandlers>>();
  private screenshotCache = new Map<string, string>();
  private readonly latency: number;
  private readonly stepInterval: number;
  private readonly now: () => number;
  private counter = 0;

  constructor(opts: MockOptions = {}) {
    this.latency = opts.latencyMs ?? 180;
    this.stepInterval = opts.stepIntervalMs ?? 1600;
    this.now = opts.now ?? (() => Date.now());
    const now = this.now();
    for (const seed of seedHistory(now, opts.seedCount ?? 42)) {
      const task = findTask(seed.run.task_id)!;
      this.runs.push({ ...seed, script: episodeScript(task, seed.run.goal) });
    }
    if (opts.liveDemo ?? true) this.seedLiveDemo(now);
  }

  /* ---------------------------- helpers ---------------------------- */

  private iso(t = this.now()): string {
    return new Date(t).toISOString();
  }

  private async delay<T>(value: () => T): Promise<T> {
    if (this.latency > 0) await new Promise((r) => setTimeout(r, this.latency));
    return value();
  }

  private get(runId: string): RunState {
    const s = this.runs.find((r) => r.run.id === runId);
    if (!s) throw new ApiError(404, `Run ${runId} not found`);
    return s;
  }

  private emit(runId: string, partial: Omit<RunEvent, "run_id" | "timestamp">) {
    const event: RunEvent = { run_id: runId, timestamp: this.iso(), ...partial };
    for (const h of this.listeners.get(runId) ?? []) {
      h.onEvent(clone(event));
      if (event.type === "status" && event.status && isTerminal(event.status)) h.onStateChange?.("closed");
    }
    if (event.type === "status" && event.status && isTerminal(event.status)) this.listeners.delete(runId);
  }

  private pushChat(state: RunState, msg: ChatMessage) {
    state.chat.push(msg);
    this.emit(state.run.id, { type: "chat", chat: msg });
  }

  private setStatus(state: RunState, status: RunStatus) {
    state.run.status = status;
    const now = this.iso();
    if (status === "running" && !state.run.started_at) state.run.started_at = now;
    if (isTerminal(status)) state.run.finished_at = now;
    this.emit(state.run.id, { type: "status", status });
  }

  /* -------------------------- simulation --------------------------- */

  private seedLiveDemo(now: number) {
    const task = findTask(OPENENDED_TASK_ID)!;
    const goal = "Find the latest BrowserGym release on GitHub and report its version.";
    const run: Run = {
      id: LIVE_DEMO_RUN_ID,
      task_id: task.id,
      goal,
      agent: { type: "mock", model: null, use_screenshot: false, use_axtree: true },
      status: "running",
      reward: null,
      n_steps: 0,
      max_steps: 15,
      created_at: this.iso(now - 9_000),
      started_at: this.iso(now - 8_000),
      finished_at: null,
      error: null,
    };
    const state: RunState = {
      run,
      steps: [],
      chat: [{ role: "info", message: `Goal: ${goal}`, timestamp: run.started_at! }],
      script: episodeScript(task, goal, "https://github.com/ServiceNow/BrowserGym"),
      plan: { target: 8, outcome: "succeeded" },
    };
    this.runs.unshift(state);
    for (let i = 0; i < 2; i++) this.appendStep(state, false);
    this.schedule(state, this.stepInterval);
  }

  private appendStep(state: RunState, emit = true) {
    const plan = state.plan!;
    const index = state.steps.length;
    const isFinal = index === plan.target - 1;
    const startedAt = Date.parse(state.run.started_at ?? state.run.created_at);
    const step = buildStep(state.run, state.script, index, {
      isFinal,
      startedAt,
      outcome: plan.outcome,
      error: plan.error,
    });
    step.timestamp = this.iso();
    state.steps.push(step);
    state.run.n_steps = state.steps.length;
    if (emit) this.emit(state.run.id, { type: "step", step: stripStep(step) });
  }

  private schedule(state: RunState, ms: number) {
    clearTimeout(state.timer);
    state.timer = setTimeout(() => this.tick(state), ms);
  }

  private tick(state: RunState) {
    const plan = state.plan;
    if (!plan || isTerminal(state.run.status)) return;
    if (state.run.status === "queued") {
      this.setStatus(state, "running");
      this.emit(state.run.id, { type: "log", log: `side_runner started for ${state.run.task_id}` });
      this.schedule(state, this.stepInterval);
      return;
    }
    if (plan.outcome === "failed" && plan.target === 0) {
      state.run.error = plan.error ?? "Runner failed";
      state.run.reward = 0;
      this.pushChat(state, { role: "info", message: state.run.error, timestamp: this.iso() });
      this.setStatus(state, "failed");
      return;
    }
    this.appendStep(state);
    if (state.steps.length >= plan.target) {
      state.run.reward = plan.outcome === "succeeded" ? 1 : 0;
      if (plan.outcome === "succeeded") {
        this.pushChat(state, { role: "assistant", message: state.script.answer, timestamp: this.iso() });
      } else {
        state.run.error = plan.error ?? `Episode truncated after ${state.steps.length} steps.`;
        this.pushChat(state, { role: "info", message: state.run.error, timestamp: this.iso() });
      }
      this.setStatus(state, plan.outcome);
      return;
    }
    this.schedule(state, this.stepInterval);
  }

  /* ------------------------------ API ------------------------------ */

  listTasks(params?: { benchmark?: string; q?: string }) {
    return this.delay(() => {
      const q = params?.q?.trim().toLowerCase();
      return clone(
        TASKS.filter((t) => !params?.benchmark || t.benchmark === params.benchmark).filter(
          (t) => !q || [t.id, t.title, t.description ?? "", t.benchmark].some((f) => f.toLowerCase().includes(q)),
        ),
      );
    });
  }

  listAgents() {
    return this.delay(() => clone(AGENTS));
  }

  listRuns(params?: { status?: RunStatus; limit?: number; cursor?: string }) {
    return this.delay(() => {
      const limit = Math.min(Math.max(params?.limit ?? 50, 1), 200);
      const offset = params?.cursor ? Number.parseInt(params.cursor, 10) || 0 : 0;
      const all = this.runs.map((s) => s.run).filter((r) => !params?.status || r.status === params.status);
      const items = all.slice(offset, offset + limit);
      const next = offset + limit < all.length ? String(offset + limit) : null;
      return { items: clone(items), next_cursor: next };
    });
  }

  createRun(body: RunCreate) {
    return this.delay(() => {
      const task = findTask(body.task_id);
      if (!task) throw new ApiError(422, `Unknown task_id: ${body.task_id}`);
      if (task.id === OPENENDED_TASK_ID && !body.goal?.trim())
        throw new ApiError(422, "goal is required for browsergym/openended");
      const maxSteps = body.max_steps ?? 15;
      if (maxSteps < 1 || maxSteps > 100) throw new ApiError(422, "max_steps must be between 1 and 100");
      const now = this.now();
      const id = `run_${now.toString(36).slice(-6)}${(this.counter++).toString(36)}`;
      const r = rng(id);
      const run: Run = {
        id,
        task_id: task.id,
        goal: body.goal?.trim() || task.description || null,
        agent: {
          type: body.agent.type,
          model: body.agent.model ?? null,
          use_screenshot: body.agent.use_screenshot ?? false,
          use_axtree: body.agent.use_axtree ?? true,
        },
        status: "queued",
        reward: null,
        n_steps: 0,
        max_steps: maxSteps,
        created_at: this.iso(now),
        started_at: null,
        finished_at: null,
        error: null,
      };
      const needsSetup = task.requires_setup;
      const target = needsSetup ? 0 : Math.min(maxSteps, r.int(5, 8));
      const reachedMax = !needsSetup && target === maxSteps && maxSteps < 5;
      const state: RunState = {
        run,
        steps: [],
        chat: [{ role: "info", message: `Goal: ${run.goal ?? task.title}`, timestamp: run.created_at }],
        script: episodeScript(task, run.goal, body.start_url),
        plan: {
          target,
          outcome: needsSetup || reachedMax ? "failed" : "succeeded",
          error: needsSetup
            ? `${task.benchmark} requires external setup (environment variables / servers) that is not configured in mock mode.`
            : undefined,
        },
      };
      this.runs.unshift(state);
      this.schedule(state, 900);
      return clone(run);
    });
  }

  getRun(runId: string) {
    return this.delay(() => clone(this.get(runId).run));
  }

  deleteRun(runId: string) {
    return this.delay(() => {
      const s = this.get(runId);
      clearTimeout(s.timer);
      this.runs = this.runs.filter((r) => r !== s);
      this.listeners.delete(runId);
    });
  }

  cancelRun(runId: string) {
    return this.delay(() => {
      const s = this.get(runId);
      if (!isTerminal(s.run.status)) {
        clearTimeout(s.timer);
        s.run.reward = 0;
        this.pushChat(s, { role: "info", message: "Run cancelled by user.", timestamp: this.iso() });
        this.setStatus(s, "cancelled");
      }
      return clone(s.run);
    });
  }

  listSteps(runId: string) {
    return this.delay(() => this.get(runId).steps.map(stripStep));
  }

  getStep(runId: string, index: number) {
    return this.delay(() => {
      const step = this.get(runId).steps[index];
      if (!step) throw new ApiError(404, `Step ${index} not found`);
      return stripDetail(step);
    });
  }

  listChat(runId: string) {
    return this.delay(() => clone(this.get(runId).chat));
  }

  sendChat(runId: string, message: string) {
    return this.delay(() => {
      const s = this.get(runId);
      if (!message.trim()) throw new ApiError(422, "message must not be empty");
      const msg: ChatMessage = { role: "user", message: message.trim(), timestamp: this.iso() };
      this.pushChat(s, msg);
      if (!isTerminal(s.run.status)) {
        setTimeout(() => {
          if (isTerminal(s.run.status)) return;
          this.pushChat(s, {
            role: "assistant",
            message: `Got it — I'll take “${clip(msg.message, 60)}” into account on my next step.`,
            timestamp: this.iso(),
          });
        }, 1100);
      }
      return clone(msg);
    });
  }

  screenshotSrc(runId: string, step: Pick<Step, "index" | "screenshot_url">): string | null {
    if (!step.screenshot_url) return null;
    const key = `${runId}:${step.index}`;
    const cached = this.screenshotCache.get(key);
    if (cached) return cached;
    const s = this.runs.find((r) => r.run.id === runId);
    const full = s?.steps[step.index];
    if (!full) return null;
    const uri = svgDataUri(screenshotSvg(full._frame, step.index));
    this.screenshotCache.set(key, uri);
    return uri;
  }

  subscribeRunEvents(runId: string, handlers: RunEventHandlers) {
    let active = true;
    handlers.onStateChange?.("connecting");
    const s = this.runs.find((r) => r.run.id === runId);
    setTimeout(() => {
      if (!active) return;
      if (!s || isTerminal(s.run.status)) {
        if (s) handlers.onEvent({ type: "status", run_id: runId, timestamp: this.iso(), status: s.run.status });
        handlers.onStateChange?.("closed");
        return;
      }
      handlers.onStateChange?.("open");
      let set = this.listeners.get(runId);
      if (!set) this.listeners.set(runId, (set = new Set()));
      set.add(handlers);
    }, Math.min(this.latency, 50));
    return () => {
      active = false;
      this.listeners.get(runId)?.delete(handlers);
    };
  }

  dispose() {
    for (const s of this.runs) clearTimeout(s.timer);
    this.listeners.clear();
  }
}

function clip(s: string, n: number) {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

export function createMockApi(opts?: MockOptions): SideApi & { backend: MockBackend } {
  const backend = new MockBackend(opts);
  return {
    mode: "mock",
    baseUrl: "mock://side",
    backend,
    health: async () => ({ status: "ok", version: "mock" }),
    listTasks: (p) => backend.listTasks(p),
    listAgents: () => backend.listAgents(),
    listRuns: (p) => backend.listRuns(p),
    createRun: (b) => backend.createRun(b),
    getRun: (id) => backend.getRun(id),
    deleteRun: (id) => backend.deleteRun(id),
    cancelRun: (id) => backend.cancelRun(id),
    listSteps: (id) => backend.listSteps(id),
    getStep: (id, i) => backend.getStep(id, i),
    listChat: (id) => backend.listChat(id),
    sendChat: (id, m) => backend.sendChat(id, m),
    screenshotSrc: (id, step) => backend.screenshotSrc(id, step),
    subscribeRunEvents: (id, h) => backend.subscribeRunEvents(id, h),
  };
}
