/**
 * Parser for BrowserGym's flattened accessibility tree (`flatten_axtree_to_str`), e.g.
 *
 *   RootWebArea 'Skyhop', focused
 *   \t[12] main ''
 *   \t\t[15] textbox 'From' value='Paris', focused
 */

export interface AXNode {
  /** Stable id unique within the tree (line number based). */
  id: string;
  bid: string | null;
  role: string;
  name: string;
  value: string | null;
  /** Remaining properties; flags without a value (e.g. `focused`) map to `true`. */
  props: Record<string, string | true>;
  depth: number;
  line: number;
  children: AXNode[];
  parent: AXNode | null;
}

export interface AXTree {
  roots: AXNode[];
  /** All nodes in document order. */
  nodes: AXNode[];
  /** bid -> nodes carrying that bid (bids may repeat, e.g. date sub-fields). */
  byBid: Map<string, AXNode[]>;
}

const LINE_RE = /^(\t*| *)(?:\[([^\]]+)\]\s+)?(\S+)(.*)$/;

function readQuoted(s: string, i: number): [string, number] | null {
  const q = s[i];
  if (q !== "'" && q !== '"') return null;
  let out = "";
  let j = i + 1;
  while (j < s.length) {
    const ch = s[j]!;
    if (ch === "\\" && j + 1 < s.length) {
      const nx = s[j + 1]!;
      out += nx === "n" ? "\n" : nx === "t" ? "\t" : nx;
      j += 2;
      continue;
    }
    if (ch === q) return [out, j + 1];
    out += ch;
    j++;
  }
  return null;
}

/** Split `a=1, b='x, y', focused` on top-level commas. */
function splitProps(s: string): string[] {
  const parts: string[] = [];
  let cur = "";
  let quote: string | null = null;
  for (let i = 0; i < s.length; i++) {
    const ch = s[i]!;
    if (quote) {
      cur += ch;
      if (ch === "\\" && i + 1 < s.length) cur += s[++i];
      else if (ch === quote) quote = null;
    } else if (ch === "'" || ch === '"') {
      quote = ch;
      cur += ch;
    } else if (ch === ",") {
      if (cur.trim()) parts.push(cur.trim());
      cur = "";
    } else cur += ch;
  }
  if (cur.trim()) parts.push(cur.trim());
  return parts;
}

function unquote(v: string): string {
  const r = readQuoted(v, 0);
  return r && r[1] === v.length ? r[0] : v;
}

export function parseAXTreeLine(line: string, lineNo = 0): Omit<AXNode, "children" | "parent"> | null {
  if (!line.trim()) return null;
  const m = LINE_RE.exec(line);
  if (!m) return null;
  const indent = m[1]!;
  const depth = indent.startsWith(" ") ? Math.floor(indent.length / 2) : indent.length;
  let rest = m[4]!.trimStart();
  let name = "";
  const quoted = readQuoted(rest, 0);
  if (quoted) {
    name = quoted[0];
    rest = rest.slice(quoted[1]);
  }
  const props: Record<string, string | true> = {};
  let value: string | null = null;
  for (const part of splitProps(rest)) {
    const eq = part.indexOf("=");
    if (eq === -1) {
      props[part] = true;
      continue;
    }
    const key = part.slice(0, eq).trim();
    const val = unquote(part.slice(eq + 1).trim());
    if (key === "value" && value === null) value = val;
    else props[key] = val;
  }
  return { id: `n${lineNo}`, bid: m[2] ?? null, role: m[3]!, name, value, props, depth, line: lineNo };
}

export function parseAXTree(text: string | null | undefined): AXTree {
  const roots: AXNode[] = [];
  const nodes: AXNode[] = [];
  const byBid = new Map<string, AXNode[]>();
  if (!text) return { roots, nodes, byBid };
  const stack: AXNode[] = [];
  text.split("\n").forEach((line, i) => {
    const parsed = parseAXTreeLine(line, i);
    if (!parsed) return;
    while (stack.length && stack[stack.length - 1]!.depth >= parsed.depth) stack.pop();
    const parent = stack[stack.length - 1] ?? null;
    const node: AXNode = { ...parsed, children: [], parent };
    (parent ? parent.children : roots).push(node);
    nodes.push(node);
    if (node.bid) {
      const list = byBid.get(node.bid);
      if (list) list.push(node);
      else byBid.set(node.bid, [node]);
    }
    stack.push(node);
  });
  return { roots, nodes, byBid };
}

export function ancestorsOf(node: AXNode): AXNode[] {
  const out: AXNode[] = [];
  for (let p = node.parent; p; p = p.parent) out.push(p);
  return out;
}

/** Case-insensitive match against bid, role, name and value. */
export function nodeMatches(node: AXNode, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return false;
  if (q.startsWith("[") && q.endsWith("]")) return node.bid === q.slice(1, -1);
  return (
    node.bid === q ||
    node.role.toLowerCase().includes(q) ||
    node.name.toLowerCase().includes(q) ||
    (node.value ?? "").toLowerCase().includes(q)
  );
}
