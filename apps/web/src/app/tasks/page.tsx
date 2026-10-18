"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Play, Search, Wrench } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState } from "@/components/states";
import { BenchmarkBadge, BenchmarkFilter } from "@/components/tasks/benchmark";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useDebounced } from "@/hooks/use-debounced";
import { useTasks } from "@/hooks/use-api";
import type { Task } from "@/lib/api";

export default function TasksPage() {
  const [query, setQuery] = useState("");
  const [benchmark, setBenchmark] = useState<string>();
  const q = useDebounced(query);
  const all = useTasks();
  const { data, error, isLoading, mutate } = useTasks({ q: q || undefined, benchmark });
  const benchmarks = useMemo(() => [...new Set((all.data ?? []).map((t) => t.benchmark))], [all.data]);

  const grouped = useMemo(() => {
    const m = new Map<string, Task[]>();
    for (const t of data ?? []) m.set(t.benchmark, [...(m.get(t.benchmark) ?? []), t]);
    return [...m.entries()];
  }, [data]);

  return (
    <div>
      <PageHeader
        title="Tasks"
        description={`Registered BrowserGym environments${all.data ? ` · ${all.data.length} tasks` : ""}.`}
      />
      <div className="mb-6 space-y-3">
        <div className="relative max-w-md">
          <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search tasks, e.g. click, login, webarena…"
            className="h-9 pl-9"
            aria-label="Search tasks"
          />
        </div>
        <BenchmarkFilter benchmarks={benchmarks} value={benchmark} onChange={setBenchmark} />
      </div>
      {error && <ErrorState error={error} onRetry={() => mutate()} className="mb-4" />}
      {isLoading && !data && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      )}
      {data && data.length === 0 && <EmptyState title="No tasks match" description="Try a different search or benchmark." />}
      <div className="space-y-8">
        {grouped.map(([bench, tasks]) => (
          <section key={bench}>
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold tracking-wide text-muted-foreground uppercase">
              {bench} <span className="font-mono text-xs font-normal">({tasks.length})</span>
            </h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {tasks.map((task) => (
                <Card key={task.id} size="sm" className="transition-shadow hover:shadow-md" data-testid="task-card">
                  <CardHeader>
                    <div className="flex items-center gap-2">
                      <BenchmarkBadge benchmark={task.benchmark} />
                      {task.requires_setup && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="inline-flex h-5 items-center gap-1 rounded-md bg-amber-500/10 px-1.5 text-[11px] font-medium text-amber-700 dark:text-amber-300">
                              <Wrench className="size-3" /> needs setup
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>Requires external servers / environment variables</TooltipContent>
                        </Tooltip>
                      )}
                    </div>
                    <CardTitle className="mt-1">{task.title}</CardTitle>
                    <CardDescription className="font-mono text-xs break-all">{task.id}</CardDescription>
                  </CardHeader>
                  <CardContent className="flex-1 text-sm text-muted-foreground">{task.description}</CardContent>
                  <CardFooter className="border-t bg-muted/30 py-2!">
                    <Button asChild size="sm" variant="ghost" className="ml-auto">
                      <Link href={`/runs/new?task=${encodeURIComponent(task.id)}`}>
                        <Play /> Run task
                      </Link>
                    </Button>
                  </CardFooter>
                </Card>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
