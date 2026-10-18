import { CheckCircle2, CircleDashed, Loader2, XCircle, Ban } from "lucide-react";
import type { RunStatus } from "@/lib/api";
import { STATUS_LABEL } from "@/lib/format";
import { cn } from "@/lib/utils";

export const STATUS_STYLES: Record<RunStatus, { badge: string; dot: string; bar: string }> = {
  queued: {
    badge: "bg-zinc-500/10 text-zinc-600 ring-zinc-500/20 dark:text-zinc-300",
    dot: "bg-zinc-400",
    bar: "bg-zinc-400",
  },
  running: {
    badge: "bg-sky-500/10 text-sky-700 ring-sky-500/25 dark:text-sky-300",
    dot: "bg-sky-500",
    bar: "bg-sky-500",
  },
  succeeded: {
    badge: "bg-emerald-500/10 text-emerald-700 ring-emerald-500/25 dark:text-emerald-300",
    dot: "bg-emerald-500",
    bar: "bg-emerald-500",
  },
  failed: {
    badge: "bg-rose-500/10 text-rose-700 ring-rose-500/25 dark:text-rose-300",
    dot: "bg-rose-500",
    bar: "bg-rose-500",
  },
  cancelled: {
    badge: "bg-amber-500/10 text-amber-700 ring-amber-500/25 dark:text-amber-300",
    dot: "bg-amber-500",
    bar: "bg-amber-500",
  },
};

const ICONS = {
  queued: CircleDashed,
  running: Loader2,
  succeeded: CheckCircle2,
  failed: XCircle,
  cancelled: Ban,
} as const;

export function StatusIcon({ status, className }: { status: RunStatus; className?: string }) {
  const Icon = ICONS[status];
  return <Icon className={cn("size-3.5", status === "running" && "animate-spin", className)} />;
}

export function StatusBadge({ status, className }: { status: RunStatus; className?: string }) {
  return (
    <span
      data-status={status}
      className={cn(
        "inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium ring-1 ring-inset whitespace-nowrap",
        STATUS_STYLES[status].badge,
        className,
      )}
    >
      <StatusIcon status={status} />
      {STATUS_LABEL[status]}
    </span>
  );
}
