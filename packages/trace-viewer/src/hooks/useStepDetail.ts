import { useEffect, useRef, useState } from "react";
import type { Step, StepDetail } from "../types";

export type StepDetailLoader = (index: number) => StepDetail | undefined | Promise<StepDetail | undefined>;

/** Returns the StepDetail for `step`, loading it lazily via `load` (results are cached per index). */
export function useStepDetail(step: Step | StepDetail | undefined, load?: StepDetailLoader) {
  const cache = useRef(new Map<number, StepDetail>());
  const [, force] = useState(0);
  const [error, setError] = useState<unknown>(null);
  const index = step?.index;

  useEffect(() => {
    if (!load || index === undefined || cache.current.has(index)) return;
    let cancelled = false;
    setError(null);
    Promise.resolve(load(index))
      .then((d) => {
        if (d && !cancelled) {
          cache.current.set(index, d);
          force((n) => n + 1);
        }
      })
      .catch((e) => !cancelled && setError(e));
    return () => {
      cancelled = true;
    };
  }, [index, load]);

  const detail: StepDetail | undefined = index !== undefined ? cache.current.get(index) ?? step : undefined;
  return { detail, loading: Boolean(load && index !== undefined && !cache.current.has(index) && !error), error };
}
