import { useEffect, useRef, useState } from "react";
import type { Step, StepDetail } from "../types";

export type StepDetailLoader = (index: number) => StepDetail | undefined | Promise<StepDetail | undefined>;

interface Cache {
  scope: string | undefined;
  entries: Map<number, StepDetail>;
  inflight: Set<number>;
  /** Empty/failed loads, keyed by index, remembered for the `Step` object they were requested for. */
  misses: Map<number, { step: Step | StepDetail; error: unknown }>;
}

const newCache = (scope: string | undefined): Cache => ({
  scope,
  entries: new Map(),
  inflight: new Set(),
  misses: new Map(),
});

/**
 * Returns the StepDetail for `step`, loading it lazily via `load`. Loaded details are cached per index
 * (reset when `scope`, e.g. the run id, changes). At most one request per index is in flight; an empty
 * or failed load is retried when the step is revisited or its `Step` object is replaced (live update).
 */
export function useStepDetail(step: Step | StepDetail | undefined, load?: StepDetailLoader, scope?: string) {
  const ref = useRef<Cache>(newCache(scope));
  if (ref.current.scope !== scope) ref.current = newCache(scope);
  const cache = ref.current;
  const [version, bump] = useState(0);
  const index = step?.index;

  useEffect(() => {
    cache.misses.clear();
  }, [index, cache]);

  useEffect(() => {
    if (!load || !step || index === undefined) return;
    if (cache.entries.has(index) || cache.inflight.has(index) || cache.misses.get(index)?.step === step) return;
    cache.inflight.add(index);
    const settle = (detail: StepDetail | undefined, error: unknown) => {
      cache.inflight.delete(index);
      if (detail) cache.entries.set(index, detail);
      else cache.misses.set(index, { step, error });
      bump((n) => n + 1);
    };
    Promise.resolve()
      .then(() => load(index))
      .then(
        (d) => settle(d, null),
        (e) => settle(undefined, e ?? new Error("Failed to load step detail")),
      );
  }, [step, index, load, cache, version]);

  const loaded = index !== undefined ? cache.entries.get(index) : undefined;
  const miss = index !== undefined ? cache.misses.get(index) : undefined;
  const settledMiss = miss && miss.step === step ? miss : undefined;
  const detail: StepDetail | undefined = index !== undefined ? loaded ?? step : undefined;
  return {
    detail,
    loading: Boolean(load && index !== undefined && !loaded && !settledMiss),
    error: settledMiss?.error ?? null,
  };
}
