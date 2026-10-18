"use client";

import Link from "next/link";
import { Activity, ArrowRight, CheckCircle2, Footprints, Plus, Timer } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { RunList } from "@/components/runs/run-list";
import { STATUS_STYLES, StatusBadge } from "@/components/status-badge";
import { ErrorState, EmptyState } from "@/components/states";
import { LiveDuration } from "@/components/time";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useRuns, useTaskIndex } from "@/hooks/use-api";
import { RUN_STATUSES, type Run, type RunStatus } from "@/lib/api";
import { STATUS_LABEL, formatDuration, runDurationMs, taskShortName } from "@/lib/format";
import { cn } from "@/lib/utils";

function computeStats(runs: Run[]) {
  const counts = Object.fromEntries(RUN_STATUSES.map((s) => [s, 0])) as Record<RunStatus, number>;
  for (const r of runs) counts[r.status]++;
  const decided = counts.succeeded + counts.failed;
  const finished = runs.filter((r) => r.finished_at && r.started_at);
  const avgSteps = runs.length ? runs.reduce((a, r) => a + r.n_steps, 0) / runs.length : 0;
  const avgDuration = finished.length
    ? finished.reduce((a, r) => a + (runDurationMs(r) ?? 0), 0) / finished.length
    : null;
  return {
    counts,
    total: runs.length,
    active: counts.running + counts.queued,
    successRate: decided ? counts.succeeded / decided : null,
    avgSteps,
    avgDuration,
  };
}

function dailyBuckets(runs: Run[], days = 7) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Array.from({ length: days }, (_, i) => {
    const start = new Date(today);
    start.setDate(today.getDate() - (days - 1 - i));
    const end = new Date(start);
    end.setDate(start.getDate() + 1);
    const inDay = runs.filter((r) => {
      const t = Date.parse(r.created_at);
      return t >= start.getTime() && t < end.getTime();
    });
    const counts = Object.fromEntries(RUN_STATUSES.map((s) => [s, 0])) as Record<RunStatus, number>;
    for (const r of inDay) counts[r.status]++;
    return { label: start.toLocaleDateString(undefined, { weekday: "short" }), total: inDay.length, counts };
  });
}

function StatCard({
  title,
  value,
  hint,
  icon: Icon,
  loading,
}: {
  title: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon: React.ComponentType<{ className?: string }>;
  loading?: boolean;
}) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardDescription>{title}</CardDescription>
        <CardAction>
          <Icon className="size-4 text-muted-foreground" />
        </CardAction>
        <CardTitle className="text-2xl font-semibold tabular-nums sm:text-3xl">
          {loading ? <Skeleton className="h-8 w-16" /> : value}
        </CardTitle>
      </CardHeader>
      {hint && <CardContent className="text-xs text-muted-foreground">{hint}</CardContent>}
    </Card>
  );
}

