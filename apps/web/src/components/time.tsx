"use client";

import { useEffect, useState } from "react";
import { formatDateTime, formatDuration, formatRelative } from "@/lib/format";

export function useNow(intervalMs = 1000, enabled = true) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, enabled]);
  return now;
}

export function RelativeTime({ iso, className }: { iso: string | null | undefined; className?: string }) {
  const now = useNow(15_000);
  if (!iso) return <span className={className}>—</span>;
  return (
    <time dateTime={iso} title={formatDateTime(iso)} className={className} suppressHydrationWarning>
      {formatRelative(iso, now)}
    </time>
  );
}

export function LiveDuration({
  start,
  end,
  className,
}: {
  start: string | null | undefined;
  end: string | null | undefined;
  className?: string;
}) {
  const now = useNow(1000, !!start && !end);
  if (!start) return <span className={className}>—</span>;
  const ms = (end ? Date.parse(end) : now) - Date.parse(start);
  return (
    <span className={className} suppressHydrationWarning>
      {formatDuration(Math.max(0, ms))}
    </span>
  );
}
