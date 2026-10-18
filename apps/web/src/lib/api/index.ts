import { createHttpApi, type SideApi } from "./client";
import { API_BASE_URL, IS_MOCK } from "./config";
import { createMockApi } from "../mock/backend";

export * from "./types";
export { ApiError, buildPath, type SideApi } from "./client";
export { API_BASE_URL, IS_MOCK } from "./config";
export type { StreamState } from "./sse";

let instance: SideApi | null = null;

export function getApi(): SideApi {
  if (!instance) instance = IS_MOCK ? createMockApi() : createHttpApi(API_BASE_URL);
  return instance;
}
