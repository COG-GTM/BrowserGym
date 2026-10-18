import type { components, operations } from "./schema";

type Schemas = components["schemas"];

export type RunStatus = Schemas["RunStatus"];
export type Task = Schemas["Task"];
export type AgentInfo = Schemas["AgentInfo"];
export type AgentConfig = Schemas["AgentConfig"];
export type AgentType = AgentConfig["type"];
export type RunCreate = Schemas["RunCreate"];
export type Run = Schemas["Run"];
export type Step = Schemas["Step"];
export type StepDetail = Schemas["StepDetail"];
export type ChatMessage = Schemas["ChatMessage"];
export type ChatRole = ChatMessage["role"];
export type RunEvent = Schemas["RunEvent"];
export type RunEventType = RunEvent["type"];

type JsonBody<R> = R extends { content: { "application/json": infer B } } ? B : never;

export type Health = JsonBody<operations["getHealth"]["responses"][200]>;
export type RunList = JsonBody<operations["listRuns"]["responses"][200]>;
export type ListRunsParams = NonNullable<operations["listRuns"]["parameters"]["query"]>;
export type ListTasksParams = NonNullable<operations["listTasks"]["parameters"]["query"]>;
export type SendChatBody = NonNullable<
  operations["sendChat"]["requestBody"]
>["content"]["application/json"];
export type ApiErrorBody = JsonBody<components["responses"]["Error"]>;

export const RUN_STATUSES: readonly RunStatus[] = [
  "queued",
  "running",
  "succeeded",
  "failed",
  "cancelled",
] as const;

export const RUN_EVENT_TYPES: readonly RunEventType[] = ["status", "step", "chat", "log"] as const;

export const TERMINAL_STATUSES: readonly RunStatus[] = ["succeeded", "failed", "cancelled"];

export function isTerminal(status: RunStatus): boolean {
  return TERMINAL_STATUSES.includes(status);
}

export const OPENENDED_TASK_ID = "browsergym/openended";
