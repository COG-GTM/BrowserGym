/**
 * Parser for BrowserGym high-level action strings (Python call syntax), e.g.
 * `click('a42')`, `fill('b12', 'text')`, `scroll(0, 200)`, `select_option('7', ['A', 'B'])`.
 */

export type PyValue = string | number | boolean | null | PyValue[];

export type ActionCategory =
  | "element"
  | "mouse"
  | "keyboard"
  | "navigation"
  | "tab"
  | "message"
  | "wait"
  | "unknown";

export interface ParsedAction {
  raw: string;
  name: string;
  args: PyValue[];
  kwargs: Record<string, PyValue>;
  category: ActionCategory;
  /** Element bids referenced by the action (target first). */
  bids: string[];
  /** Primary target bid, if any. */
  bid: string | null;
  /** Free-text payload (fill value, message, url, key...) for display. */
  text: string | null;
}

export class ActionParseError extends Error {
  constructor(message: string, readonly position: number) {
    super(message);
    this.name = "ActionParseError";
  }
}

interface ActionSpec {
  category: ActionCategory;
  /** Positional names; names ending in `_bid`/`bid` are element ids. */
  params: string[];
  textParam?: string;
}

const SPECS: Record<string, ActionSpec> = {
  click: { category: "element", params: ["bid", "button", "modifiers"] },
  dblclick: { category: "element", params: ["bid", "button", "modifiers"] },
  hover: { category: "element", params: ["bid"] },
  fill: { category: "element", params: ["bid", "value", "enable_autocomplete_menu"], textParam: "value" },
  select_option: { category: "element", params: ["bid", "options"], textParam: "options" },
  check: { category: "element", params: ["bid"] },
  uncheck: { category: "element", params: ["bid"] },
  clear: { category: "element", params: ["bid"] },
  focus: { category: "element", params: ["bid"] },
  press: { category: "element", params: ["bid", "key_comb"], textParam: "key_comb" },
  upload_file: { category: "element", params: ["bid", "file"], textParam: "file" },
  drag_and_drop: { category: "element", params: ["from_bid", "to_bid"] },
  mouse_move: { category: "mouse", params: ["x", "y"] },
  mouse_up: { category: "mouse", params: ["x", "y", "button"] },
  mouse_down: { category: "mouse", params: ["x", "y", "button"] },
  mouse_click: { category: "mouse", params: ["x", "y", "button"] },
  mouse_dblclick: { category: "mouse", params: ["x", "y", "button"] },
  mouse_drag_and_drop: { category: "mouse", params: ["from_x", "from_y", "to_x", "to_y"] },
  mouse_upload_file: { category: "mouse", params: ["x", "y", "file"], textParam: "file" },
  scroll: { category: "mouse", params: ["delta_x", "delta_y"] },
  scroll_at: { category: "mouse", params: ["x", "y", "dx", "dy"] },
  keyboard_press: { category: "keyboard", params: ["key"], textParam: "key" },
  keyboard_up: { category: "keyboard", params: ["key"], textParam: "key" },
  keyboard_down: { category: "keyboard", params: ["key"], textParam: "key" },
  keyboard_type: { category: "keyboard", params: ["text"], textParam: "text" },
  keyboard_insert_text: { category: "keyboard", params: ["text"], textParam: "text" },
  goto: { category: "navigation", params: ["url"], textParam: "url" },
  go_back: { category: "navigation", params: [] },
  go_forward: { category: "navigation", params: [] },
  new_tab: { category: "tab", params: [] },
  tab_close: { category: "tab", params: [] },
  tab_focus: { category: "tab", params: ["index"] },
  send_msg_to_user: { category: "message", params: ["text"], textParam: "text" },
  report_infeasible: { category: "message", params: ["reason"], textParam: "reason" },
  noop: { category: "wait", params: ["wait_ms"] },
};

export const KNOWN_ACTIONS: readonly string[] = Object.keys(SPECS);

