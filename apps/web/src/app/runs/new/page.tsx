"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { Bot, Check, Loader2, Rocket, Search, Wrench } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { ErrorState } from "@/components/states";
import { BenchmarkBadge, BenchmarkFilter } from "@/components/tasks/benchmark";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useDebounced } from "@/hooks/use-debounced";
import { useAgents, useTasks } from "@/hooks/use-api";
import { ApiError, OPENENDED_TASK_ID, getApi, type AgentType, type RunCreate } from "@/lib/api";
import { cn } from "@/lib/utils";

const AGENT_BLURB: Record<AgentType, string> = {
  mock: "Deterministic, offline. Great for demos and tests.",
  scripted: "Replays a fixed list of BrowserGym actions.",
  openai: "LLM agent — needs OPENAI_API_KEY on the server.",
  anthropic: "LLM agent — needs ANTHROPIC_API_KEY on the server.",
};

function Section({ n, title, description, children }: { n: number; title: string; description?: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="grid size-6 place-items-center rounded-full bg-primary/10 text-xs font-semibold text-primary">{n}</span>
          {title}
        </CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className="space-y-4">{children}</CardContent>
    </Card>
  );
}

function isValidUrl(s: string) {
  try {
    const u = new URL(s);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

function NewRunForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [query, setQuery] = useState("");
  const [benchmark, setBenchmark] = useState<string>();
  const q = useDebounced(query);
  const allTasks = useTasks();
  const tasks = useTasks({ q: q || undefined, benchmark });
  const agents = useAgents();

  const [taskId, setTaskId] = useState<string>(params.get("task") ?? OPENENDED_TASK_ID);
  const [agentType, setAgentType] = useState<AgentType>("mock");
  const [model, setModel] = useState<string | null>(null);
  const [useAxtree, setUseAxtree] = useState(true);
  const [useScreenshot, setUseScreenshot] = useState(false);
  const [goal, setGoal] = useState("");
  const [startUrl, setStartUrl] = useState("");
  const [maxSteps, setMaxSteps] = useState(15);
  const [headless, setHeadless] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  const benchmarks = useMemo(() => [...new Set((allTasks.data ?? []).map((t) => t.benchmark))], [allTasks.data]);
  const selectedTask = allTasks.data?.find((t) => t.id === taskId);
  const selectedAgent = agents.data?.find((a) => a.type === agentType);
  const isOpenended = taskId === OPENENDED_TASK_ID;

  // "Run again" links here with ?from=<run id>: prefill the form from that run's configuration.
  const fromRunId = params.get("from");
  useEffect(() => {
    if (!fromRunId) return;
    let stale = false;
    getApi()
      .getRun(fromRunId)
      .then((run) => {
        if (stale) return;
        setTaskId(run.task_id);
        setAgentType(run.agent.type);
        setModel(run.agent.model ?? null);
        setUseAxtree(run.agent.use_axtree ?? true);
        setUseScreenshot(run.agent.use_screenshot ?? false);
        if (run.task_id === OPENENDED_TASK_ID) setGoal(run.goal ?? "");
        if (run.max_steps) setMaxSteps(run.max_steps);
      })
      .catch(() => {});
    return () => {
      stale = true;
    };
  }, [fromRunId]);

  useEffect(() => {
    const models = selectedAgent?.models ?? [];
    setModel((m) => (m && models.includes(m) ? m : (models[0] ?? null)));
    if (agentType === "openai" || agentType === "anthropic") setUseScreenshot(true);
  }, [selectedAgent, agentType]);

  const errors: Record<string, string> = {};
  if (!selectedTask && allTasks.data) errors.task = "Pick a task";
  if (isOpenended && !goal.trim()) errors.goal = "A goal is required for open-ended tasks";
  if (isOpenended && startUrl && !isValidUrl(startUrl)) errors.startUrl = "Enter a valid http(s) URL";
  if (!Number.isInteger(maxSteps) || maxSteps < 1 || maxSteps > 100) errors.maxSteps = "Between 1 and 100";
  const valid = Object.keys(errors).length === 0 && !!selectedTask;

  const body: RunCreate = {
    task_id: taskId,
    agent: { type: agentType, model, use_axtree: useAxtree, use_screenshot: useScreenshot },
    goal: isOpenended ? goal.trim() || null : null,
    start_url: isOpenended ? startUrl.trim() || null : null,
    max_steps: maxSteps,
    headless,
  };

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!valid) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const run = await getApi().createRun(body);
      router.push(`/runs/${run.id}`);
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.detail : (err as Error).message);
      setSubmitting(false);
    }
  }

  const fieldError = (k: string) => touched && errors[k] ? <p className="text-xs text-destructive">{errors[k]}</p> : null;

  return (
    <form onSubmit={submit} className="grid gap-6 lg:grid-cols-[1fr_340px]" noValidate>
      <div className="min-w-0 space-y-6">
        <Section n={1} title="Task" description="Pick a registered BrowserGym environment.">
          <div className="relative">
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search tasks…"
              className="h-9 pl-9"
              aria-label="Search tasks"
            />
          </div>
          <BenchmarkFilter benchmarks={benchmarks} value={benchmark} onChange={setBenchmark} />
          {tasks.error && <ErrorState error={tasks.error} onRetry={() => tasks.mutate()} />}
          <ScrollArea className="h-72 rounded-lg border">
            <div role="radiogroup" aria-label="Task" className="divide-y">
              {!tasks.data &&
                Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="m-3 h-10" />)}
              {tasks.data?.length === 0 && <p className="p-6 text-center text-sm text-muted-foreground">No tasks match.</p>}
              {tasks.data?.map((t) => (
                <button
                  type="button"
                  role="radio"
                  aria-checked={t.id === taskId}
                  key={t.id}
                  onClick={() => setTaskId(t.id)}
                  className={cn(
                    "flex w-full items-start gap-3 px-3 py-2.5 text-left transition-colors hover:bg-muted/60",
                    t.id === taskId && "bg-primary/5 hover:bg-primary/10",
                  )}
                >
                  <span
                    className={cn(
                      "mt-0.5 grid size-4 shrink-0 place-items-center rounded-full border",
                      t.id === taskId && "border-primary bg-primary text-primary-foreground",
                    )}
                  >
                    {t.id === taskId && <Check className="size-3" />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium">{t.title}</span>
                      <BenchmarkBadge benchmark={t.benchmark} />
                      {t.requires_setup && (
                        <span className="inline-flex items-center gap-1 text-[11px] text-amber-700 dark:text-amber-300">
                          <Wrench className="size-3" /> needs setup
                        </span>
                      )}
                    </span>
                    <span className="block truncate font-mono text-xs text-muted-foreground">{t.id}</span>
                  </span>
                </button>
              ))}
            </div>
          </ScrollArea>
          {fieldError("task")}
          {selectedTask?.requires_setup && (
            <p className="rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
              <strong>{selectedTask.benchmark}</strong> needs external servers / environment variables on the runner host.
            </p>
          )}
          {isOpenended && (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="goal">Goal</Label>
                <Textarea
                  id="goal"
                  value={goal}
                  onChange={(e) => setGoal(e.target.value)}
                  placeholder="e.g. Find the latest BrowserGym release on GitHub and report its version."
                  rows={3}
                  aria-invalid={touched && !!errors.goal}
                />
                {fieldError("goal")}
              </div>
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="start_url">Start URL <span className="font-normal text-muted-foreground">(optional)</span></Label>
                <Input
                  id="start_url"
                  type="url"
                  value={startUrl}
                  onChange={(e) => setStartUrl(e.target.value)}
                  placeholder="https://github.com/ServiceNow/BrowserGym"
                  aria-invalid={touched && !!errors.startUrl}
                />
                {fieldError("startUrl")}
              </div>
            </div>
          )}
        </Section>

        <Section n={2} title="Agent" description="Who drives the browser.">
          {agents.error && <ErrorState error={agents.error} onRetry={() => agents.mutate()} />}
          <div role="radiogroup" aria-label="Agent" className="grid gap-3 sm:grid-cols-2">
            {!agents.data && Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-20" />)}
            {agents.data?.map((a) => (
              <button
                type="button"
                role="radio"
                aria-checked={a.type === agentType}
                key={a.type}
                onClick={() => setAgentType(a.type)}
                className={cn(
                  "flex items-start gap-3 rounded-xl border p-3 text-left transition-all hover:bg-muted/50",
                  a.type === agentType && "border-primary bg-primary/5 ring-1 ring-primary",
                )}
              >
                <span className={cn("grid size-8 shrink-0 place-items-center rounded-lg bg-muted", a.type === agentType && "bg-primary text-primary-foreground")}>
                  <Bot className="size-4" />
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-medium">{a.title}</span>
                  <span className="block text-xs text-muted-foreground">{AGENT_BLURB[a.type]}</span>
                </span>
              </button>
            ))}
          </div>
          {selectedAgent?.models && selectedAgent.models.length > 0 && (
            <div className="space-y-2">
              <Label>Model</Label>
              <Select value={model ?? undefined} onValueChange={setModel}>
                <SelectTrigger className="w-full sm:w-72" aria-label="Model">
                  <SelectValue placeholder="Choose a model" />
                </SelectTrigger>
                <SelectContent>
                  {selectedAgent.models.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex items-center justify-between gap-3 rounded-lg border p-3">
              <span>
                <span className="block text-sm font-medium">Use AXTree</span>
                <span className="block text-xs text-muted-foreground">Accessibility tree observation</span>
              </span>
              <Switch checked={useAxtree} onCheckedChange={setUseAxtree} aria-label="Use AXTree" />
            </label>
            <label className="flex items-center justify-between gap-3 rounded-lg border p-3">
              <span>
                <span className="block text-sm font-medium">Use screenshot</span>
                <span className="block text-xs text-muted-foreground">Send screenshots to the agent</span>
              </span>
              <Switch checked={useScreenshot} onCheckedChange={setUseScreenshot} aria-label="Use screenshot" />
            </label>
          </div>
        </Section>

        <Section n={3} title="Limits">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="max_steps">Max steps</Label>
              <div className="flex items-center gap-2">
                <Input
                  id="max_steps"
                  type="number"
                  min={1}
                  max={100}
                  value={Number.isNaN(maxSteps) ? "" : maxSteps}
                  onChange={(e) => setMaxSteps(e.target.valueAsNumber)}
                  className="w-24"
                  aria-invalid={touched && !!errors.maxSteps}
                />
                {[5, 15, 30, 50].map((n) => (
                  <Button key={n} type="button" size="xs" variant={maxSteps === n ? "secondary" : "ghost"} onClick={() => setMaxSteps(n)}>
                    {n}
                  </Button>
                ))}
              </div>
              {fieldError("maxSteps")}
            </div>
            <label className="flex items-center justify-between gap-3 rounded-lg border p-3">
              <span>
                <span className="block text-sm font-medium">Headless browser</span>
                <span className="block text-xs text-muted-foreground">Turn off to watch Chromium on the runner host</span>
              </span>
              <Switch checked={headless} onCheckedChange={setHeadless} aria-label="Headless" />
            </label>
          </div>
        </Section>
      </div>

      <div className="lg:sticky lg:top-20 lg:self-start">
        <Card>
          <CardHeader>
            <CardTitle>Summary</CardTitle>
            <CardDescription>POST /runs</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <dl className="space-y-2">
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">Task</dt>
                <dd className="truncate text-right font-medium">{selectedTask?.title ?? "—"}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">Agent</dt>
                <dd className="text-right font-medium">
                  {selectedAgent?.title.split(" (")[0] ?? agentType}
                  {model ? ` · ${model}` : ""}
                </dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">Max steps</dt>
                <dd className="font-mono">{Number.isNaN(maxSteps) ? "—" : maxSteps}</dd>
              </div>
            </dl>
            <pre className="max-h-56 overflow-auto rounded-lg bg-muted p-3 font-mono text-[11px] leading-relaxed" data-testid="request-preview">
              {JSON.stringify(body, null, 2)}
            </pre>
            {submitError && (
              <p role="alert" className="rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
                {submitError}
              </p>
            )}
          </CardContent>
          <CardFooter>
            <Button type="submit" className="w-full" size="lg" disabled={submitting || (touched && !valid)}>
              {submitting ? <Loader2 className="animate-spin" /> : <Rocket />}
              Launch run
            </Button>
          </CardFooter>
        </Card>
      </div>
    </form>
  );
}

export default function NewRunPage() {
  return (
    <div>
      <PageHeader title="New run" description="Launch a BrowserGym episode: choose a task, an agent and limits." />
      <Suspense>
        <NewRunForm />
      </Suspense>
    </div>
  );
}
