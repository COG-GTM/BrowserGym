import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ancestorsOf, nodeMatches, parseAXTree, type AXNode } from "../parsers/axtree";
import { cx } from "../utils";

export interface AXTreeViewerProps {
  /** BrowserGym `axtree_txt` (output of `flatten_axtree_to_str`). */
  axtree: string | null | undefined;
  /** Bid referenced by the step's action; highlighted, expanded and scrolled into view. */
  highlightBid?: string | null;
  /** Currently focused element (`focused_element_bid`). */
  focusedBid?: string | null;
  /** Nodes deeper than this start collapsed (paths to highlighted / matching nodes are always expanded). */
  defaultExpandDepth?: number;
  onSelectBid?: (bid: string) => void;
  onHoverBid?: (bid: string | null) => void;
  /** Initial search query. */
  defaultQuery?: string;
  className?: string;
}

interface Row {
  node: AXNode;
  match: boolean;
}

export function AXTreeViewer({
  axtree,
  highlightBid,
  focusedBid,
  defaultExpandDepth = 4,
  onSelectBid,
  onHoverBid,
  defaultQuery = "",
  className,
}: AXTreeViewerProps) {
  const tree = useMemo(() => parseAXTree(axtree), [axtree]);
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [query, setQuery] = useState(defaultQuery);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [matchCursor, setMatchCursor] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setCollapsed(new Set());
    setExpanded(new Set());
  }, [tree]);

  const forcedOpen = useMemo(() => {
    const s = new Set<string>();
    for (const n of highlightBid ? tree.byBid.get(highlightBid) ?? [] : []) ancestorsOf(n).forEach((a) => s.add(a.id));
    return s;
  }, [tree, highlightBid]);

  const matches = useMemo(() => (query.trim() ? tree.nodes.filter((n) => nodeMatches(n, query)) : []), [tree, query]);

  const rows: Row[] = useMemo(() => {
    const searching = query.trim().length > 0;
    const matchIds = new Set(matches.map((n) => n.id));
    const keep = new Set<string>();
    if (searching) for (const m of matches) [m, ...ancestorsOf(m)].forEach((n) => keep.add(n.id));
    const out: Row[] = [];
    const isOpen = (n: AXNode) => {
      if (searching) return true;
      if (collapsed.has(n.id)) return false;
      return expanded.has(n.id) || forcedOpen.has(n.id) || n.depth < defaultExpandDepth;
    };
    const walk = (nodes: AXNode[]) => {
      for (const n of nodes) {
        if (searching && !keep.has(n.id)) continue;
        out.push({ node: n, match: matchIds.has(n.id) });
        if (n.children.length && isOpen(n)) walk(n.children);
      }
    };
    walk(tree.roots);
    return out;
  }, [tree, query, matches, collapsed, expanded, forcedOpen, defaultExpandDepth]);

  const isNodeOpen = (n: AXNode) =>
    query.trim()
      ? true
      : !collapsed.has(n.id) && (expanded.has(n.id) || forcedOpen.has(n.id) || n.depth < defaultExpandDepth);

  const toggle = (n: AXNode, open?: boolean) => {
    const next = open ?? !isNodeOpen(n);
    setCollapsed((s) => {
      const c = new Set(s);
      if (next) c.delete(n.id);
      else c.add(n.id);
      return c;
    });
    setExpanded((s) => {
      const c = new Set(s);
      if (next) c.add(n.id);
      else c.delete(n.id);
      return c;
    });
  };

  const scrollTo = (id: string) => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-node-id="${id}"]`);
    el?.scrollIntoView?.({ block: "nearest" });
  };

  useEffect(() => {
    if (!highlightBid) return;
    const first = tree.byBid.get(highlightBid)?.[0];
    if (first) requestAnimationFrame(() => scrollTo(first.id));
  }, [highlightBid, tree]);

  const focusRow = (id: string) => {
    setActiveId(id);
    listRef.current?.querySelector<HTMLElement>(`[data-node-id="${id}"]`)?.focus();
  };

  const onRowKey = (e: KeyboardEvent<HTMLDivElement>, n: AXNode, i: number) => {
    const open = n.children.length > 0 && isNodeOpen(n);
    switch (e.key) {
      case "ArrowDown":
        if (rows[i + 1]) focusRow(rows[i + 1]!.node.id);
        break;
      case "ArrowUp":
        if (rows[i - 1]) focusRow(rows[i - 1]!.node.id);
        break;
      case "ArrowRight":
        if (n.children.length && !open) toggle(n, true);
        else if (open && rows[i + 1]) focusRow(rows[i + 1]!.node.id);
        break;
      case "ArrowLeft":
        if (open) toggle(n, false);
        else if (n.parent) focusRow(n.parent.id);
        break;
      case "Home":
        if (rows[0]) focusRow(rows[0].node.id);
        break;
      case "End":
        if (rows.length) focusRow(rows[rows.length - 1]!.node.id);
        break;
      case "Enter":
      case " ":
        if (n.bid) onSelectBid?.(n.bid);
        else if (n.children.length) toggle(n);
        break;
      default:
        return;
    }
    e.preventDefault();
  };

  const onSearchKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && matches.length) {
      e.preventDefault();
      const next = (matchCursor + (e.shiftKey ? matches.length - 1 : 1)) % matches.length;
      setMatchCursor(next);
      setActiveId(matches[next]!.id);
      scrollTo(matches[next]!.id);
    } else if (e.key === "Escape") {
      setQuery("");
    }
  };

  const tabStop = activeId && rows.some((r) => r.node.id === activeId) ? activeId : rows[0]?.node.id;

  return (
    <div className={cx("stv-axtree", className)}>
      <div className="stv-axtree__search">
        <input
          type="search"
          placeholder="Search role, name, value or [bid]"
          aria-label="Search accessibility tree"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setMatchCursor(-1);
          }}
          onKeyDown={onSearchKey}
        />
        {query.trim() && (
          <span className="stv-axtree__count" aria-live="polite">
            {matches.length} {matches.length === 1 ? "match" : "matches"}
          </span>
        )}
      </div>
      <div className="stv-axtree__list" role="tree" aria-label="Accessibility tree" ref={listRef}>
        {rows.length === 0 && <div className="stv-empty">{axtree ? "No matching nodes" : "No AXTree for this step"}</div>}
        {rows.map(({ node: n, match }, i) => {
          const hasKids = n.children.length > 0;
          const open = hasKids && isNodeOpen(n);
          const flags = Object.entries(n.props);
          return (
            <div
              key={n.id}
              role="treeitem"
              aria-level={n.depth + 1}
              aria-expanded={hasKids ? open : undefined}
              aria-selected={n.id === activeId}
              tabIndex={n.id === tabStop ? 0 : -1}
              data-node-id={n.id}
              data-bid={n.bid ?? undefined}
              className={cx(
                "stv-axnode",
                n.bid !== null && n.bid === highlightBid && "stv-axnode--highlight",
                n.bid !== null && n.bid === focusedBid && "stv-axnode--focused",
                match && "stv-axnode--match",
                n.id === activeId && "stv-axnode--active",
              )}
              style={{ paddingLeft: `${n.depth * 14 + 4}px` }}
              onClick={() => {
                setActiveId(n.id);
                if (n.bid) onSelectBid?.(n.bid);
              }}
              onMouseEnter={onHoverBid && n.bid ? () => onHoverBid(n.bid) : undefined}
              onMouseLeave={onHoverBid && n.bid ? () => onHoverBid(null) : undefined}
              onKeyDown={(e) => onRowKey(e, n, i)}
            >
              <span
                className={cx("stv-axnode__caret", !hasKids && "stv-axnode__caret--leaf")}
                aria-hidden
                onClick={(e) => {
                  if (!hasKids) return;
                  e.stopPropagation();
                  toggle(n);
                }}
              >
                {hasKids ? (open ? "▾" : "▸") : "·"}
              </span>
              {n.bid !== null && <span className="stv-axnode__bid">[{n.bid}]</span>}
              <span className="stv-axnode__role">{n.role}</span>
              {n.name && <span className="stv-axnode__name">'{n.name}'</span>}
              {n.value !== null && <span className="stv-axnode__value">value='{n.value}'</span>}
              {flags.map(([k, v]) => (
                <span key={k} className="stv-axnode__prop">
                  {v === true ? k : `${k}=${v}`}
                </span>
              ))}
              {n.bid !== null && n.bid === focusedBid && <span className="stv-axnode__badge">focused</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
