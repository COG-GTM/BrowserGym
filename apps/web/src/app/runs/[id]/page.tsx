"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeft,
  Ban,
  ChevronFirst,
  ChevronLast,
  ChevronLeft,
  ChevronRight,
  Copy,
  ExternalLink,
  ImageOff,
  Loader2,
  MessageSquare,
  Radio,
  RotateCcw,
  Trash2,
} from "lucide-react";
import { ActionCode } from "@/components/run-detail/action-code";
import { AxTreeView } from "@/components/run-detail/axtree-view";
import { ChatPanel } from "@/components/run-detail/chat-panel";
import { StepTimeline } from "@/components/run-detail/step-timeline";
import { StatusBadge } from "@/components/status-badge";
import { EmptyState, ErrorState } from "@/components/states";
import { BenchmarkBadge } from "@/components/tasks/benchmark";
import { LiveDuration, RelativeTime } from "@/components/time";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useStepDetail, useTaskIndex } from "@/hooks/use-api";
import { useRunLive } from "@/hooks/use-run-live";
import { getApi, isTerminal, type Step } from "@/lib/api";
import { agentLabel, formatDuration, taskShortName } from "@/lib/format";
import { cn } from "@/lib/utils";

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 truncate text-sm font-medium">{children}</dd>
    </div>
  );
}

function StreamIndicator({ state }: { state: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    open: { label: "Live", cls: "bg-sky-500 animate-pulse" },
    connecting: { label: "Connecting", cls: "bg-zinc-400 animate-pulse" },
    reconnecting: { label: "Reconnecting", cls: "bg-amber-500 animate-pulse" },
    closed: { label: "Ended", cls: "bg-zinc-400" },
    idle: { label: "—", cls: "bg-zinc-300" },
  };
  const s = map[state] ?? map.idle;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground" data-testid="stream-state">
      <span className={cn("size-2 rounded-full", s.cls)} /> {s.label}
    </span>
  );
}

function Screenshot({ runId, step, live }: { runId: string; step: Step | undefined; live: boolean }) {
  const src = step ? getApi().screenshotSrc(runId, step) : null;
  const [failed, setFailed] = useState<string | null>(null);
  return (
    <div className="relative aspect-[16/10] w-full overflow-hidden rounded-lg border bg-muted/40">
      {src && failed !== src ? (
        <img
          key={src}
          src={src}
          alt={step ? `Screenshot of step ${step.index}` : ""}
          className="size-full object-contain"
          onError={() => setFailed(src)}
          data-testid="step-screenshot"
        />
      ) : (
        <div className="grid size-full place-items-center text-sm text-muted-foreground">
          {step ? (
            <span className="flex flex-col items-center gap-2">
              <ImageOff className="size-6" /> No screenshot for this step
            </span>
          ) : live ? (
            <span className="flex flex-col items-center gap-2">
              <Loader2 className="size-6 animate-spin" /> Waiting for the first step…
            </span>
          ) : (
            "No steps recorded"
          )}
        </div>
      )}
      {live && (
        <span className="absolute top-2 left-2 inline-flex items-center gap-1 rounded-full bg-rose-600 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-white uppercase shadow">
          <Radio className="size-3" /> Live
        </span>
      )}
    </div>
  );
}

