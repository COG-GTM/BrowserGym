import type { operations, paths } from "./schema";
import { openRunEventStream, type RunEventHandlers, type Unsubscribe } from "./sse";
import type {
  AgentInfo,
  ApiErrorBody,
  ChatMessage,
  Health,
  ListRunsParams,
  ListTasksParams,
  Run,
  RunCreate,
  RunList,
  Step,
  StepDetail,
  Task,
} from "./types";

export interface SideApi {
  readonly mode: "mock" | "http";
  readonly baseUrl: string;
  health(): Promise<Health>;
  listTasks(params?: ListTasksParams): Promise<Task[]>;
  listAgents(): Promise<AgentInfo[]>;
  listRuns(params?: ListRunsParams): Promise<RunList>;
  createRun(body: RunCreate): Promise<Run>;
  getRun(runId: string): Promise<Run>;
  deleteRun(runId: string): Promise<void>;
  cancelRun(runId: string): Promise<Run>;
  listSteps(runId: string): Promise<Step[]>;
  getStep(runId: string, index: number): Promise<StepDetail>;
  listChat(runId: string): Promise<ChatMessage[]>;
  sendChat(runId: string, message: string): Promise<ChatMessage>;
  /** Resolve an image src for a step's screenshot, or null if it has none. */
  screenshotSrc(runId: string, step: Pick<Step, "index" | "screenshot_url">): string | null;
  subscribeRunEvents(runId: string, handlers: RunEventHandlers): Unsubscribe;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`${status}: ${detail}`);
    this.name = "ApiError";
  }
}

type PathParams<P extends string> = P extends `${string}{${infer K}}${infer Rest}`
  ? { [key in K]: string | number } & PathParams<Rest>
  : unknown;

/** Fill a contract path template, e.g. buildPath("/runs/{run_id}", { run_id: "r1" }). */
export function buildPath<P extends keyof paths & string>(template: P, params: PathParams<P>): string {
  const values = params as Record<string, string | number>;
  return template.replace(/\{(\w+)\}/g, (_, key: string) => encodeURIComponent(String(values[key])));
}

function query(params?: Record<string, string | number | undefined | null>): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") search.set(k, String(v));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

type SuccessBody<O extends keyof operations> = operations[O]["responses"] extends infer R
  ? R extends Record<number, unknown>
    ? R[Extract<keyof R, 200 | 201>] extends { content: { "application/json": infer B } }
      ? B
      : void
    : never
  : never;

export function createHttpApi(baseUrl: string, fetchImpl: typeof fetch = (...a) => fetch(...a)): SideApi {
  async function call<O extends keyof operations>(
    _op: O,
    path: string,
    init?: { method?: string; body?: unknown },
  ): Promise<SuccessBody<O>> {
    const res = await fetchImpl(`${baseUrl}${path}`, {
      method: init?.method ?? "GET",
      headers: {
        Accept: "application/json",
        ...(init?.body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
      cache: "no-store",
    });
    if (!res.ok) {
      let detail = res.statusText || "Request failed";
      try {
        const body = (await res.json()) as Partial<ApiErrorBody>;
        if (body && typeof body.detail === "string") detail = body.detail;
        else if (body?.detail) detail = JSON.stringify(body.detail);
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(res.status, detail);
    }
    if (res.status === 204) return undefined as SuccessBody<O>;
    return (await res.json()) as SuccessBody<O>;
  }

  const origin = (() => {
    try {
      return new URL(baseUrl).origin;
    } catch {
      return "";
    }
  })();
  const basePath = baseUrl.slice(origin.length);

  return {
    mode: "http",
    baseUrl,
    health: () => call("getHealth", buildPath("/health", {})),
    listTasks: (params) => call("listTasks", buildPath("/tasks", {}) + query(params)),
    listAgents: () => call("listAgents", buildPath("/agents", {})),
    listRuns: (params) => call("listRuns", buildPath("/runs", {}) + query(params)),
    createRun: (body) => call("createRun", buildPath("/runs", {}), { method: "POST", body }),
    getRun: (runId) => call("getRun", buildPath("/runs/{run_id}", { run_id: runId })),
    deleteRun: (runId) =>
      call("deleteRun", buildPath("/runs/{run_id}", { run_id: runId }), { method: "DELETE" }).then(
        () => undefined,
      ),
    cancelRun: (runId) =>
      call("cancelRun", buildPath("/runs/{run_id}/cancel", { run_id: runId }), { method: "POST" }),
    listSteps: (runId) => call("listSteps", buildPath("/runs/{run_id}/steps", { run_id: runId })),
    getStep: (runId, index) =>
      call("getStep", buildPath("/runs/{run_id}/steps/{index}", { run_id: runId, index })),
    listChat: (runId) => call("listChat", buildPath("/runs/{run_id}/chat", { run_id: runId })),
    sendChat: (runId, message) =>
      call("sendChat", buildPath("/runs/{run_id}/chat", { run_id: runId }), {
        method: "POST",
        body: { message },
      }),
    screenshotSrc(runId, step) {
      const url = step.screenshot_url;
      if (!url) return null;
      if (/^(https?:|data:|blob:)/.test(url)) return url;
      // Accept either a path relative to the API base ("/runs/...") or an origin-relative one ("/api/v1/runs/...").
      if (basePath && url.startsWith(`${basePath}/`)) return `${origin}${url}`;
      return `${baseUrl}${url.startsWith("/") ? "" : "/"}${url}`;
    },
    subscribeRunEvents: (runId, handlers) =>
      openRunEventStream(
        `${baseUrl}${buildPath("/runs/{run_id}/events", { run_id: runId })}`,
        handlers,
      ),
  };
}
