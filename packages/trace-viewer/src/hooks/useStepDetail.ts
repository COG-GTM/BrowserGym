import { useEffect, useRef, useState } from "react";
import type { Step, StepDetail } from "../types";

export type StepDetailLoader = (index: number) => StepDetail | undefined | Promise<StepDetail | undefined>;

type Settled = { entries: Map<number, StepDetail>; step: Step | StepDetail; error: unknown };

/**
 * Returns the StepDetail for `step`, loading it lazily via `load`. Loaded details are cached per index
 * (reset when `scope`, e.g. the run id, changes). An empty or failed load is not cached: it is retried
 * when the step is revisited or its `Step` object is replaced (e.g. a live run publishes an update).
 */
export function useStepDetail(step: Step | StepDetail | undefined, load?: StepDetailLoader, scope?: string) {
  const cache = useRef({ scope, entries: new Map<number, StepDetail>() });
  if (cache.current.scope !== scope) cache.current = { scope, entries: new Map() };
  const entries = cache.current.entries;
  const [, force] = useState(0);
  const [settled, setSettled] = useState<Settled | null>(null);
  const index = step?.index;

  useEffect(() => {
    if (!load || !step || index === undefined || entries.has(index)) return;
    let cancelled = false;
    Promise.resolve(load(index))
      .then((d) => {
        if (cancelled) return;
        if (d) {
          entries.set(index, d);
          force((n) => n + 1);
        } else setSettled({ entries, step, error: null });
      })
      .catch((e) => !cancelled && setSettled({ entries, step, error: e }));
    return () => {
      cancelled = true;
    };
  }, [step, index, load, entries]);

  const current = settled && settled.entries === entries && settled.step === step ? settled : null;
  const loaded = index !== undefined ? entries.get(index) : undefined;
  const detail: StepDetail | undefined = index !== undefined ? loaded ?? step : undefined;
  return {
    detail,
    loading: Boolean(load && index !== undefined && !loaded && !current),
    error: current?.error ?? null,
  };
}