export default function RunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const live = useRunLive(id);
  const tasks = useTaskIndex();
  const { run, steps, chat, logs, stream } = live;
  const [selected, setSelected] = useState<number | null>(null); // null = follow latest
  const [cancelling, setCancelling] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const latest = steps.length ? steps[steps.length - 1].index : null;
  const current = selected ?? latest;
  const step = steps.find((s) => s.index === current);
  const detail = useStepDetail(id, current);
  const following = selected === null;
  const active = !!run && !isTerminal(run.status);

  const go = useCallback(
    (index: number | null) => {
      if (index === null || latest === null) return setSelected(null);
      const clamped = Math.max(0, Math.min(latest, index));
      setSelected(active && clamped === latest ? null : clamped);
    },
    [latest, active],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input, textarea, [contenteditable]")) return;
      if (current === null) return;
      if (e.key === "ArrowLeft") go(current - 1);
      if (e.key === "ArrowRight") go(current + 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, go]);

  if (live.error) {
    return (
      <div className="space-y-4">
        <Button asChild variant="ghost" size="sm">
          <Link href="/runs">
            <ArrowLeft /> Runs
          </Link>
        </Button>
        <ErrorState error={live.error} onRetry={() => live.reload().catch(() => {})} />
      </div>
    );
  }

  if (!run) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-24 w-full" />
        <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
          <Skeleton className="hidden h-96 lg:block" />
          <Skeleton className="aspect-[16/10] w-full" />
        </div>
      </div>
    );
  }

  const task = tasks.get(run.task_id);
  const pct = run.max_steps ? Math.min(100, (run.n_steps / run.max_steps) * 100) : 0;

  async function cancel() {
    setCancelling(true);
    setActionError(null);
    try {
      await live.cancel();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setCancelling(false);
    }
  }

  async function remove() {
    if (!confirm("Delete this run and its artifacts?")) return;
    try {
      await getApi().deleteRun(id);
      router.push("/runs");
    } catch (e) {
      setActionError((e as Error).message);
    }
  }

  const rerunHref = `/runs/new?from=${encodeURIComponent(run.id)}`;

  return (
    <div className="space-y-5">
      {/* header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <Link href="/runs" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="size-4" /> Runs
          </Link>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <h1 className="truncate text-xl font-semibold tracking-tight sm:text-2xl">{task?.title ?? taskShortName(run.task_id)}</h1>
            <StatusBadge status={run.status} />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            {task && <BenchmarkBadge benchmark={task.benchmark} />}
            <span className="font-mono">{run.task_id}</span>
            <span>·</span>
            <button
              className="inline-flex items-center gap-1 font-mono hover:text-foreground"
              onClick={() => navigator.clipboard?.writeText(run.id)}
              title="Copy run id"
            >
              {run.id} <Copy className="size-3" />
            </button>
          </div>
          {run.goal && <p className="mt-3 max-w-3xl text-sm">{run.goal}</p>}
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {active ? (
            <Button variant="destructive" onClick={cancel} disabled={cancelling} data-testid="cancel-run">
              {cancelling ? <Loader2 className="animate-spin" /> : <Ban />} Cancel run
            </Button>
          ) : (
            <>
              <Button asChild variant="outline">
                <Link href={rerunHref}>
                  <RotateCcw /> Run again
                </Link>
              </Button>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon" onClick={remove} aria-label="Delete run">
                    <Trash2 />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Delete run</TooltipContent>
              </Tooltip>
            </>
          )}
        </div>
      </div>
      {actionError && <ErrorState error={actionError} />}

      {/* summary */}
      <Card size="sm">
        <CardContent>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            <Meta label="Agent">{agentLabel(run.agent)}</Meta>
            <Meta label="Steps">
              <span className="font-mono">
                {run.n_steps}
                <span className="text-muted-foreground">/{run.max_steps ?? "?"}</span>
              </span>
              <Progress value={pct} className="mt-1.5 h-1" />
            </Meta>
            <Meta label="Reward">
              <span className={cn("font-mono", (run.reward ?? 0) > 0 && "text-emerald-600 dark:text-emerald-400")}>
                {run.reward === null || run.reward === undefined ? "—" : run.reward.toFixed(2)}
              </span>
            </Meta>
            <Meta label="Duration">
              <LiveDuration start={run.started_at} end={run.finished_at} className="font-mono" />
            </Meta>
            <Meta label="Created">
              <RelativeTime iso={run.created_at} />
            </Meta>
            <Meta label="Stream">
              <StreamIndicator state={stream} />
            </Meta>
          </dl>
          {run.error && (
            <p className="mt-4 rounded-lg bg-destructive/10 px-3 py-2 font-mono text-xs break-words text-destructive" data-testid="run-error">
              {run.error}
            </p>
          )}
        </CardContent>
      </Card>

      {/* main grid */}
      <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)] xl:grid-cols-[260px_minmax(0,1fr)_340px]">
        <Card size="sm" className="order-2 lg:order-1 lg:max-h-[calc(100dvh-8rem)] lg:self-start">
          <CardHeader>
            <CardTitle>Timeline</CardTitle>
            <CardAction className="font-mono text-xs text-muted-foreground">{steps.length} steps</CardAction>
          </CardHeader>
          <CardContent className="overflow-y-auto">
            {steps.length === 0 && !active ? (
              <p className="text-sm text-muted-foreground">No steps recorded.</p>
            ) : (
              <StepTimeline steps={steps} selected={current} onSelect={go} live={active} />
            )}
          </CardContent>
        </Card>

        <div className="order-1 min-w-0 space-y-4 lg:order-2">
          <Card size="sm">
            <CardContent className="space-y-3">
              <Screenshot runId={id} step={step} live={active && following} />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-1">
                  <Button variant="outline" size="icon-sm" onClick={() => go(0)} disabled={!current} aria-label="First step">
                    <ChevronFirst />
                  </Button>
                  <Button variant="outline" size="icon-sm" onClick={() => current !== null && go(current - 1)} disabled={!current} aria-label="Previous step">
                    <ChevronLeft />
                  </Button>
                  <span className="min-w-20 text-center font-mono text-xs tabular-nums" data-testid="step-position">
                    {current === null ? "—" : `${current + 1} / ${steps.length}`}
                  </span>
                  <Button
                    variant="outline"
                    size="icon-sm"
                    onClick={() => current !== null && go(current + 1)}
                    disabled={current === null || current === latest}
                    aria-label="Next step"
                  >
                    <ChevronRight />
                  </Button>
                  <Button variant="outline" size="icon-sm" onClick={() => go(latest)} disabled={current === latest} aria-label="Last step">
                    <ChevronLast />
                  </Button>
                </div>
                {active && (
                  <Button size="sm" variant={following ? "secondary" : "outline"} onClick={() => setSelected(null)} aria-pressed={following}>
                    <Radio className={cn(following && "text-rose-500")} /> {following ? "Following live" : "Jump to live"}
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>

          {step ? (
            <Card size="sm" data-testid="step-inspector">
              <CardHeader>
                <CardTitle>Step {step.index}</CardTitle>
                <CardAction className="flex items-center gap-3 font-mono text-xs text-muted-foreground">
                  <span>reward {step.reward.toFixed(2)}</span>
                  <span>{formatDuration(step.elapsed_ms)}</span>
                </CardAction>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Action</p>
                  <div className="rounded-lg bg-muted/60 px-3 py-2 text-sm" data-testid="step-action">
                    <ActionCode action={step.action} />
                  </div>
                </div>
                {step.thought && (
                  <div>
                    <p className="mb-1 text-xs font-medium text-muted-foreground">Thought</p>
                    <p className="text-sm leading-relaxed" data-testid="step-thought">
                      {step.thought}
                    </p>
                  </div>
                )}
                {step.last_action_error && (
                  <p className="rounded-lg bg-destructive/10 px-3 py-2 font-mono text-xs break-words text-destructive">{step.last_action_error}</p>
                )}
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  {step.url && (
                    <a href={step.url} target="_blank" rel="noreferrer" className="inline-flex max-w-full items-center gap-1 truncate hover:text-foreground">
                      <ExternalLink className="size-3 shrink-0" /> <span className="truncate">{step.url}</span>
                    </a>
                  )}
                  {step.terminated && <span className="text-emerald-600 dark:text-emerald-400">terminated</span>}
                  {step.truncated && <span className="text-amber-600">truncated</span>}
                </div>
                <Tabs defaultValue="axtree">
                  <TabsList>
                    <TabsTrigger value="axtree">AXTree</TabsTrigger>
                    <TabsTrigger value="html">HTML</TabsTrigger>
                    <TabsTrigger value="raw">JSON</TabsTrigger>
                    {logs.length > 0 && <TabsTrigger value="logs">Logs</TabsTrigger>}
                  </TabsList>
                  <TabsContent value="axtree">
                    {detail.isLoading && !detail.data ? (
                      <Skeleton className="h-40" />
                    ) : (
                      <AxTreeView text={detail.data?.axtree_txt} focusedBid={detail.data?.focused_element_bid} />
                    )}
                  </TabsContent>
                  <TabsContent value="html">
                    <pre className="max-h-80 overflow-auto rounded-lg bg-muted/60 p-3 font-mono text-[11px] leading-5">
                      {detail.data?.pruned_html ?? "No HTML captured for this step."}
                    </pre>
                  </TabsContent>
                  <TabsContent value="raw">
                    <pre className="max-h-80 overflow-auto rounded-lg bg-muted/60 p-3 font-mono text-[11px] leading-5">
                      {JSON.stringify(detail.data ?? step, (k, v) => (k === "axtree_txt" || k === "pruned_html" ? (v ? "…" : v) : v), 2)}
                    </pre>
                  </TabsContent>
                  <TabsContent value="logs">
                    <pre className="max-h-80 overflow-auto rounded-lg bg-muted/60 p-3 font-mono text-[11px] leading-5">
                      {logs.map((l) => `${l.timestamp}  ${l.message}`).join("\n")}
                    </pre>
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>
          ) : (
            !active && <EmptyState title="No steps" description="This run finished without recording any steps." />
          )}
        </div>

        <Card size="sm" className="order-3 gap-0 py-0 lg:col-span-2 xl:col-span-1 xl:max-h-[calc(100dvh-8rem)] xl:self-start">
          <CardHeader className="border-b py-3">
            <CardTitle className="flex items-center gap-2">
              <MessageSquare className="size-4" /> Chat
            </CardTitle>
            <CardAction className="font-mono text-xs text-muted-foreground">{chat.length}</CardAction>
          </CardHeader>
          <ChatPanel messages={chat} onSend={live.sendChat} disabled={!active} className="h-[420px] xl:h-[560px]" />
        </Card>
      </div>
    </div>
  );
}
