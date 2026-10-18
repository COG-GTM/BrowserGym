"use client";

import useSWR, { type SWRConfiguration } from "swr";
import { getApi, type ListRunsParams, type ListTasksParams, type Task } from "@/lib/api";

export function useTasks(params?: ListTasksParams, config?: SWRConfiguration) {
  return useSWR(["tasks", params?.benchmark ?? "", params?.q ?? ""], () => getApi().listTasks(params), {
    keepPreviousData: true,
    ...config,
  });
}

export function useAgents() {
  return useSWR("agents", () => getApi().listAgents());
}

export function useRuns(params?: ListRunsParams, config?: SWRConfiguration) {
  return useSWR(
    ["runs", params?.status ?? "", params?.limit ?? 50, params?.cursor ?? ""],
    () => getApi().listRuns(params),
    { refreshInterval: 4000, keepPreviousData: true, ...config },
  );
}

export function useStepDetail(runId: string, index: number | null) {
  return useSWR(index === null ? null : ["step", runId, index], () => getApi().getStep(runId, index!), {
    revalidateOnFocus: false,
    keepPreviousData: true,
  });
}

/** Map of task id -> Task for labelling runs. */
export function useTaskIndex() {
  const { data } = useTasks(undefined, { revalidateOnFocus: false });
  const map = new Map<string, Task>();
  for (const t of data ?? []) map.set(t.id, t);
  return map;
}
