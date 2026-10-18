import { cn } from "@/lib/utils";

/** Renders a BrowserGym action string like click('a42') with light syntax highlighting. */
export function ActionCode({ action, className }: { action: string | null | undefined; className?: string }) {
  if (!action) return <code className={cn("font-mono text-muted-foreground", className)}>—</code>;
  const m = action.match(/^(\w+)\((.*)\)$/s);
  if (!m) return <code className={cn("font-mono", className)}>{action}</code>;
  const [, fn, args] = m;
  const parts = args.split(/('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")/g);
  return (
    <code className={cn("font-mono break-all", className)}>
      <span className="text-primary">{fn}</span>
      <span className="text-muted-foreground">(</span>
      {parts.map((p, i) =>
        /^['"]/.test(p) ? (
          <span key={i} className="text-emerald-700 dark:text-emerald-400">
            {p}
          </span>
        ) : (
          <span key={i} className="text-amber-700 dark:text-amber-300">
            {p}
          </span>
        ),
      )}
      <span className="text-muted-foreground">)</span>
    </code>
  );
}
