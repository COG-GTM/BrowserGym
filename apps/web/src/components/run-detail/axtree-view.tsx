"use client";

import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export function AxTreeView({ text, focusedBid }: { text: string | null | undefined; focusedBid?: string | null }) {
  const [filter, setFilter] = useState("");
  const lines = useMemo(() => (text ?? "").split("\n"), [text]);
  if (!text) return <p className="p-4 text-sm text-muted-foreground">No AXTree captured for this step.</p>;
  const f = filter.trim().toLowerCase();
  return (
    <div className="space-y-2">
      <div className="relative">
        <Search className="absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter nodes or bid…" className="h-8 pl-8 text-xs" aria-label="Filter AXTree" />
      </div>
      <pre className="max-h-80 overflow-auto rounded-lg bg-muted/60 p-3 font-mono text-[11px] leading-5" data-testid="axtree">
        {lines.map((line, i) => {
          if (f && !line.toLowerCase().includes(f)) return null;
          const m = line.match(/^(\t*)(?:\[([^\]]+)\] )?(\S+)(.*)$/);
          if (!m) return <div key={i}>{line}</div>;
          const [, indent, bid, role, rest] = m;
          const isFocused = !!bid && bid === focusedBid;
          return (
            <div key={i} className={cn("rounded px-1 whitespace-pre", isFocused && "bg-primary/15 ring-1 ring-primary/40")}>
              {indent.replace(/\t/g, "  ")}
              {bid && <span className="text-amber-700 dark:text-amber-300">[{bid}] </span>}
              <span className="text-sky-700 dark:text-sky-300">{role}</span>
              <span className="text-foreground/80">{rest}</span>
            </div>
          );
        })}
      </pre>
    </div>
  );
}
