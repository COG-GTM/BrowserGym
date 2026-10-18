import { useCallback, useRef, type KeyboardEvent, type PointerEvent } from "react";
import { tryParseAction } from "../parsers/action";
import type { Step } from "../types";
import { clamp, cx } from "../utils";
import { ActionBadge } from "./ActionBadge";

export interface StepTimelineProps {
  steps: Step[];
  currentIndex: number;
  onChange: (index: number) => void;
  /** Steps moved by PageUp/PageDown. */
  pageSize?: number;
  /** Hide the action label under the track. */
  hideLabel?: boolean;
  className?: string;
}

function stepFailed(steps: Step[], i: number): boolean {
  // BrowserGym reports an action's error in the *next* observation.
  return Boolean(steps[i + 1]?.last_action_error);
}

export function StepTimeline({ steps, currentIndex, onChange, pageSize = 5, hideLabel, className }: StepTimelineProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);
  const last = Math.max(0, steps.length - 1);
  const current = clamp(currentIndex, 0, last);
  const step = steps[current];

  const go = useCallback(
    (i: number) => {
      const next = clamp(i, 0, last);
      if (next !== current) onChange(next);
    },
    [current, last, onChange],
  );

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const map: Record<string, number> = {
      ArrowLeft: current - 1,
      ArrowDown: current - 1,
      ArrowRight: current + 1,
      ArrowUp: current + 1,
      PageDown: current - pageSize,
      PageUp: current + pageSize,
      Home: 0,
      End: last,
    };
    if (e.key in map) {
      e.preventDefault();
      go(map[e.key]!);
    }
  };

  const indexFromPointer = (clientX: number): number => {
    const el = trackRef.current;
    if (!el || steps.length <= 1 || !Number.isFinite(clientX)) return current;
    const rect = el.getBoundingClientRect();
    const ratio = rect.width ? (clientX - rect.left) / rect.width : 0;
    return Math.round(clamp(ratio, 0, 1) * last);
  };

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    draggingRef.current = true;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    e.currentTarget.focus();
    go(indexFromPointer(e.clientX));
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (draggingRef.current) go(indexFromPointer(e.clientX));
  };
  const onPointerUp = (e: PointerEvent<HTMLDivElement>) => {
    draggingRef.current = false;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
  };

  const pct = (i: number) => (last === 0 ? 0 : (i / last) * 100);
  const parsed = tryParseAction(step?.action);

  return (
    <div className={cx("stv-timeline", className)}>
      <div
        ref={trackRef}
        className="stv-timeline__track"
        role="slider"
        tabIndex={0}
        aria-label="Step"
        aria-valuemin={0}
        aria-valuemax={last}
        aria-valuenow={current}
        aria-valuetext={`Step ${current + 1} of ${steps.length}${parsed ? `: ${parsed.name}` : ""}`}
        aria-disabled={steps.length === 0 || undefined}
        onKeyDown={onKeyDown}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <div className="stv-timeline__rail" />
        <div className="stv-timeline__fill" style={{ width: `${pct(current)}%` }} />
        {steps.map((s, i) => {
          const cat = tryParseAction(s.action)?.category ?? (s.action ? "invalid" : "none");
          return (
            <span
              key={s.index}
              className={cx(
                "stv-timeline__marker",
                i === current && "stv-timeline__marker--current",
                i < current && "stv-timeline__marker--past",
                stepFailed(steps, i) && "stv-timeline__marker--error",
                (s.terminated || s.truncated) && "stv-timeline__marker--terminal",
              )}
              data-category={cat}
              data-testid={`step-marker-${i}`}
              style={{ left: `${pct(i)}%` }}
              title={`Step ${i + 1}: ${s.action ?? "—"}`}
            />
          );
        })}
      </div>
      {!hideLabel && (
        <div className="stv-timeline__label" aria-live="polite">
          <span className="stv-timeline__count">
            Step <strong>{steps.length ? current + 1 : 0}</strong> / {steps.length}
          </span>
          {step && <ActionBadge action={step.action} error={stepFailed(steps, current)} compact />}
        </div>
      )}
    </div>
  );
}
