import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import { useCallback, useEffect, useRef, useState } from 'react';

import { useApi } from './ApiProvider';
import { isTerminal, type ChatMessage, type Run, type RunCreate, type RunEvent, type RunStatus, type Step } from './types';

export const keys = {
  runs: (scope: string, status?: RunStatus) => ['side', scope, 'runs', status ?? 'all'] as const,
  run: (scope: string, id: string) => ['side', scope, 'run', id] as const,
  steps: (scope: string, id: string) => ['side', scope, 'steps', id] as const,
  chat: (scope: string, id: string) => ['side', scope, 'chat', id] as const,
  tasks: (scope: string, q: string, benchmark?: string) => ['side', scope, 'tasks', q, benchmark ?? ''] as const,
  agents: (scope: string) => ['side', scope, 'agents'] as const,
  health: (scope: string) => ['side', scope, 'health'] as const,
};

const PAGE_SIZE = 20;

export function useRuns(status?: RunStatus) {
  const { api, scope } = useApi();
  return useInfiniteQuery({
    queryKey: keys.runs(scope, status),
    queryFn: ({ pageParam }) => api.listRuns({ status, limit: PAGE_SIZE, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    refetchInterval: 10_000,
  });
}

export function useRun(id: string) {
  const { api, scope } = useApi();
  return useQuery({ queryKey: keys.run(scope, id), queryFn: () => api.getRun(id) });
}

export function useSteps(id: string) {
  const { api, scope } = useApi();
  return useQuery({ queryKey: keys.steps(scope, id), queryFn: () => api.listSteps(id) });
}

export function useChat(id: string) {
  const { api, scope } = useApi();
  return useQuery({ queryKey: keys.chat(scope, id), queryFn: () => api.listChat(id) });
}

export function useTasks(q: string, benchmark?: string) {
  const { api, scope } = useApi();
  return useQuery({
    queryKey: keys.tasks(scope, q, benchmark),
    queryFn: () => api.listTasks({ q: q || undefined, benchmark }),
    placeholderData: (prev) => prev,
    staleTime: 60_000,
  });
}

export function useAgents() {
  const { api, scope } = useApi();
  return useQuery({ queryKey: keys.agents(scope), queryFn: () => api.listAgents(), staleTime: 5 * 60_000 });
}

export function useHealth(enabled = true) {
  const { api, scope } = useApi();
  return useQuery({ queryKey: keys.health(scope), queryFn: () => api.getHealth(), enabled, retry: 0 });
}

export function useCreateRun() {
  const { api, scope } = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RunCreate) => api.createRun(body),
    onSuccess: (run) => {
      qc.setQueryData(keys.run(scope, run.id), run);
      qc.invalidateQueries({ queryKey: ['side', scope, 'runs'] });
    },
  });
}

export function useCancelRun(id: string) {
  const { api, scope } = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.cancelRun(id),
    onSuccess: (run) => {
      qc.setQueryData(keys.run(scope, id), run);
      qc.invalidateQueries({ queryKey: ['side', scope, 'runs'] });
    },
  });
}

export function useDeleteRun() {
  const { api, scope } = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteRun(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['side', scope, 'runs'] }),
  });
}

export function useSendChat(id: string) {
  const { api, scope } = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (message: string) => api.sendChat(id, message),
    onSuccess: (msg) => mergeChat(qc, keys.chat(scope, id), msg),
  });
}

function sameMessage(a: ChatMessage, b: ChatMessage) {
  return a.role === b.role && a.message === b.message && a.timestamp === b.timestamp;
}

function mergeChat(qc: QueryClient, key: readonly unknown[], msg: ChatMessage) {
  qc.setQueryData<ChatMessage[]>(key, (prev = []) => (prev.some((m) => sameMessage(m, msg)) ? prev : [...prev, msg]));
}

function mergeStep(prev: Step[] = [], step: Step): Step[] {
  const next = prev.filter((s) => s.index !== step.index);
  next.push(step);
  return next.sort((a, b) => a.index - b.index);
}

/** Apply one RunEvent to the query cache. Exported for tests. */
export function applyRunEvent(qc: QueryClient, scope: string, event: RunEvent) {
  const id = event.run_id;
  if (event.type === 'status' && event.status) {
    const status = event.status;
    qc.setQueryData<Run>(keys.run(scope, id), (prev) =>
      prev
        ? {
            ...prev,
            status,
            started_at: prev.started_at ?? (status === 'running' ? event.timestamp : prev.started_at),
            finished_at: isTerminal(status) ? (prev.finished_at ?? event.timestamp) : prev.finished_at,
          }
        : prev,
    );
  } else if (event.type === 'step' && event.step) {
    const step = event.step;
    qc.setQueryData<Step[]>(keys.steps(scope, id), (prev) => mergeStep(prev, step));
    qc.setQueryData<Run>(keys.run(scope, id), (prev) =>
      prev ? { ...prev, n_steps: Math.max(prev.n_steps, step.index + 1) } : prev,
    );
  } else if (event.type === 'chat' && event.chat) {
    mergeChat(qc, keys.chat(scope, id), event.chat);
  }
}

export type StreamState = 'idle' | 'connecting' | 'live' | 'closed' | 'error';

/**
 * Follow a run's SSE stream while it is active, keeping run/steps/chat queries in sync.
 * Fires a haptic when the run reaches a terminal status.
 */
export function useRunEvents(id: string, status: RunStatus | undefined) {
  const { api, scope } = useApi();
  const qc = useQueryClient();
  const [stream, setStream] = useState<{ key: string; state: StreamState }>({ key: '', state: 'idle' });
  const streamKey = `${scope}:${id}`;
  const state: StreamState = stream.key === streamKey ? stream.state : 'connecting';
  const setState = useCallback((next: StreamState) => setStream({ key: streamKey, state: next }), [streamKey]);
  const [logs, setLogs] = useState<string[]>([]);
  const active = status !== undefined && !isTerminal(status);
  const announced = useRef(false);

  useEffect(() => {
    if (!active) return;
    announced.current = false;
    const unsubscribe = api.subscribeRunEvents(id, {
      onEvent: (event) => {
        setState('live');
        applyRunEvent(qc, scope, event);
        if (event.type === 'log' && event.log) setLogs((prev) => [...prev.slice(-19), event.log!]);
        if (event.type === 'status' && event.status && isTerminal(event.status) && !announced.current) {
          announced.current = true;
          Haptics.notificationAsync(
            event.status === 'succeeded'
              ? Haptics.NotificationFeedbackType.Success
              : event.status === 'failed'
                ? Haptics.NotificationFeedbackType.Error
                : Haptics.NotificationFeedbackType.Warning,
          ).catch(() => undefined);
          qc.invalidateQueries({ queryKey: keys.run(scope, id) });
          qc.invalidateQueries({ queryKey: keys.steps(scope, id) });
          qc.invalidateQueries({ queryKey: keys.chat(scope, id) });
          qc.invalidateQueries({ queryKey: ['side', scope, 'runs'] });
        }
      },
      onError: () => setState('error'),
      onReconnect: () => {
        setState('live');
        qc.invalidateQueries({ queryKey: keys.run(scope, id) });
        qc.invalidateQueries({ queryKey: keys.steps(scope, id) });
        qc.invalidateQueries({ queryKey: keys.chat(scope, id) });
      },
      onClose: () => setState('closed'),
    });
    return unsubscribe;
  }, [api, scope, qc, id, active, setState]);

  return { state: active ? state : 'closed', logs };
}
