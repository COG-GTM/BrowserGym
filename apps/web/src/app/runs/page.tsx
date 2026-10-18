"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { ChevronLeft, ChevronRight, Plus, RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { RunList } from "@/components/runs/run-list";
import { STATUS_STYLES } from "@/components/status-badge";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useRuns, useTaskIndex } from "@/hooks/use-api";
import { RUN_STATUSES, type RunStatus } from "@/lib/api";
import { STATUS_LABEL } from "@/lib/format";
import { cn } from "@/lib/utils";

const PAGE_SIZES = [10, 20, 50];

function RunsView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const statusParam = params.get("status");
  const status = RUN_STATUSES.includes(statusParam as RunStatus) ? (statusParam as RunStatus) : undefined;
  const [limit, setLimit] = useState(20);
  // Stack of cursors for the pages visited; the last entry is the current page's cursor.
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const cursor = cursors[cursors.length - 1];
  const page = cursors.length;

  const { data, error, isLoading, isValidating, mutate } = useRuns({ status, limit, cursor });
  const tasks = useTaskIndex();

  const setStatus = (s?: RunStatus) => {
    setCursors([undefined]);
    const next = new URLSearchParams(params);
    if (s) next.set("status", s);
    else next.delete("status");
    router.replace(`${pathname}${next.size ? `?${next}` : ""}`);
  };

  return (
    <div>
      <PageHeader
        title="Runs"
        description="Every BrowserGym episode, newest first."
        actions={
          <>
            <Button variant="outline" size="icon" onClick={() => mutate()} aria-label="Refresh">
              <RefreshCw className={cn(isValidating && "animate-spin")} />
            </Button>
            <Button asChild>
              <Link href="/runs/new">
                <Plus /> New run
              </Link>
            </Button>
          </>
        }
      />
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="no-scrollbar -mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0" role="tablist" aria-label="Filter by status">
          {[undefined, ...RUN_STATUSES].map((s) => (
            <button
              key={s ?? "all"}
              role="tab"
              aria-selected={status === s}
              onClick={() => setStatus(s)}
              className={cn(
                "inline-flex h-8 shrink-0 items-center gap-2 rounded-full border px-3 text-sm font-medium transition-colors",
                status === s ? "border-primary bg-primary text-primary-foreground" : "bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              {s && <span className={cn("size-2 rounded-full", STATUS_STYLES[s].dot)} />}
              {s ? STATUS_LABEL[s] : "All"}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          Rows
          <Select
            value={String(limit)}
            onValueChange={(v) => {
              setLimit(Number(v));
              setCursors([undefined]);
            }}
          >
            <SelectTrigger size="sm" className="w-20" aria-label="Rows per page">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PAGE_SIZES.map((n) => (
                <SelectItem key={n} value={String(n)}>
                  {n}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {error && <ErrorState error={error} onRetry={() => mutate()} className="mb-4" />}
      {!isLoading && data && data.items.length === 0 ? (
        <EmptyState
          title={status ? `No ${STATUS_LABEL[status].toLowerCase()} runs` : "No runs yet"}
          description="Launch a BrowserGym episode to see it here."
          action={
            <Button asChild size="sm">
              <Link href="/runs/new">New run</Link>
            </Button>
          }
        />
      ) : (
        <RunList runs={data?.items} tasks={tasks} loading={isLoading} />
      )}

      <div className="mt-4 flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Page {page}
          {data ? ` · ${data.items.length} runs` : ""}
        </p>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={page === 1 || isLoading} onClick={() => setCursors((c) => c.slice(0, -1))}>
            <ChevronLeft /> Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={!data?.next_cursor || isLoading}
            onClick={() => data?.next_cursor && setCursors((c) => [...c, data.next_cursor!])}
          >
            Next <ChevronRight />
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function RunsPage() {
  return (
    <Suspense>
      <RunsView />
    </Suspense>
  );
}