class Lexer {
  pos = 0;
  constructor(readonly src: string) {}

  ws(): void {
    while (this.pos < this.src.length && /\s/.test(this.src[this.pos]!)) this.pos++;
  }
  peek(): string | undefined {
    this.ws();
    return this.src[this.pos];
  }
  expect(ch: string): void {
    if (this.peek() !== ch) throw new ActionParseError(`Expected '${ch}'`, this.pos);
    this.pos++;
  }
  eof(): boolean {
    this.ws();
    return this.pos >= this.src.length;
  }
  identifier(): string {
    this.ws();
    const m = /^[A-Za-z_][A-Za-z0-9_]*/.exec(this.src.slice(this.pos));
    if (!m) throw new ActionParseError("Expected identifier", this.pos);
    this.pos += m[0].length;
    return m[0];
  }

  string(): string {
    const start = this.pos;
    let prefixEnd = this.pos;
    while (/[rRbBuUfF]/.test(this.src[prefixEnd] ?? "")) prefixEnd++;
    const isRaw = /[rR]/.test(this.src.slice(this.pos, prefixEnd));
    this.pos = prefixEnd;
    const q = this.src[this.pos];
    if (q !== "'" && q !== '"') throw new ActionParseError("Expected string", start);
    const triple = this.src.startsWith(q.repeat(3), this.pos);
    const delim = triple ? q.repeat(3) : q;
    this.pos += delim.length;
    let out = "";
    while (true) {
      if (this.pos >= this.src.length) throw new ActionParseError("Unterminated string", start);
      if (this.src.startsWith(delim, this.pos)) {
        this.pos += delim.length;
        return out;
      }
      const ch = this.src[this.pos]!;
      if (ch === "\\" && !isRaw) {
        const nx = this.src[this.pos + 1] ?? "";
        const map: Record<string, string> = { n: "\n", t: "\t", r: "\r", "\\": "\\", "'": "'", '"': '"', "0": "\0" };
        if (nx === "u" || nx === "x") {
          const len = nx === "u" ? 4 : 2;
          const hex = this.src.slice(this.pos + 2, this.pos + 2 + len);
          out += String.fromCharCode(parseInt(hex, 16));
          this.pos += 2 + len;
        } else {
          out += map[nx] ?? `\\${nx}`;
          this.pos += 2;
        }
        continue;
      }
      if (!triple && ch === "\n") throw new ActionParseError("Unterminated string", start);
      out += ch;
      this.pos++;
    }
  }

  value(): PyValue {
    const ch = this.peek();
    if (ch === undefined) throw new ActionParseError("Unexpected end of input", this.pos);
    if (ch === "[" || ch === "(") {
      const close = ch === "[" ? "]" : ")";
      this.pos++;
      const items: PyValue[] = [];
      while (this.peek() !== close) {
        items.push(this.value());
        if (this.peek() === ",") this.pos++;
        else break;
      }
      this.expect(close);
      return items;
    }
    if (ch === "'" || ch === '"' || /^[rRbBuUfF]{1,2}['"]/.test(this.src.slice(this.pos, this.pos + 3))) {
      let s = this.string();
      // implicit concatenation: 'a' 'b'
      while (this.peek() === "'" || this.peek() === '"') s += this.string();
      return s;
    }
    const num = /^[-+]?(\d+\.?\d*(e[-+]?\d+)?|\.\d+(e[-+]?\d+)?)/i.exec(this.src.slice(this.pos));
    if (num) {
      this.pos += num[0].length;
      return Number(num[0]);
    }
    const id = this.identifier();
    if (id === "True") return true;
    if (id === "False") return false;
    if (id === "None") return null;
    throw new ActionParseError(`Unsupported value '${id}'`, this.pos - id.length);
  }
}

function asText(v: PyValue | undefined): string | null {
  if (v === undefined || v === null) return null;
  if (Array.isArray(v)) return v.map((x) => asText(x) ?? "").join(", ");
  return String(v);
}

function parseCall(lx: Lexer): ParsedAction {
  const start = lx.pos;
  const name = lx.identifier();
  lx.expect("(");
  const args: PyValue[] = [];
  const kwargs: Record<string, PyValue> = {};
  while (lx.peek() !== ")") {
    const save = lx.pos;
    const kw = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)/.exec(lx.src.slice(lx.pos));
    if (kw) {
      lx.pos += kw[0].length;
      kwargs[kw[1]!] = lx.value();
    } else {
      if (Object.keys(kwargs).length) throw new ActionParseError("Positional argument after keyword argument", save);
      args.push(lx.value());
    }
    if (lx.peek() === ",") lx.pos++;
    else break;
  }
  lx.expect(")");
  const raw = lx.src.slice(start, lx.pos).trim();

