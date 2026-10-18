import { cn } from "@/lib/utils";

const COLORS: Record<string, string> = {
  openended: "bg-violet-500/10 text-violet-700 dark:text-violet-300",
  miniwob: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
  webarena: "bg-orange-500/10 text-orange-700 dark:text-orange-300",
  visualwebarena: "bg-pink-500/10 text-pink-700 dark:text-pink-300",
  workarena: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  assistantbench: "bg-amber-500/10 text-amber-700 dark:text-amber-300",
  weblinx: "bg-cyan-500/10 text-cyan-700 dark:text-cyan-300",
};

export function BenchmarkBadge({ benchmark, className }: { benchmark: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center rounded-md px-1.5 font-mono text-[11px] font-medium",
        COLORS[benchmark] ?? "bg-muted text-muted-foreground",
        className,
      )}
    >
      {benchmark}
    </span>
  );
}

export function BenchmarkFilter({
  benchmarks,
  value,
  onChange,
}: {
  benchmarks: string[];
  value: string | undefined;
  onChange: (v: string | undefined) => void;
}) {
  return (
    <div className="no-scrollbar -mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:px-0" role="tablist" aria-label="Filter by benchmark">
      {[undefined, ...benchmarks].map((b) => (
        <button
          type="button"
          key={b ?? "all"}
          role="tab"
          aria-selected={value === b}
          onClick={() => onChange(b)}
          className={cn(
            "inline-flex h-7 shrink-0 items-center rounded-full border px-3 text-xs font-medium transition-colors",
            value === b ? "border-primary bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
          )}
        >
          {b ?? "All"}
        </button>
      ))}
    </div>
  );
}
