import type { components, paths } from './schema';

type Schemas = components['schemas'];

export type RunStatus = Schemas['RunStatus'];
export type Task = Schemas['Task'];
export type AgentInfo = Schemas['AgentInfo'];
export type AgentType = AgentInfo['type'];
export type AgentConfig = Schemas['AgentConfig'];
export type RunCreate = Schemas['RunCreate'];
export type Run = Schemas['Run'];
export type Step = Schemas['Step'];
export type StepDetail = Schemas['StepDetail'];
export type ChatMessage = Schemas['ChatMessage'];
export type RunEvent = Schemas['RunEvent'];
export type RunEventType = RunEvent['type'];
export type DeviceRegistration = Schemas['DeviceRegistration'];

export type RunPage = paths['/runs']['get']['responses']['200']['content']['application/json'];
export type ListRunsQuery = NonNullable<paths['/runs']['get']['parameters']['query']>;
export type ListTasksQuery = NonNullable<paths['/tasks']['get']['parameters']['query']>;
export type Health = paths['/health']['get']['responses']['200']['content']['application/json'];

export const RUN_STATUSES: readonly RunStatus[] = ['queued', 'running', 'succeeded', 'failed', 'cancelled'];
export const TERMINAL_STATUSES: readonly RunStatus[] = ['succeeded', 'failed', 'cancelled'];
export const RUN_EVENT_TYPES: readonly RunEventType[] = ['status', 'step', 'chat', 'log'];

export function isTerminal(status: RunStatus): boolean {
  return TERMINAL_STATUSES.includes(status);
}
