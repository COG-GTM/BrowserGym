"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Bot, ChevronRight, Footprints } from "lucide-react";
import { StatusBadge } from "@/components/status-badge";
import { LiveDuration, RelativeTime } from "@/components/time";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Run, Task } from "@/lib/api";
import { agentLabel, taskShortName } from "@/lib/format";
import { cn } from "@/lib/utils";

function Reward({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <span className="text-muted-foreground">—</span>;
  return (
    <span className={cn("font-mono tabular-nums", value > 0 ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground")}>
      {value.toFixed(2)}
    </span>
  );
}

function StepsCell({ run }: { run: Run }) {
  const pct = run.max_steps ? Math.min(100, (run.n_steps / run.max_steps) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-xs tabular-nums">
        {run.n_steps}
        {run.max_steps ? <span className="text-muted-foreground">/{run.max_steps}</span> : null}
      </span>
      {run.max_steps ? (
        <span className="hidden h-1 w-12 overflow-hidden rounded-full bg-muted lg:block">
          <span className="block h-full rounded-full bg-primary/70" style={{ width: `${pct}%` }} />
        </span>
      ) : null}
    </div>
  );
}

export function RunList({
  runs,
  tasks,
  loading,
  compact = false,
}: {
  runs: Run[] | undefined;
  tasks: Map<string, Task>;
  loading?: boolean;
  compact?: boolean;
}) {
  const router = useRouter();
  if (loading && !runs) {
    return (
      <div className="space-y-2">
        {Array.from({ length: compact ? 5 : 8 }, (_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }
  const items = runs ?? [];
  return (
    <>
      {/* desktop */}
      <div className="hidden overflow-hidden rounded-xl border md:block">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40 hover:bg-muted/40">
              <TableHead className="w-[120px]">Status</TableHead>
              <TableHead>Task</TableHead>
              <TableHead>Agent</TableHead>
              <TableHead>Steps</TableHead>
              {!compact && <TableHead>Reward</TableHead>}
              {!compact && <TableHead>Duration</TableHead>}
              <TableHead className="text-right">Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((run) => (
              <TableRow
                key={run.id}
                className="cursor-pointer"
                onClick={() => router.push(`/runs/${run.id}`)}
                data-testid="run-row"
              >
                <TableCell>
                  <StatusBadge status={run.status} />
                </TableCell>
                <TableCell className="max-w-[340px]">
                  <Link href={`/runs/${run.id}`} className="block truncate font-medium hover:underline" onClick={(e) => e.stopPropagation()}>
                    {tasks.get(run.task_id)?.title ?? taskShortName(run.task_id)}
                  </Link>
                  <span className="block truncate font-mono text-xs text-muted-foreground">
                    {run.id} · {taskShortName(run.task_id)}
                  </span>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">{agentLabel(run.agent)}</TableCell>
                <TableCell>
                  <StepsCell run={run} />
                </TableCell>
                {!compact && (
                  <TableCell>
                    <Reward value={run.reward} />
                  </TableCell>
                )}
                {!compact && (
                  <TableCell className="font-mono text-xs tabular-nums text-muted-foreground">
                    <LiveDuration start={run.started_at} end={run.finished_at} />
                  </TableCell>
                )}
                <TableCell className="text-right text-sm text-muted-foreground">
                  <RelativeTime iso={run.created_at} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {/* mobile */}
      <ul className="space-y-2 md:hidden">
        {items.map((run) => (
          <li key={run.id}>
            <Link
              href={`/runs/${run.id}`}
              data-testid="run-card"
              className="flex items-center gap-3 rounded-xl border bg-card p-3 transition-colors active:bg-muted"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <StatusBadge status={run.status} />
                  <RelativeTime iso={run.created_at} className="text-xs text-muted-foreground" />
                </div>
                <p className="mt-2 truncate font-medium">{tasks.get(run.task_id)?.title ?? taskShortName(run.task_id)}</p>
                <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    <Bot className="size-3" /> {agentLabel(run.agent)}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Footprints className="size-3" /> {run.n_steps}
                    {run.max_steps ? `/${run.max_steps}` : ""}
                  </span>
                </div>
              </div>
              <ChevronRight className="size-4 text-muted-foreground" />
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