export default function DashboardPage() {
  const { data, error, isLoading, mutate } = useRuns({ limit: 200 }, { refreshInterval: 3000 });
  const tasks = useTaskIndex();
  const runs = data?.items ?? [];
  const stats = computeStats(runs);
  const buckets = dailyBuckets(runs);
  const maxBucket = Math.max(1, ...buckets.map((b) => b.total));
  const active = runs.filter((r) => r.status === "running" || r.status === "queued");

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="BrowserGym episodes launched from Side."
        actions={
          <Button asChild>
            <Link href="/runs/new">
              <Plus /> New run
            </Link>
          </Button>
        }
      />
      {error && <ErrorState error={error} onRetry={() => mutate()} />}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          title="Total runs"
          value={stats.total}
          icon={Activity}
          loading={isLoading}
          hint={data?.next_cursor ? "Latest 200 runs" : "All runs"}
        />
        <StatCard
          title="Active now"
          value={
            <span className="inline-flex items-center gap-2">
              {stats.active}
              {stats.active > 0 && <span className="size-2 animate-pulse rounded-full bg-sky-500" />}
            </span>
          }
          icon={Timer}
          loading={isLoading}
          hint={`${stats.counts.running} running · ${stats.counts.queued} queued`}
        />
        <StatCard
          title="Success rate"
          value={stats.successRate === null ? "—" : `${Math.round(stats.successRate * 100)}%`}
          icon={CheckCircle2}
          loading={isLoading}
          hint={`${stats.counts.succeeded} succeeded · ${stats.counts.failed} failed`}
        />
        <StatCard
          title="Avg. steps"
          value={stats.avgSteps.toFixed(1)}
          icon={Footprints}
          loading={isLoading}
          hint={`Avg. duration ${formatDuration(stats.avgDuration)}`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Runs by status</CardTitle>
            <CardDescription>Distribution and daily volume over the last 7 days</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div>
              <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted" role="img" aria-label="Runs by status">
                {RUN_STATUSES.map((s) =>
                  stats.counts[s] ? (
                    <div
                      key={s}
                      className={cn("h-full transition-all", STATUS_STYLES[s].bar)}
                      style={{ width: `${(stats.counts[s] / Math.max(1, stats.total)) * 100}%` }}
                      title={`${STATUS_LABEL[s]}: ${stats.counts[s]}`}
                    />
                  ) : null,
                )}
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
                {RUN_STATUSES.map((s) => (
                  <Link
                    key={s}
                    href={`/runs?status=${s}`}
                    className="flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm hover:bg-muted"
                  >
                    <span className="flex items-center gap-2">
                      <span className={cn("size-2 rounded-full", STATUS_STYLES[s].dot)} />
                      {STATUS_LABEL[s]}
                    </span>
                    <span className="font-mono tabular-nums">{stats.counts[s]}</span>
                  </Link>
                ))}
              </div>
            </div>
            <div className="flex h-40 items-end gap-2 sm:gap-4" role="img" aria-label="Daily runs">
              {buckets.map((b, i) => (
                <div key={i} className="flex h-full flex-1 flex-col items-center justify-end gap-2">
                  <div className="flex w-full max-w-12 flex-col-reverse overflow-hidden rounded-md bg-muted/50" style={{ height: `${(b.total / maxBucket) * 100}%`, minHeight: 4 }}>
                    {RUN_STATUSES.map((s) =>
                      b.counts[s] ? (
                        <div key={s} className={STATUS_STYLES[s].bar} style={{ height: `${(b.counts[s] / Math.max(1, b.total)) * 100}%` }} />
                      ) : null,
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">{b.label}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Live now</CardTitle>
            <CardDescription>Queued and running episodes</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {isLoading && <Skeleton className="h-16 w-full" />}
            {!isLoading && active.length === 0 && (
              <EmptyState title="Nothing running" description="Launch a run to watch it live." className="p-6" />
            )}
            {active.slice(0, 5).map((run) => (
              <Link
                key={run.id}
                href={`/runs/${run.id}`}
                className="block rounded-lg border p-3 transition-colors hover:bg-muted"
                data-testid="active-run"
              >
                <div className="flex items-center justify-between gap-2">
                  <StatusBadge status={run.status} />
                  <LiveDuration start={run.started_at} end={run.finished_at} className="font-mono text-xs text-muted-foreground" />
                </div>
                <p className="mt-2 truncate text-sm font-medium">{tasks.get(run.task_id)?.title ?? taskShortName(run.task_id)}</p>
                <div className="mt-2 flex items-center gap-2">
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-sky-500 transition-all"
                      style={{ width: `${run.max_steps ? (run.n_steps / run.max_steps) * 100 : 0}%` }}
                    />
                  </div>
                  <span className="font-mono text-xs tabular-nums text-muted-foreground">
                    {run.n_steps}/{run.max_steps ?? "?"}
                  </span>
                </div>
              </Link>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent runs</CardTitle>
          <CardAction>
            <Button asChild variant="ghost" size="sm">
              <Link href="/runs">
                View all <ArrowRight />
              </Link>
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent>
          {!isLoading && runs.length === 0 ? (
            <EmptyState
              title="No runs yet"
              description="Launch your first BrowserGym episode."
              action={
                <Button asChild size="sm">
                  <Link href="/runs/new">New run</Link>
                </Button>
              }
            />
          ) : (
            <RunList runs={data ? runs.slice(0, 8) : undefined} tasks={tasks} loading={isLoading} compact />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
