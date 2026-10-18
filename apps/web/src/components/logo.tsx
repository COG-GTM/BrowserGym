import { cn } from "@/lib/utils";

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-semibold tracking-tight", className)}>
      <span className="relative grid size-7 place-items-center rounded-lg bg-primary text-primary-foreground shadow-sm">
        <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round">
          <path d="M16 7.5c-.8-1.3-2.3-2-4-2-2.2 0-4 1.3-4 3.1 0 4.2 8 2.6 8 6.9 0 1.8-1.8 3-4 3-1.8 0-3.4-.8-4.2-2.2" />
        </svg>
      </span>
      <span className="text-lg">Side</span>
    </span>
  );
}
