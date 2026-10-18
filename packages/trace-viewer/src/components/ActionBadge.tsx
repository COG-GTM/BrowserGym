import { useMemo } from "react";
import { tryParseActions, type ParsedAction } from "../parsers/action";
import { cx } from "../utils";

export interface ActionBadgeProps {
  /** Raw BrowserGym action string, e.g. `click('a42')`. */
  action: string | null | undefined;
  /** Mark the badge as failed (e.g. the step that follows reported `last_action_error`). */
  error?: boolean;
  /** Compact rendering: name + bid only. */
  compact?: boolean;
  /** Called when the bid chip is clicked/hovered (for cross-highlighting). */
  onBidClick?: (bid: string) => void;
  onBidHover?: (bid: string | null) => void;
  className?: string;
}

const MAX_TEXT = 60;

function truncate(s: string, n = MAX_TEXT): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

export function ActionBadge({ action, error, compact, onBidClick, onBidHover, className }: ActionBadgeProps) {
  const parsed: ParsedAction[] | null = useMemo(() => tryParseActions(action), [action]);

  if (!action) {
    return (
      <span className={cx("stv-action", "stv-action--none", className)} data-category="none">
        <span className="stv-action__name">no action</span>
      </span>
    );
  }
  if (!parsed) {
    return (
      <span className={cx("stv-action", "stv-action--invalid", className)} data-category="invalid" title={action}>
        <span className="stv-action__name">unparsed</span>
        <code className="stv-action__text">{truncate(action)}</code>
      </span>
    );
  }
  const badges = parsed.map((p, i) => (
    <SingleBadge
      key={i}
      parsed={p}
      error={error}
      compact={compact}
      onBidClick={onBidClick}
      onBidHover={onBidHover}
      className={parsed.length === 1 ? className : undefined}
    />
  ));
  if (badges.length === 1) return badges[0]!;
  return (
    <span className={cx("stv-actions", className)} title={action}>
      {badges}
    </span>
  );
}

function SingleBadge({
  parsed,
  error,
  compact,
  onBidClick,
  onBidHover,
  className,
}: Omit<ActionBadgeProps, "action"> & { parsed: ParsedAction }) {
  return (
    <span
      className={cx("stv-action", error && "stv-action--error", className)}
      data-category={parsed.category}
      title={parsed.raw}
    >
      <span className="stv-action__name">{parsed.name}</span>
      {parsed.bids.map((bid, i) => (
        <button
          key={`${bid}-${i}`}
          type="button"
          className="stv-action__bid"
          aria-label={`Element ${bid}`}
          onClick={onBidClick ? () => onBidClick(bid) : undefined}
          onMouseEnter={onBidHover ? () => onBidHover(bid) : undefined}
          onMouseLeave={onBidHover ? () => onBidHover(null) : undefined}
          tabIndex={onBidClick ? 0 : -1}
        >
          {i > 0 && <span aria-hidden>→ </span>}[{bid}]
        </button>
      ))}
      {!compact && parsed.text && <span className="stv-action__text">{truncate(parsed.text)}</span>}
    </span>
  );
}
