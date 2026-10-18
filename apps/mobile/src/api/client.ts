import createFetchClient from 'openapi-fetch';

import type { paths } from './schema';
import { openRunEventStream } from './sse';
import type {
  AgentInfo,
  ChatMessage,
  DeviceRegistration,
  Health,
  ListRunsQuery,
  ListTasksQuery,
  Run,
  RunCreate,
  RunEvent,
  RunPage,
  Step,
  StepDetail,
  Task,
} from './types';

export type Unsubscribe = () => void;

/** A bundled asset (number from require) or a remote image. */
export type ScreenshotSource = number | { uri: string };

export interface RunEventHandlers {
  onEvent: (event: RunEvent) => void;
  onError?: (error: Error) => void;
  onClose?: () => void;
}

/** Everything the app needs from the Side API (contracts/openapi.yaml). Implemented over HTTP and by the mock. */
export interface SideApi {
  readonly mode: 'http' | 'mock';
  getHealth(): Promise<Health>;
  listTasks(query?: ListTasksQuery): Promise<Task[]>;
  listAgents(): Promise<AgentInfo[]>;
  listRuns(query?: ListRunsQuery): Promise<RunPage>;
  createRun(body: RunCreate): Promise<Run>;
  getRun(runId: string): Promise<Run>;
  deleteRun(runId: string): Promise<void>;
  cancelRun(runId: string): Promise<Run>;
  listSteps(runId: string): Promise<Step[]>;
  getStep(runId: string, index: number): Promise<StepDetail>;
  listChat(runId: string): Promise<ChatMessage[]>;
  sendChat(runId: string, message: string): Promise<ChatMessage>;
  registerDevice(body: DeviceRegistration): Promise<void>;
  /** Image source for a step screenshot, or null if the step has none. */
  screenshotSource(runId: string, step: Step): ScreenshotSource | null;
  /** Subscribe to the run's SSE stream. The stream closes after a terminal `status` event. */
  subscribeRunEvents(runId: string, handlers: RunEventHandlers): Unsubscribe;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

function detailOf(error: unknown): string | undefined {
  if (error && typeof error === 'object' && 'detail' in error) {
    const detail = (error as { detail: unknown }).detail;
    return typeof detail === 'string' ? detail : JSON.stringify(detail);
  }
  return undefined;
}

function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (!result.response.ok) {
    throw new ApiError(
      detailOf(result.error) ?? `HTTP ${result.response.status}`,
      result.response.status,
    );
  }
  return result.data as T;
}

export function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.trim().replace(/\/+$/, '');
}

export function createHttpApi(baseUrl: string, fetchImpl?: typeof fetch): SideApi {
  const base = normalizeBaseUrl(baseUrl);
  // Resolve fetch lazily so tests (and polyfills) can swap the global.
  const client = createFetchClient<paths>({
    baseUrl: base,
    fetch: (req) => (fetchImpl ?? globalThis.fetch)(req),
  });
  const runId = (id: string) => ({ params: { path: { run_id: id } } });
  const stepPath = (id: string, index: number) => ({ params: { path: { run_id: id, index } } });

  return {
    mode: 'http',
    async getHealth() {
      return unwrap(await client.GET('/health'));
    },
    async listTasks(query) {
      return unwrap(await client.GET('/tasks', { params: { query } }));
    },
    async listAgents() {
      return unwrap(await client.GET('/agents'));
    },
    async listRuns(query) {
      return unwrap(await client.GET('/runs', { params: { query } }));
    },
    async createRun(body) {
      return unwrap(await client.POST('/runs', { body }));
    },
    async getRun(id) {
      return unwrap(await client.GET('/runs/{run_id}', runId(id)));
    },
    async deleteRun(id) {
      unwrap(await client.DELETE('/runs/{run_id}', runId(id)));
    },
    async cancelRun(id) {
      return unwrap(await client.POST('/runs/{run_id}/cancel', runId(id)));
    },
    async listSteps(id) {
      return unwrap(await client.GET('/runs/{run_id}/steps', runId(id)));
    },
    async getStep(id, index) {
      return unwrap(await client.GET('/runs/{run_id}/steps/{index}', stepPath(id, index)));
    },
    async listChat(id) {
      return unwrap(await client.GET('/runs/{run_id}/chat', runId(id)));
    },
    async sendChat(id, message) {
      return unwrap(await client.POST('/runs/{run_id}/chat', { ...runId(id), body: { message } }));
    },
    async registerDevice(body) {
      unwrap(await client.POST('/devices', { body }));
    },
    screenshotSource(id, step) {
      if (!step.screenshot_url) return null;
      return { uri: resolveUrl(base, step.screenshot_url) };
    },
    subscribeRunEvents(id, handlers) {
      return openRunEventStream(`${base}/runs/${encodeURIComponent(id)}/events`, handlers);
    },
  };
}

/** Resolve a contract "relative URL" (e.g. `/runs/r1/steps/0/screenshot`) against the API base. */
export function resolveUrl(base: string, url: string): string {
  if (/^https?:\/\//i.test(url)) return url;
  if (url.startsWith('/api/')) {
    const origin = base.match(/^(https?:\/\/[^/]+)/i)?.[1] ?? base;
    return `${origin}${url}`;
  }
  return `${base}${url.startsWith('/') ? '' : '/'}${url}`;
}
