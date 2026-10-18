// Minimal reference implementation of the Side web data-testid contract (see e2e/README.md).
// Lets the `web` Playwright project run today; apps/web is the real product.
const TERMINAL = ["succeeded", "failed", "cancelled"];
const STATUSES = ["queued", "running", ...TERMINAL];
const app = document.getElementById("app");
const state = { tasks: [], agents: [], runs: [], live: {} };

const h = (tag, attrs = {}, ...children) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) el.setAttribute(k, v === true ? "" : v);
  }
  el.append(...children.flat().filter((c) => c !== null && c !== undefined));
  return el;
};
const badge = (status, testid) => h("span", { class: "badge", "data-status": status, "data-testid": testid }, status);

async function boot() {
  const [tasks, agents, runs] = await Promise.all(["tasks", "agents", "runs"].map((f) => fetch(`/fixtures/${f}.json`).then((r) => r.json())));
  Object.assign(state, { tasks, agents, runs });
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[href^='/']");
    if (a) { e.preventDefault(); navigate(a.getAttribute("href")); }
  });
  window.addEventListener("popstate", render);
  render();
}

function navigate(path) { history.pushState({}, "", path); render(); }

function render() {
  for (const live of Object.values(state.live)) live.detach?.();
  const path = location.pathname;
  app.replaceChildren();
  if (path === "/tasks") return renderTasks();
  if (path === "/runs/new") return renderNewRun();
  const m = path.match(/^\/runs\/([^/]+)$/);
  if (m) return renderRun(decodeURIComponent(m[1]));
  return renderRuns();
}

function renderRuns() {
  const params = new URLSearchParams(location.search);
  const filter = h("select", { "data-testid": "runs-status-filter", onchange: (e) => {
    const q = e.target.value ? `?status=${e.target.value}` : "";
    history.replaceState({}, "", `/runs${q}`); renderRuns();
  } }, h("option", { value: "" }, "All statuses"), STATUSES.map((s) => h("option", { value: s }, s)));
  filter.value = params.get("status") ?? "";
  const rows = state.runs.filter((r) => !filter.value || r.status === filter.value);
  app.replaceChildren(
    h("h1", {}, "Runs"),
    h("label", {}, "Status", filter),
    rows.length
      ? h("table", { "data-testid": "runs-list" }, h("tr", {}, h("th", {}, "Run"), h("th", {}, "Task"), h("th", {}, "Status"), h("th", {}, "Steps")),
          rows.map((r) => h("tr", { "data-testid": "run-row", "data-run-id": r.id, "data-status": r.status, onclick: () => navigate(`/runs/${r.id}`) },
            h("td", {}, r.id), h("td", {}, r.task_id), h("td", {}, badge(r.status, "run-row-status")), h("td", {}, String(r.n_steps)))))
      : h("p", { "data-testid": "runs-empty" }, "No runs match this filter."),
  );
}

function renderTasks() {
  const list = h("table", {});
  const empty = h("p", { "data-testid": "tasks-empty", hidden: true }, "No tasks match your search.");
  const search = h("input", { "data-testid": "tasks-search-input", placeholder: "Search tasks", oninput: draw });
  function draw() {
    const q = search.value.trim().toLowerCase();
    const rows = state.tasks.filter((t) => !q || `${t.id} ${t.title} ${t.description ?? ""}`.toLowerCase().includes(q));
    list.replaceChildren(...rows.map((t) => h("tr", { "data-testid": "task-row", "data-task-id": t.id, "data-benchmark": t.benchmark },
      h("td", {}, t.id), h("td", {}, t.title), h("td", {}, t.benchmark), h("td", {}, t.requires_setup ? "needs setup" : ""))));
    empty.hidden = rows.length > 0;
  }
  app.replaceChildren(h("h1", {}, "Tasks"), search, list, empty);
  draw();
}

function renderNewRun() {
  let selected = null;
  const options = h("ul", { class: "options" });
  const chosen = h("p", { "data-testid": "selected-task" }, "No task selected");
  const search = h("input", { "data-testid": "task-search-input", placeholder: "Search tasks", oninput: draw });
  function draw() {
    const q = search.value.trim().toLowerCase();
    options.replaceChildren(...state.tasks.filter((t) => !q || `${t.id} ${t.title}`.toLowerCase().includes(q)).map((t) =>
      h("li", { "data-testid": "task-option", "data-task-id": t.id, onclick: () => { selected = t; chosen.textContent = t.id; chosen.dataset.taskId = t.id; } }, `${t.id} — ${t.title}`)));
  }
  const agent = h("select", { "data-testid": "agent-select" }, state.agents.map((a) => h("option", { value: a.type }, a.title)));
  const goal = h("input", { "data-testid": "goal-input", placeholder: "Goal (open-ended tasks)" });
  const startUrl = h("input", { "data-testid": "start-url-input", placeholder: "https://example.com" });
  const maxSteps = h("input", { "data-testid": "max-steps-input", type: "number", min: 1, max: 100, value: 15 });
  const form = h("form", { "data-testid": "new-run-form", onsubmit: (e) => {
    e.preventDefault();
    if (!selected) return alert("Pick a task");
    const run = { id: `run-${Math.random().toString(36).slice(2, 10)}`, task_id: selected.id, goal: goal.value || null,
      agent: { type: agent.value, model: null, use_screenshot: false, use_axtree: true }, status: "queued", reward: null, n_steps: 0,
      max_steps: Number(maxSteps.value), created_at: new Date().toISOString(), started_at: null, finished_at: null, error: null };
    state.runs.unshift(run);
    navigate(`/runs/${run.id}`);
  } }, h("label", {}, "Task"), search, options, chosen, h("label", {}, "Agent"), agent, h("label", {}, "Goal"), goal,
    h("label", {}, "Start URL"), startUrl, h("label", {}, "Max steps"), maxSteps, h("button", { type: "submit", "data-testid": "create-run-submit" }, "Create run"));
  app.replaceChildren(h("h1", {}, "New run"), form);
  draw();
}

