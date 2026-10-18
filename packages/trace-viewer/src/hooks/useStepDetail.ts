import { useEffect, useRef, useState } from "react";
import type { Step, StepDetail } from "../types";

export type StepDetailLoader = (index: number) => StepDetail | undefined | Promise<StepDetail | undefined>;

/**
 * Returns the StepDetail for `step`, loading it lazily via `load`. Results (including "no detail")
 * are cached per index; the cache is reset when `scope` (e.g. the run id) changes.
 */
export function useStepDetail(step: Step | StepDetail | undefined, load?: StepDetailLoader, scope?: string) {
  const cache = useRef({ scope, entries: new Map<number, StepDetail | null>() });
  if (cache.current.scope !== scope) cache.current = { scope, entries: new Map() };
  const entries = cache.current.entries;
  const [, force] = useState(0);
  const [error, setError] = useState<{ entries: Map<number, StepDetail | null>; index: number; error: unknown } | null>(
    null,
  );
  const index = step?.index;

  useEffect(() => {
    if (!load || index === undefined || entries.has(index)) return;
    let cancelled = false;
    Promise.resolve(load(index))
      .then((d) => {
        if (cancelled) return;
        entries.set(index, d ?? null);
        force((n) => n + 1);
      })
      .catch((e) => !cancelled && setError({ entries, index, error: e }));
    return () => {
      cancelled = true;
    };
  }, [index, load, entries]);

  const currentError = error && error.entries === entries && error.index === index ? error.error : null;
  const loaded = index !== undefined ? entries.get(index) : undefined;
  const detail: StepDetail | undefined = index !== undefined ? loaded ?? step : undefined;
  return {
    detail,
    loading: Boolean(load && index !== undefined && !entries.has(index) && !currentError),
    error: currentError,
  };
}
