import type {
  AgentConfig,
  AgentInfo,
  ChatMessage,
  Run,
  RunStatus,
  StepDetail,
  Task,
} from "../api/types";

/* ------------------------------------------------------------------ */
/* deterministic randomness                                            */
/* ------------------------------------------------------------------ */

export function hashString(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export function rng(seed: number | string) {
  let a = typeof seed === "string" ? hashString(seed) : seed >>> 0;
  const next = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  return {
    next,
    int: (min: number, max: number) => Math.floor(next() * (max - min + 1)) + min,
    pick: <T,>(items: readonly T[]): T => items[Math.floor(next() * items.length)],
  };
}

/* ------------------------------------------------------------------ */
/* catalog                                                             */
/* ------------------------------------------------------------------ */

const miniwob = (slug: string, title: string, description: string): Task => ({
  id: `browsergym/miniwob.${slug}`,
  benchmark: "miniwob",
  title,
  description,
  requires_setup: false,
});

export const TASKS: Task[] = [
  {
    id: "browsergym/openended",
    benchmark: "openended",
    title: "Open-ended task",
    description: "Give the agent any goal and a start URL; it browses until it decides it is done.",
    requires_setup: false,
  },
  miniwob("click-test", "Click test", "Click the button labelled “Click Me!”."),
  miniwob("click-button", "Click button", "Click the button with the requested text."),
  miniwob("click-checkboxes", "Click checkboxes", "Select the requested checkboxes and submit."),
  miniwob("click-dialog", "Click dialog", "Close the dialog box by clicking the right button."),
  miniwob("click-link", "Click link", "Click on the link containing the specified text."),
  miniwob("click-tab", "Click tab", "Switch to the tab that contains the requested link."),
  miniwob("enter-text", "Enter text", "Type the given text into the textbox and press submit."),
  miniwob("enter-password", "Enter password", "Enter the password twice and submit."),
  miniwob("login-user", "Login user", "Log in with the provided username and password."),
  miniwob("choose-date", "Choose date", "Pick the requested date from a datepicker."),
  miniwob("book-flight", "Book flight", "Search for and book the cheapest flight matching the request."),
  miniwob("email-inbox", "Email inbox", "Perform the requested action on an email in the inbox."),
  miniwob("social-media", "Social media", "Interact with a post in a social-media feed."),
  miniwob("search-engine", "Search engine", "Search for a term and click the n-th result."),
  miniwob("use-autocomplete", "Use autocomplete", "Pick an option from an autocomplete widget."),
  {
    id: "browsergym/webarena.4",
    benchmark: "webarena",
    title: "WebArena #4 — top-selling products (shopping admin)",
    description: "What are the top-3 best-selling products in Jan 2023?",
    requires_setup: true,
  },
  {
    id: "browsergym/webarena.27",
    benchmark: "webarena",
    title: "WebArena #27 — Reddit comments",
    description: "Tell me the count of comments that have received more downvotes than upvotes for the user who made the latest post on the Showerthoughts forum.",
    requires_setup: true,
  },
  {
    id: "browsergym/webarena.310",
    benchmark: "webarena",
    title: "WebArena #310 — GitLab contributors",
    description: "Tell me who has made the most contributions, in terms of number of commits, to the thoughtbot/administrate project.",
    requires_setup: true,
  },
  {
    id: "browsergym/visualwebarena.12",
    benchmark: "visualwebarena",
    title: "VisualWebArena #12 — classifieds",
    description: "Find the most recently listed blue bicycle and add it to watchlist.",
    requires_setup: true,
  },
  {
    id: "browsergym/workarena.servicenow.order-standard-laptop",
    benchmark: "workarena",
    title: "WorkArena — order a standard laptop",
    description: "Order a standard laptop from the ServiceNow service catalog.",
    requires_setup: true,
  },
  {
    id: "browsergym/workarena.servicenow.create-incident",
    benchmark: "workarena",
    title: "WorkArena — create an incident",
    description: "Create a new incident record with the given fields.",
    requires_setup: true,
  },
  {
    id: "browsergym/workarena.servicenow.filter-change-request-list",
    benchmark: "workarena",
    title: "WorkArena — filter change requests",
    description: "Filter the change request list using the requested conditions.",
    requires_setup: true,
  },
  {
    id: "browsergym/assistantbench.validation.3",
    benchmark: "assistantbench",
    title: "AssistantBench — validation #3",
    description: "Which gyms near Tompkins Square Park offer classes before 7am?",
    requires_setup: false,
  },
  {
    id: "browsergym/weblinx.apfyesq.6",
    benchmark: "weblinx",
    title: "WebLINX — apfyesq turn 6",
    description: "Replay a recorded conversational browsing turn.",
    requires_setup: false,
  },
];

export const AGENTS: AgentInfo[] = [
  { type: "mock", title: "Mock agent (offline, deterministic)", models: [] },
  { type: "scripted", title: "Scripted replay", models: [] },
  { type: "openai", title: "OpenAI", models: ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o4-mini"] },
  {
    type: "anthropic",
    title: "Anthropic",
    models: ["claude-sonnet-4-5", "claude-3-7-sonnet-latest", "claude-3-5-haiku-latest"],
  },
];

export function findTask(id: string): Task | undefined {
  return TASKS.find((t) => t.id === id);
}

/* ------------------------------------------------------------------ */
/* episode scripts                                                     */
/* ------------------------------------------------------------------ */

export interface PageElement {
  bid: string;
  role: string;
  name: string;
  value?: string;
}

export interface Frame {
  url: string;
  title: string;
  heading: string;
  elements: PageElement[];
  action: string;
  thought: string;
  target?: string;
}

interface SiteProfile {
  url: string;
  title: string;
  search: string;
  query: string;
  result: string;
  detail: string;
  answer: string;
}

function siteFor(task: Task, goal: string | null | undefined, startUrl?: string | null): SiteProfile {
  switch (task.benchmark) {
    case "webarena":
      return {
        url: "http://shopping-admin.local:7780/admin",
        title: "Dashboard / Magento Admin",
        search: "Search by keyword",
        query: "bestsellers january 2023",
        result: "Reports › Products › Bestsellers",
        detail: "Period: Month — 2023-01",
        answer: "Quest Lumaflex™ Band, Sprite Yoga Strap 6 foot, Overnight Duffle",
      };
    case "visualwebarena":
      return {
        url: "http://classifieds.local:9980/",
        title: "Classifieds",
        search: "Search listings",
        query: "blue bicycle",
        result: "Blue Schwinn road bike — $180",
        detail: "Add to watchlist",
        answer: "Added the blue Schwinn road bike to the watchlist.",
      };
    case "workarena":
      return {
        url: "https://dev12345.service-now.com/now/nav/ui/home",
        title: "ServiceNow — Service Catalog",
        search: "Search catalog",
        query: "standard laptop",
        result: "Standard Laptop",
        detail: "Order Now",
        answer: "Request REQ0010042 submitted for a Standard Laptop.",
      };
    case "openended":
      return {
        url: startUrl || "https://github.com/ServiceNow/BrowserGym",
        title: "ServiceNow/BrowserGym · GitHub",
        search: "Search or jump to…",
        query: "releases",
        result: "Releases",
        detail: "Latest",
        answer: goal ? `Done: ${goal.replace(/\.$/, "")}. The latest release is v0.14.0.` : "Done.",
      };
    default:
      return {
        url: "https://www.google.com/",
        title: "Search",
        search: "Search",
        query: goal ?? task.title,
        result: "Top result",
        detail: "Details",
        answer: "Here is what I found.",
      };
  }
}

function miniwobFrames(task: Task): Frame[] {
  const slug = task.id.split(".").slice(1).join(".");
  const url = `http://localhost:8000/miniwob/${slug}.html`;
  const instruction = task.description ?? task.title;
  const base: PageElement[] = [
    { bid: "12", role: "heading", name: instruction },
    { bid: "14", role: "textbox", name: "Answer" },
    { bid: "15", role: "button", name: "Click Me!" },
    { bid: "16", role: "button", name: "Submit" },
  ];
  const page = { url, title: `${task.title} Task`, heading: instruction };
  return [
    {
      ...page,
      elements: base,
      action: "noop()",
      thought: `The instruction reads: “${instruction}”. Let me inspect the page before acting.`,
    },
    {
      ...page,
      elements: base,
      action: "click('15')",
      target: "15",
      thought: "Button [15] matches the instruction; clicking it.",
    },
    {
      ...page,
      elements: base.map((e) => (e.bid === "14" ? { ...e, value: "BrowserGym" } : e)),
      action: "fill('14', 'BrowserGym')",
      target: "14",
      thought: "The textbox [14] needs a value before submitting.",
    },
    {
      ...page,
      elements: base,
      action: "click('16')",
      target: "16",
      thought: "Everything looks filled in. Submitting with [16].",
    },
  ];
}

function siteFrames(site: SiteProfile): Frame[] {
  const home: PageElement[] = [
    { bid: "21", role: "link", name: "Home" },
    { bid: "42", role: "searchbox", name: site.search },
    { bid: "57", role: "button", name: "Search" },
    { bid: "118", role: "link", name: site.result },
  ];
  const detail: PageElement[] = [
    { bid: "21", role: "link", name: "Home" },
    { bid: "160", role: "heading", name: site.result },
    { bid: "203", role: "link", name: site.detail },
    { bid: "240", role: "button", name: "Back" },
  ];
  return [
    {
      url: site.url,
      title: site.title,
      heading: site.title,
      elements: home,
      action: `goto('${site.url}')`,
      thought: "Start by opening the start page.",
    },
    {
      url: site.url,
      title: site.title,
      heading: site.title,
      elements: home.map((e) => (e.bid === "42" ? { ...e, value: site.query } : e)),
      action: `fill('42', '${site.query.replace(/'/g, "\\'")}')`,
      target: "42",
      thought: `The search box [42] is visible. Typing “${site.query}”.`,
    },
    {
      url: site.url,
      title: site.title,
      heading: site.title,
      elements: home,
      action: "press('42', 'Enter')",
      target: "42",
      thought: "Submit the search.",
    },
    {
      url: `${site.url.replace(/\/$/, "")}/search?q=${encodeURIComponent(site.query)}`,
      title: `${site.query} — ${site.title}`,
      heading: `Results for “${site.query}”`,
      elements: home,
      action: "click('118')",
      target: "118",
      thought: `“${site.result}” [118] looks like the right result.`,
    },
    {
      url: `${site.url.replace(/\/$/, "")}/item/118`,
      title: site.result,
      heading: site.result,
      elements: detail,
      action: "scroll(0, 600)",
      thought: "Scroll down to find the relevant section.",
    },
    {
      url: `${site.url.replace(/\/$/, "")}/item/118`,
      title: site.result,
      heading: site.result,
      elements: detail,
      action: "click('203')",
      target: "203",
      thought: `Open “${site.detail}” [203].`,
    },
  ];
}

export interface EpisodeScript {
  frames: Frame[];
  answer: string;
}

export function episodeScript(task: Task, goal?: string | null, startUrl?: string | null): EpisodeScript {
  if (task.benchmark === "miniwob") {
    return { frames: miniwobFrames(task), answer: "Task completed." };
  }
  const site = siteFor(task, goal, startUrl);
  return { frames: siteFrames(site), answer: site.answer };
}

export function frameAt(script: EpisodeScript, index: number, isFinal: boolean): Frame {
  const base = script.frames[Math.min(index, script.frames.length - 1)];
  if (isFinal) {
    return {
      ...base,
      action: `send_msg_to_user('${script.answer.replace(/'/g, "\\'")}')`,
      target: undefined,
      thought: "I have what I need. Reporting back to the user.",
    };
  }
  if (index >= script.frames.length) {
    return { ...base, action: index % 2 ? "scroll(0, 400)" : "noop()", target: undefined, thought: "Waiting for the page to settle." };
  }
  return base;
}

export function axtreeFor(frame: Frame, focused?: string): string {
  const lines = [`RootWebArea '${frame.title}', focused`, `\t[9] main ''`, `\t\t[10] heading '${frame.heading}'`];
  for (const el of frame.elements) {
    const props = ["clickable"];
    if (el.bid === focused) props.push("focused");
    const value = el.value ? ` value='${el.value}'` : "";
    lines.push(`\t\t[${el.bid}] ${el.role} '${el.name}'${value}, ${props.join(", ")}`);
  }
  lines.push(`\t\t[300] contentinfo ''`, `\t\t\tStaticText 'Rendered by Side mock mode'`);
  return lines.join("\n");
}

const TAG: Record<string, string> = {
  button: "button",
  link: "a",
  textbox: "input",
  searchbox: "input",
  heading: "h2",
};

export function prunedHtmlFor(frame: Frame): string {
  const body = frame.elements
    .map((el) => {
      const tag = TAG[el.role] ?? "div";
      if (tag === "input") return `    <input bid="${el.bid}" aria-label="${el.name}" value="${el.value ?? ""}">`;
      return `    <${tag} bid="${el.bid}">${el.name}</${tag}>`;
    })
    .join("\n");
  return `<html>\n<body>\n  <main bid="9">\n    <h1 bid="10">${frame.heading}</h1>\n${body}\n  </main>\n</body>\n</html>`;
}

/* ------------------------------------------------------------------ */
/* screenshots                                                         */
/* ------------------------------------------------------------------ */

function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

function clip(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

export function screenshotSvg(frame: Frame, index: number): string {
  const W = 1280;
  const H = 800;
  const rows = frame.elements
    .map((el, i) => {
      const y = 250 + i * 110;
      const isTarget = el.bid === frame.target;
      const isButton = el.role === "button";
      const isInput = el.role === "textbox" || el.role === "searchbox";
      const fill = isButton ? "#6d28d9" : isInput ? "#ffffff" : "#f4f4f5";
      const color = isButton ? "#ffffff" : "#18181b";
      const w = isButton ? 260 : 720;
      const label = isInput ? el.value || el.name : el.name;
      const labelColor = isInput && !el.value ? "#a1a1aa" : color;
      return `
  <g>
    <rect x="96" y="${y}" width="${w}" height="64" rx="12" fill="${fill}" stroke="${isTarget ? "#f43f5e" : "#d4d4d8"}" stroke-width="${isTarget ? 5 : 2}"/>
    <text x="${96 + 24}" y="${y + 41}" font-size="24" fill="${labelColor}" font-family="ui-sans-serif,system-ui">${esc(clip(label, 52))}</text>
    <text x="${96 + w + 16}" y="${y + 40}" font-size="18" fill="#a1a1aa" font-family="ui-monospace,monospace">[${el.bid}]</text>
    ${isTarget ? `<circle cx="${96 + w - 40}" cy="${y + 32}" r="18" fill="#f43f5e" fill-opacity="0.35" stroke="#f43f5e" stroke-width="3"/>` : ""}
  </g>`;
    })
    .join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">
  <rect width="${W}" height="${H}" fill="#fafafa"/>
  <rect width="${W}" height="72" fill="#e4e4e7"/>
  <circle cx="32" cy="36" r="9" fill="#f87171"/><circle cx="60" cy="36" r="9" fill="#fbbf24"/><circle cx="88" cy="36" r="9" fill="#34d399"/>
  <rect x="124" y="16" width="${W - 260}" height="40" rx="20" fill="#ffffff"/>
  <text x="148" y="43" font-size="20" fill="#52525b" font-family="ui-monospace,monospace">${esc(clip(frame.url, 90))}</text>
  <rect x="${W - 116}" y="18" width="92" height="36" rx="18" fill="#6d28d9"/>
  <text x="${W - 70}" y="43" font-size="18" fill="#fff" text-anchor="middle" font-family="ui-sans-serif,system-ui">step ${index}</text>
  <text x="96" y="160" font-size="40" font-weight="700" fill="#18181b" font-family="ui-sans-serif,system-ui">${esc(clip(frame.heading, 48))}</text>
  <text x="96" y="204" font-size="22" fill="#71717a" font-family="ui-sans-serif,system-ui">${esc(clip(frame.title, 80))}</text>
  ${rows}
</svg>`;
}

export function svgDataUri(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

/* ------------------------------------------------------------------ */
/* seeded history                                                      */
/* ------------------------------------------------------------------ */

export interface MockStep extends StepDetail {
  _frame: Frame;
}

export function buildStep(
  run: Pick<Run, "id" | "task_id" | "goal" | "status">,
  script: EpisodeScript,
  index: number,
  opts: { isFinal: boolean; startedAt: number; outcome: RunStatus; error?: string },
): MockStep {
  const r = rng(`${run.id}:${index}`);
  const frame = frameAt(script, index, opts.isFinal);
  const success = opts.isFinal && opts.outcome === "succeeded";
  const failedLast = opts.isFinal && opts.outcome === "failed";
  const elapsed = r.int(700, 3800);
  return {
    index,
    action: frame.action,
    thought: frame.thought,
    url: frame.url,
    reward: success ? 1 : 0,
    terminated: success,
    truncated: failedLast && !opts.error,
    last_action_error: failedLast && opts.error ? opts.error : null,
    screenshot_url: `/runs/${run.id}/steps/${index}/screenshot`,
    elapsed_ms: elapsed,
    timestamp: new Date(opts.startedAt + (index + 1) * 2600 + elapsed).toISOString(),
    axtree_txt: axtreeFor(frame, frame.target),
    pruned_html: prunedHtmlFor(frame),
    focused_element_bid: frame.target ?? null,
    _frame: frame,
  };
}

export const SEED_GOALS = [
  "Find the latest BrowserGym release on GitHub and report its version.",
  "Open the BrowserGym docs and summarize the action space in one sentence.",
  "Look up the MiniWoB++ paper and tell me who the first author is.",
  "Check whether the WorkArena repo has an open issue about login timeouts.",
];

const FAILURE_ERRORS = [
  "TimeoutError: Locator.click: Timeout 500ms exceeded. waiting for get_by_test_id(\"203\")",
  "ValueError: Could not find element with bid \"118\"",
  null,
];

export interface SeedRun {
  run: Run;
  steps: MockStep[];
  chat: ChatMessage[];
}

function agentFor(r: ReturnType<typeof rng>): AgentConfig {
  const type = r.pick(["mock", "mock", "openai", "anthropic", "scripted"] as const);
  const model =
    type === "openai" ? r.pick(["gpt-4o", "gpt-4o-mini", "gpt-4.1"]) : type === "anthropic" ? r.pick(["claude-sonnet-4-5", "claude-3-7-sonnet-latest"]) : null;
  return { type, model, use_screenshot: type === "openai" || type === "anthropic", use_axtree: true };
}

export function seedHistory(now: number, count = 42): SeedRun[] {
  const r = rng("side-seed");
  const out: SeedRun[] = [];
  const runnable = TASKS.filter((t) => t.benchmark !== "weblinx");
  for (let i = 0; i < count; i++) {
    const task = r.pick(runnable);
    const goal = task.id === "browsergym/openended" ? r.pick(SEED_GOALS) : task.description ?? null;
    const roll = r.next();
    const status: RunStatus = roll < 0.62 ? "succeeded" : roll < 0.86 ? "failed" : "cancelled";
    const created = now - (i + 1) * r.int(25, 160) * 60_000 - 5 * 60_000;
    const started = created + r.int(500, 4000);
    const maxSteps = r.pick([10, 15, 15, 20, 30]);
    const nSteps = status === "failed" && r.next() < 0.3 ? maxSteps : r.int(3, 9);
    const error = status === "failed" ? r.pick(FAILURE_ERRORS) : null;
    // Derived only from the seeded RNG so ids survive page reloads (deep links work in mock mode).
    const id = `run_${r.int(36 ** 5, 36 ** 6 - 1).toString(36)}${i.toString(36).padStart(2, "0")}`;
    const base: Run = {
      id,
      task_id: task.id,
      goal,
      agent: agentFor(r),
      status,
      reward: status === "succeeded" ? 1 : 0,
      n_steps: nSteps,
      max_steps: maxSteps,
      created_at: new Date(created).toISOString(),
      started_at: new Date(started).toISOString(),
      finished_at: null,
      error: status === "failed" ? (error ?? `Episode truncated after ${nSteps} steps without completing the task.`) : null,
    };
    const script = episodeScript(task, goal);
    const steps = Array.from({ length: nSteps }, (_, idx) =>
      buildStep(base, script, idx, {
        isFinal: idx === nSteps - 1,
        startedAt: started,
        outcome: status,
        error: error ?? undefined,
      }),
    );
    const finished = Date.parse(steps[steps.length - 1].timestamp) + 400;
    base.finished_at = new Date(finished).toISOString();
    const chat: ChatMessage[] = [
      { role: "info", message: `Goal: ${goal ?? task.title}`, timestamp: base.started_at! },
    ];
    if (status === "succeeded") chat.push({ role: "assistant", message: script.answer, timestamp: base.finished_at });
    if (status === "failed") chat.push({ role: "info", message: base.error!, timestamp: base.finished_at });
    if (status === "cancelled") chat.push({ role: "info", message: "Run cancelled by user.", timestamp: base.finished_at });
    out.push({ run: base, steps, chat });
  }
  return out;
}