function renderRun(id) {
  const run = state.runs.find((r) => r.id === id);
  if (!run) return app.replaceChildren(h("p", { "data-testid": "run-not-found" }, `Run ${id} not found`));
  const live = (state.live[id] ??= { steps: [], chat: [], es: null });
  const status = badge(run.status, "run-status");
  const liveDot = h("span", { class: "live", "data-testid": "live-indicator", hidden: true }, "● live");
  const steps = h("ol", { class: "steps", "data-testid": "step-list", start: 0 });
  const detail = h("div", { class: "panel", "data-testid": "step-detail", hidden: true });
  const chat = h("div", { class: "chat" });
  const input = h("input", { "data-testid": "chat-input", placeholder: "Message the agent" });
  const cancel = h("button", { "data-testid": "run-cancel", onclick: () => {
    live.es?.close(); live.es = null;
    fetch(`/api/v1/runs/${id}/cancel`, { method: "POST" }).catch(() => {});
    setStatus("cancelled");
  } }, "Cancel run");

  function setStatus(s) {
    run.status = s; status.dataset.status = s; status.textContent = s;
    if (TERMINAL.includes(s)) { run.finished_at = new Date().toISOString(); liveDot.hidden = true; cancel.disabled = true; live.es?.close(); live.es = null; }
  }
  function addStep(step) {
    steps.append(h("li", { "data-testid": "step-item", "data-step-index": step.index, onclick: (e) => openStep(step, e.currentTarget) }, step.action ?? "(no action)"));
  }
  function openStep(step, li) {
    steps.querySelectorAll("li").forEach((el) => el.classList.toggle("sel", el === li));
    detail.hidden = false; detail.dataset.stepIndex = step.index;
    detail.replaceChildren(h("h3", {}, `Step ${step.index}`), h("p", {}, "Action: ", h("code", { "data-testid": "step-action" }, step.action ?? "")),
      h("p", { "data-testid": "step-thought" }, step.thought ?? ""), h("img", { "data-testid": "step-screenshot", alt: `step ${step.index}`, src: `/api/v1/runs/${id}/steps/${step.index}/screenshot` }));
  }
  function addChat(m) { chat.append(h("div", { class: "msg", "data-testid": "chat-message", "data-role": m.role }, h("b", {}, `${m.role}: `), m.message)); }
  const send = h("button", { "data-testid": "chat-send", type: "submit" }, "Send");
  const chatForm = h("form", { onsubmit: (e) => {
    e.preventDefault();
    const message = input.value.trim(); if (!message) return;
    const m = { role: "user", message, timestamp: new Date().toISOString() };
    live.chat.push(m); addChat(m); input.value = "";
    fetch(`/api/v1/runs/${id}/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }) }).catch(() => {});
  } }, input, send);

  app.replaceChildren(h("section", { "data-testid": "run-detail", "data-run-id": id },
    h("h1", {}, `Run ${id} `, status, " ", liveDot), h("p", { class: "muted" }, `${run.task_id} · agent ${run.agent.type}`),
    cancel, h("div", { class: "grid" },
      h("div", { class: "panel" }, h("h3", {}, "Steps"), steps),
      detail,
      h("div", { class: "panel", "data-testid": "chat-panel" }, h("h3", {}, "Chat"), chat, chatForm))));
  live.steps.forEach(addStep); live.chat.forEach(addChat);
  cancel.disabled = TERMINAL.includes(run.status);

  if (!TERMINAL.includes(run.status) && !live.es) {
    live.es = new EventSource(`/api/v1/runs/${encodeURIComponent(id)}/events?delay_ms=400`);
    for (const type of ["status", "step", "chat", "log"]) live.es.addEventListener(type, (e) => live.onEvent?.(JSON.parse(e.data)));
  }
  live.onEvent = (ev) => {
    if (ev.type === "status") setStatus(ev.status);
    if (ev.type === "step") { live.steps.push(ev.step); run.n_steps = live.steps.length; addStep(ev.step); }
    if (ev.type === "chat") { live.chat.push(ev.chat); addChat(ev.chat); }
  };
  live.detach = () => { live.onEvent = (ev) => {
    if (ev.type === "status") { run.status = ev.status; if (TERMINAL.includes(ev.status)) { live.es?.close(); live.es = null; } }
    if (ev.type === "step") { live.steps.push(ev.step); run.n_steps = live.steps.length; }
    if (ev.type === "chat") live.chat.push(ev.chat);
  }; };
  liveDot.hidden = !live.es;
}

boot();
