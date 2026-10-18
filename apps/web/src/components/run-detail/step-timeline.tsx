"use client";

import { useEffect, useRef } from "react";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { ActionCode } from "@/components/run-detail/action-code";
import type { Step } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";

function StepDot({ step }: { step: Step }) {
  if (step.last_action_error) return <AlertCircle className="size-4 text-rose-500" />;
  if (step.terminated && step.reward > 0) return <CheckCircle2 className="size-4 text-emerald-500" />;
  return <span className="grid size-4 place-items-center font-mono text-[10px] text-muted-foreground">{step.index}</span>;
}

export function StepTimeline({
  steps,
  selected,
  onSelect,
  live,
}: {
  steps: Step[];
  selected: number | null;
  onSelect: (index: number) => void;
  live: boolean;
}) {
  const activeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [selected, steps.length]);

  return (
    <>
      {/* vertical list (lg+) */}
      <ol className="hidden space-y-1 lg:block" aria-label="Steps">
        {steps.map((s) => (
          <li key={s.index}>
            <button
              ref={s.index === selected ? activeRef : undefined}
              onClick={() => onSelect(s.index)}
              aria-current={s.index === selected}
              data-testid="timeline-step"
              className={cn(
                "group flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left transition-colors hover:bg-muted",
                s.index === selected && "bg-primary/10 hover:bg-primary/15",
              )}
            >
              <span className="mt-0.5">
                <StepDot step={s} />
              </span>
              <span className="min-w-0 flex-1">
                <ActionCode action={s.action} className="block truncate text-xs" />
                {s.thought && <span className="mt-0.5 line-clamp-2 block text-xs text-muted-foreground">{s.thought}</span>}
              </span>
              <span className="shrink-0 font-mono text-[10px] text-muted-foreground">{formatDuration(s.elapsed_ms)}</span>
            </button>
          </li>
        ))}
        {live && (
          <li className="flex items-center gap-2 px-2 py-2 text-xs text-muted-foreground">
            <Loader2 className="size-4 animate-spin text-sky-500" /> Waiting for next step…
          </li>
        )}
      </ol>
      {/* horizontal scrubber (< lg) */}
      <div className="no-scrollbar -mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1 lg:hidden" aria-label="Steps">
        {steps.map((s) => (
          <button
            key={s.index}
            ref={s.index === selected ? activeRef : undefined}
            onClick={() => onSelect(s.index)}
            aria-current={s.index === selected}
            className={cn(
              "flex h-9 shrink-0 items-center gap-1.5 rounded-lg border px-2.5 font-mono text-xs",
              s.index === selected ? "border-primary bg-primary text-primary-foreground" : "bg-card",
              s.last_action_error && s.index !== selected && "border-rose-500/50 text-rose-600",
            )}
          >
            {s.index}
            <span className="max-w-24 truncate opacity-80">{s.action?.split("(")[0]}</span>
          </button>
        ))}
        {live && (
          <span className="flex h-9 shrink-0 items-center rounded-lg border border-dashed px-3">
            <Loader2 className="size-3.5 animate-spin text-sky-500" />
          </span>
        )}
      </div>
    </>
  );
}