  const spec = SPECS[name];
  const named: Record<string, PyValue> = { ...kwargs };
  spec?.params.forEach((p, i) => {
    if (i < args.length && !(p in named)) named[p] = args[i]!;
  });
  const bids = spec
    ? spec.params.filter((p) => p === "bid" || p.endsWith("_bid")).map((p) => named[p]).filter((v): v is string | number => typeof v === "string" || typeof v === "number").map(String)
    : [];
  let text = spec?.textParam ? asText(named[spec.textParam]) : null;
  if (spec && !spec.textParam && spec.category === "mouse" && args.length) text = args.map((a) => asText(a)).join(", ");
  if (name === "noop" && named.wait_ms !== undefined) text = `${asText(named.wait_ms)} ms`;
  if (name === "tab_focus") text = asText(named.index);

  return {
    raw,
    name,
    args,
    kwargs,
    category: spec?.category ?? "unknown",
    bids,
    bid: bids[0] ?? null,
    text,
  };
}

/**
 * Parse an action string that may contain several calls (one per line or `;`-separated),
 * as produced by BrowserGym's multi-action mode. Comments (`# ...`) are ignored.
 */
export function parseActions(source: string): ParsedAction[] {
  const lx = new Lexer(stripComments(source));
  const out: ParsedAction[] = [];
  while (!lx.eof()) {
    out.push(parseCall(lx));
    while (lx.peek() === ";") lx.pos++;
  }
  return out;
}

/** Remove `# ...` comments, tracking single/triple-quoted strings across lines. */
function stripComments(source: string): string {
  let out = "";
  let quote: string | null = null;
  for (let i = 0; i < source.length; i++) {
    const ch = source[i]!;
    if (quote) {
      if (ch === "\\") {
        out += source.slice(i, i + 2);
        i++;
        continue;
      }
      if (source.startsWith(quote, i)) {
        out += quote;
        i += quote.length - 1;
        quote = null;
        continue;
      }
      if (ch === "\n" && quote.length === 1) quote = null;
      out += ch;
    } else if (ch === "'" || ch === '"') {
      quote = source.startsWith(ch.repeat(3), i) ? ch.repeat(3) : ch;
      out += quote;
      i += quote.length - 1;
    } else if (ch === "#") {
      while (i + 1 < source.length && source[i + 1] !== "\n") i++;
    } else out += ch;
  }
  return out;
}

/** Parse a single action. Throws {@link ActionParseError} on malformed input. */
export function parseAction(source: string): ParsedAction {
  const all = parseActions(source);
  if (all.length === 0) throw new ActionParseError("Empty action", 0);
  return all[0]!;
}

/** Like {@link parseAction} but returns `null` instead of throwing. */
export function tryParseAction(source: string | null | undefined): ParsedAction | null {
  if (!source) return null;
  try {
    return parseAction(source);
  } catch {
    return null;
  }
}

/** Like {@link parseActions} but returns `null` instead of throwing (and for empty input). */
export function tryParseActions(source: string | null | undefined): ParsedAction[] | null {
  if (!source) return null;
  try {
    const all = parseActions(source);
    return all.length ? all : null;
  } catch {
    return null;
  }
}
