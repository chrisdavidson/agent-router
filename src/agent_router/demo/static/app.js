/* agent-router demo UI: vanilla JS, no build. One checkpoint renderer (renderCheckpoint)
   is shared by the Playground, the Live timeline, the backend comparison and Replay. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const state = {
  catalog: null, // /api/catalog
  entries: new Map(), // id -> entry
  backends: [], // [{name, available}]
  threshold: 0.5,
  thrTouched: false, // until the slider moves, each backend routes at its own calibrated threshold
};

const PRESETS = [
  { label: "17% of 2,340", point: "prompt", text: "What is 17% of 2,340 exactly?" },
  {
    label: "python3 -c 2**200", point: "tool", tool: "Bash",
    text: "compute 2**200 exactly", input: { command: 'python3 -c "print(2**200)"' },
  },
  {
    label: "Read release.html", point: "tool", tool: "Read",
    text: "summarize the release notes page", input: { file_path: "docs/release.html" },
  },
  {
    label: "failed orders", point: "prompt",
    text: "List the ids of orders whose status is failed in data/orders.json",
  },
  {
    label: "release-notes skill", point: "skill", tool: "Skill",
    text: "Write a commit message for adding retry logic to the HTTP client",
    input: { skill: "release-notes" },
  },
  { label: "run the test suite", point: "prompt", text: "run the test suite" },
];
const POINT_NAMES = { prompt: "Prompt", tool: "Tool", skill: "Skill" };
const POINT_LONG = { prompt: "User prompt", tool: "Tool call", skill: "Skill call" };

/* -- small helpers -------------------------------------------------------- */

function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

const pct = (p) => `${(p * 100).toFixed(p >= 0.995 || p < 0.005 ? 0 : 1)}%`;
const ms = (v) => (v == null ? "" : v >= 1000 ? `${(v / 1000).toFixed(2)} s` : `${Math.round(v)} ms`);

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  let body = null;
  try { body = await res.json(); } catch { /* not JSON */ }
  if (!res.ok) {
    const detail = body && body.detail ? (typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)) : res.statusText;
    throw new Error(detail);
  }
  return body;
}

function optionMeta(id) {
  if (id === "none") return state.catalog ? state.catalog.none : { id: "none", name: "Native path" };
  return state.entries.get(id) || { id, name: id };
}

/* -- the checkpoint model -------------------------------------------------- */

/** Normalise a route response, a live `decision` event or an audit record. */
function toCheckpoint(src) {
  const d = src.decision || src; // route response nests decision; events/records are flat
  const result = src.result !== undefined ? src.result : null;
  const probabilities = (result && result.probabilities) || src.probabilities || {};
  const choice = (result && result.choice) || src.choice || null;
  let optionIds = src.options && src.options.length
    ? src.options.map((o) => (typeof o === "string" ? o : o.id))
    : Object.keys(probabilities);
  if (!optionIds.includes("none") && Object.keys(probabilities).length) optionIds.push("none");
  optionIds = [...optionIds.filter((i) => i !== "none"), ...(optionIds.includes("none") ? ["none"] : [])];
  const thr = src.threshold ?? (src.thresholds && src.thresholds.threshold) ?? state.threshold;
  return {
    point: src.point || (src.event && src.event.point) || "prompt",
    tool: src.tool_name || null,
    action: d.action,
    reason: d.reason || null,
    entryId: d.entry_id || null,
    choice,
    probabilities,
    optionIds,
    confidence: (result && result.confidence) ?? src.confidence ?? null,
    backend: (result && result.backend) || src.backend || null,
    stages: (result && result.stages) || src.stages || [],
    latency: src.latency_ms ?? (result && result.latency_ms) ?? null,
    hint: src.hint || null,
    hintRestored: !!src.hint_restored,
    threshold: thr,
    mode: src.mode || (src.thresholds && src.thresholds.mode) || null,
    state: src.state || null,
    text: src.text || null,
  };
}

/** Visual state: suggest | enforce | gated (pointed, but below threshold) | native | skipped | error */
function tone(cp) {
  if (cp.action === "suggest") return "suggest";
  if (cp.action === "enforce") return "enforce";
  if (cp.action === "native" && cp.entryId) return "gated";
  if (cp.action === "native" && !Object.keys(cp.probabilities).length && cp.reason && cp.reason.startsWith("decider error")) return "error";
  if (cp.action === "skipped") return "skipped";
  return "native";
}

function verdict(cp) {
  const t = tone(cp);
  const name = cp.entryId ? optionMeta(cp.entryId).name : null;
  const p = cp.entryId ? cp.probabilities[cp.entryId] : null;
  switch (t) {
    case "suggest": return { title: `Points to ${name}`, pill: "Hint injected" };
    case "enforce": return { title: `Blocks ${cp.tool || "the call"}, points to ${name}`, pill: "Call denied" };
    case "gated": return { title: `Leans to ${name}, not enough`, pill: `${pct(p)} is under ${pct(cp.threshold)}` };
    case "error": return { title: "Classifier failed, agent continues", pill: "Fail open" };
    case "skipped": return { title: skipTitle(cp.reason), pill: "Skipped" };
    default: return { title: "None fits, agent's own tools", pill: "Native path" };
  }
}

function skipTitle(reason) {
  if (!reason) return "Not routed";
  if (reason.includes("own tool")) return "Already a catalog tool, not routed";
  if (reason.includes("no eligible")) return "No catalog option covers this tool";
  if (reason.includes("already suggested")) return "Already hinted this turn";
  if (reason.includes("disabled")) return "Router disabled";
  return reason;
}

/** Plain text with **bold** spans (no HTML is ever interpreted). */
function richText(text) {
  const frag = document.createDocumentFragment();
  String(text).split(/(\*\*[^*]+\*\*)/).forEach((part) => {
    if (/^\*\*[^*]+\*\*$/.test(part)) frag.append(el("b", { text: part.slice(2, -2) }));
    else if (part) frag.append(part);
  });
  return frag;
}

/* -- rendering ------------------------------------------------------------- */

/** Bars for one distribution. `showThr=false` for a cascade stage that did not decide. */
function renderBars(cp, t, showThr = true) {
  const bars = el("div", { class: "bars", role: "list", "aria-label": "Probability per option" });
  const thr = Math.max(0, Math.min(1, cp.threshold));
  const edge = thr < 0.08 ? "edge-l" : thr > 0.92 ? "edge-r" : "";
  if (showThr) {
    bars.append(
      el("span"),
      el("div", { class: "thr-head", "aria-hidden": "true" },
        el("span", { class: `thr-tag ${edge}`, style: `left:${thr * 100}%`, text: `threshold ${thr.toFixed(2)}` })),
      el("span"),
    );
  }
  cp.optionIds.forEach((id) => {
    const isNone = id === "none";
    if (isNone && cp.optionIds.length > 1) bars.append(el("div", { class: "bar-sep", "aria-hidden": "true" }));
    const p = cp.probabilities[id] ?? 0;
    const chosen = id === cp.choice;
    const meta = optionMeta(id);
    const fill = el("span", { class: "bar-fill" });
    const row = el("div", {
      class: `bar-row${chosen ? ` chosen ${t}` : ""}${isNone ? " is-none" : ""}`,
      role: "listitem",
      "aria-label": `${meta.name}: ${pct(p)}${chosen ? ", chosen" : ""}`,
    },
      el("div", { class: "bar-label", title: meta.what || "" },
        el("span", { class: "nm", text: isNone ? "none" : meta.name }),
        el("span", { class: "id", text: isNone ? "the agent's own tools" : id })),
      el("div", { class: "bar-track" }, fill,
        showThr ? el("span", { class: "thr-mark", style: `left:${thr * 100}%`, "aria-hidden": "true" }) : null),
      el("div", { class: "bar-val", text: Object.keys(cp.probabilities).length ? pct(p) : "–" }),
    );
    bars.append(row);
    requestAnimationFrame(() => { fill.style.width = `${Math.max(p * 100, p > 0 ? 0.6 : 0)}%`; });
  });
  return bars;
}

/* -- cascade stages (local classifier, then Jev) --------------------------------- */

const STAGE_NAMES = { primary: "Local classifier (MIT, offline)", confirm: "Jev (confirms)" };

function cascadeNote(cp) {
  if (cp.backend === "cascade:local") return { cls: "local", text: "Answered locally", why: "The local classifier was confidently none; Jev was not asked." };
  if (cp.backend === "cascade:local-fallback") return { cls: "fallback", text: "Jev failed: local fallback", why: "Escalated, but Jev failed: the local answer is used, biased to none." };
  return { cls: "escalated", text: "Escalated to Jev", why: "The local answer was not a confident none, so Jev confirms." };
}

/** One labelled bar set per stage; only the deciding one shows the router threshold. */
function renderStages(cp, t) {
  const note = cascadeNote(cp);
  const box = el("div", { class: "stages" }, el("p", { class: `stage-note ${note.cls}`, text: note.text, title: note.why }));
  const fallback = cp.backend === "cascade:local-fallback";
  cp.stages.forEach((st, i) => {
    const deciding = !fallback && i === cp.stages.length - 1;
    const head = el("div", { class: "stage-head" },
      el("span", { class: "stage-name", text: STAGE_NAMES[st.role] || st.role }),
      el("span", { class: "stage-meta", text: [st.backend, st.latency_ms != null ? ms(st.latency_ms) : null].filter(Boolean).join(", ") }));
    const body = st.skipped
      ? el("p", { class: "cmp-off", text: "Skipped: Jev failed repeatedly, so it is paused for a minute (circuit open)." })
      : st.failed || st.error_type
      ? el("p", { class: "cmp-off", text: `Failed (${st.error_type || "error"}). Details are in the audit log.` })
      : renderBars({ ...cp, probabilities: st.probabilities || {}, choice: st.choice }, deciding ? t : "stage", deciding);
    box.append(el("section", { class: `stage${deciding ? " deciding" : ""}` }, head, body));
  });
  if (fallback) {
    box.append(el("section", { class: "stage deciding" },
      el("div", { class: "stage-head" }, el("span", { class: "stage-name", text: "Fallback answer" })),
      renderBars(cp, t)));
  }
  return box;
}

function renderSees(cp, t) {
  const box = el("div", { class: "sees" });
  if (cp.hint) {
    box.append(
      el("h4", { text: t === "enforce" ? `The ${cp.tool || "native"} call is denied with this reason` : "What the agent sees (added to its context)" }),
      el("pre", { class: `hint-text ${t}`, text: cp.hint }),
    );
    if (cp.hintRestored) box.append(el("p", { class: "note", text: "The audit log keeps 300 characters; the rest is re-rendered from the same catalog template." }));
  } else {
    const why = t === "gated"
      ? "Nothing. The top option is below the threshold, so the hook returns {} and the agent carries on unchanged."
      : t === "error"
        ? `Nothing. ${cp.reason || "The classifier raised"}; the router fails open.`
        : "Nothing. The hook returns {} and the agent carries on unchanged.";
    box.append(el("h4", { text: "What the agent sees" }), el("p", { class: "nothing", text: why }));
  }
  return box;
}

function renderDetails(cp) {
  const dl = el("dl");
  const add = (k, v) => { if (v != null && v !== "") dl.append(el("dt", { text: k }), el("dd", { text: v })); };
  add("Router reason", cp.reason);
  add("Confidence", cp.confidence != null ? cp.confidence.toFixed(3) : null);
  add("Mode", cp.mode);
  const d = el("details", { class: "why" }, el("summary", { text: "Why this decision" }), dl);
  if (cp.state) d.append(el("pre", { text: cp.state }));
  return d;
}

/** Fill `root` with one checkpoint. opts: {compact, title, extra} */
function renderCheckpoint(root, src, opts = {}) {
  const cp = toCheckpoint(src);
  const t = tone(cp);
  const v = verdict(cp);
  root.replaceChildren();
  root.classList.toggle("compact", !!opts.compact);
  const where = el("div", { class: "cp-where" },
    opts.title ? opts.title : `${POINT_LONG[cp.point] || cp.point} checkpoint`,
    cp.tool ? " on " : "", cp.tool ? el("span", { class: "tool", text: cp.tool }) : "");
  const meta = el("div", { class: "cp-meta" },
    cp.backend ? `${cp.backend}` : "", cp.latency != null ? `, ${ms(cp.latency)}` : "");
  root.append(
    el("div", { class: "cp-head" }, where, meta),
    el("div", { class: "verdict" }, el("h3", { text: v.title }), el("span", { class: `pill ${t}`, text: v.pill })),
  );
  if (cp.stages.length) root.append(renderStages(cp, t));
  else if (cp.optionIds.length) root.append(renderBars(cp, t));
  if (opts.compact) {
    if (opts.extra) root.append(opts.extra);
    if (t === "error" && cp.reason) root.append(el("p", { class: "cmp-off", text: cp.reason }));
    return cp;
  }
  root.append(renderSees(cp, t), renderDetails(cp));
  return cp;
}

/* -- playground ------------------------------------------------------------- */

const form = $("#step-form");
let routeSeq = 0;

function currentPoint() { return $("input[name=point]:checked", form).value; }

function syncPointFields() {
  const point = currentPoint();
  $("#tool-fields").hidden = point === "prompt";
  $("#text-label").textContent = point === "prompt" ? "Prompt" : "Prompt the agent is working on";
  const toolSel = $("#tool-name");
  if (point === "skill") { ensureOption(toolSel, "Skill"); toolSel.value = "Skill"; toolSel.disabled = true; }
  else { toolSel.disabled = false; if (toolSel.value === "Skill") toolSel.value = "Bash"; }
}

function ensureOption(sel, value) {
  if (![...sel.options].some((o) => o.value === value)) sel.append(el("option", { text: value }));
}

function applyPreset(p, btn) {
  $$(".preset").forEach((b) => b.setAttribute("aria-pressed", b === btn ? "true" : "false"));
  $(`input[name=point][value=${p.point}]`, form).checked = true;
  $("#text").value = p.text;
  if (p.tool) { ensureOption($("#tool-name"), p.tool); $("#tool-name").value = p.tool; }
  $("#tool-input").value = p.input ? JSON.stringify(p.input, null, 2) : "";
  syncPointFields();
  runRoute();
}

function readStep() {
  const point = currentPoint();
  const step = { text: $("#text").value, point };
  if (point !== "prompt") {
    step.tool_name = $("#tool-name").value;
    const raw = $("#tool-input").value.trim();
    if (raw) {
      try { step.tool_input = JSON.parse(raw); } catch { throw new Error("Tool input must be a JSON object, for example {\"command\": \"ls\"}."); }
      if (typeof step.tool_input !== "object" || Array.isArray(step.tool_input)) throw new Error("Tool input must be a JSON object.");
    }
  }
  step.mode = $("input[name=mode]:checked", form).value;
  // untouched slider: the server applies the backend's own (calibrated) threshold
  step.threshold = state.thrTouched ? Number($("#threshold").value) : null;
  return step;
}

/** Show the threshold the server used while the slider is untouched (backend default). */
function showThreshold(thr) {
  if (thr == null) return;
  $("#threshold").value = thr;
  $("#thr-out").textContent = `${Number(thr).toFixed(2)} auto`;
  $("#thr-out").title = "The classifier's own calibrated threshold. Move the slider to override it.";
}

function showFormError(msg) {
  const e = $("#form-error");
  e.hidden = !msg;
  e.textContent = msg || "";
}

async function route(step, backend) {
  return api("/api/route", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...step, backend }),
  });
}

async function runRoute() {
  let step;
  try { step = readStep(); } catch (err) { showFormError(err.message); return; }
  showFormError("");
  const seq = ++routeSeq;
  const board = $("#board");
  board.classList.add("loading");
  try {
    const res = await route(step, $("#backend").value || "local");
    if (seq !== routeSeq) return;
    if (!state.thrTouched) showThreshold(res.threshold);
    renderCheckpoint(board, res);
  } catch (err) {
    if (seq === routeSeq) showFormError(`Routing failed: ${err.message}`);
  } finally {
    if (seq === routeSeq) board.classList.remove("loading");
  }
  if (!$("#compare").hidden) runCompare();
}

async function runCompare() {
  let step;
  try { step = readStep(); } catch (err) { showFormError(err.message); return; }
  const section = $("#compare");
  const grid = $("#compare-grid");
  section.hidden = false;
  grid.replaceChildren();
  for (const b of state.backends) {
    const card = el("article", { class: "checkpoint compact", "aria-live": "polite" });
    grid.append(card);
    if (!b.available) {
      card.append(el("div", { class: "cmp-name", text: b.name }),
        el("p", { class: "cmp-off", text: "Not available here: install its extra or set its API key." }));
      continue;
    }
    card.append(el("div", { class: "cmp-name", text: b.name }), el("p", { class: "cmp-off", text: "Asking…" }));
    const t0 = performance.now();
    route(step, b.name).then((res) => {
      renderCheckpoint(card, res, { compact: true, title: el("span", { class: "cmp-name", text: b.name }) });
      $(".cp-meta", card).replaceChildren(el("span", { class: "latency", text: ms(res.latency_ms) }));
    }).catch((err) => {
      card.replaceChildren(el("div", { class: "cmp-name", text: b.name }),
        el("p", { class: "cmp-off", text: `Failed after ${ms(performance.now() - t0)}: ${err.message}` }));
    });
  }
}

function initPlayground() {
  const presets = $("#presets");
  PRESETS.forEach((p) => {
    const btn = el("button", { type: "button", class: "preset", "aria-pressed": "false" },
      el("span", { class: "pt", text: POINT_NAMES[p.point] }), p.label);
    btn.addEventListener("click", () => applyPreset(p, btn));
    presets.append(btn);
  });
  $$("input[name=point]", form).forEach((r) => r.addEventListener("change", syncPointFields));
  form.addEventListener("submit", (e) => { e.preventDefault(); runRoute(); });
  $("#compare-btn").addEventListener("click", runCompare);
  let slideTimer;
  $("#threshold").addEventListener("input", (e) => {
    state.thrTouched = true;
    $("#thr-out").textContent = Number(e.target.value).toFixed(2);
    clearTimeout(slideTimer);
    slideTimer = setTimeout(runRoute, 120);
  });
  $$("input[name=mode]", form).forEach((r) => r.addEventListener("change", runRoute));
  $("#backend").addEventListener("change", runRoute);
  applyPreset(PRESETS[0], $(".preset"));
}

/* -- live agent -------------------------------------------------------------- */

let live = null; // EventSource

function tlItem(kind, cls, ...body) {
  return tlInsert(null, kind, cls, ...body);
}

/** Add a timeline item, before `before` when given (else at the end). */
function tlInsert(before, kind, cls, ...body) {
  const li = el("li", { class: `tl ${cls}` }, el("div", { class: "tl-kind", text: kind }), el("div", { class: "tl-body" }, ...body));
  $("#timeline").insertBefore(li, before);
  li.scrollIntoView({ block: "nearest", behavior: "smooth" });
  return li;
}

function liveStatus(...kids) {
  const s = $("#live-status");
  s.hidden = false;
  s.replaceChildren(...kids);
}

function stopLive(message) {
  if (live) { live.close(); live = null; }
  $("#live-run").disabled = false;
  $("#live-stop").hidden = true;
  $$(".tl.pending").forEach((n) => n.remove());
  if (message) liveStatus(message);
}

async function startLive(e) {
  e.preventDefault();
  const prompt = $("#live-prompt").value.trim();
  if (!prompt) { liveStatus("Type a prompt for the agent first."); return; }
  stopLive();
  $("#timeline").replaceChildren();
  const mode = $("input[name=live-mode]:checked").value;
  const backend = $("#live-backend").value || "local";
  $("#live-run").disabled = true;
  liveStatus(`Starting a ${mode} session with the ${backend} classifier…`);
  let start;
  try {
    // POST mints a one-time token; the stream itself is a plain same-origin GET.
    start = await api("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, mode, backend }),
    });
  } catch (err) {
    $("#live-run").disabled = false;
    liveStatus(`The server did not start the run: ${err.message}`);
    return;
  }
  $("#live-stop").hidden = false;
  const toolItems = new Map();
  let lastCheckpoint = null;
  let session = null;
  const pending = () => { $$(".tl.pending").forEach((n) => n.remove()); tlItem("", "pending", "Agent is working…"); };

  live = new EventSource(start.stream);
  const on = (type, fn) => live.addEventListener(type, (ev) => fn(JSON.parse(ev.data)));
  on("session", (d) => {
    session = d.session;
    state.threshold = d.threshold;
    liveStatus(`Session ${d.session}, ${d.mode} mode, threshold ${d.threshold.toFixed(2)}, ${d.backend} classifier.`);
  });
  on("prompt", (d) => { tlItem("You asked", "prompt", d.prompt); pending(); });
  on("decision", (d) => {
    $$(".tl.pending").forEach((n) => n.remove());
    const kind = d.point === "prompt" ? "Checkpoint: user prompt" : `Checkpoint: before ${d.tool_name}`;
    // The SDK streams the tool_use block before its PreToolUse hook runs: put the
    // checkpoint above the call it guards.
    const guarded = d.tool_name ? [...toolItems.values()].reverse()
      .find((li) => li.dataset.tool === d.tool_name && !li.dataset.checked) : null;
    if (guarded) guarded.dataset.checked = "1";
    const before = guarded || null;
    let li;
    if (d.action === "skipped" && !Object.keys(d.probabilities || {}).length) {
      // gated out before the classifier was asked: one quiet line
      const why = (d.tool_name || "").startsWith("mcp__agent_router__")
        ? "already a catalog tool, not routed" : "no catalog option covers this tool, not routed";
      li = tlInsert(before, kind, "cp skipped", el("span", { class: "muted", text: `Skipped: ${why}.` }));
    } else {
      const card = el("article", { class: "checkpoint" });
      const cp = renderCheckpoint(card, { ...d, threshold: state.threshold, mode }, { compact: true });
      const t = tone(cp);
      if (cp.hint) card.append(el("pre", { class: `hint-text ${t}`, text: cp.hint }));
      li = tlInsert(before, kind, `cp ${t}`, card);
    }
    lastCheckpoint = li;
    pending();
  });
  on("hook", (d) => {
    if (!lastCheckpoint) return;
    const txt = { additionalContext: "Hook returned additionalContext: the hint above joins the agent's context.",
      deny: "Hook returned deny: the native call does not run.", none: "Hook returned {}: nothing changes." }[d.output] || d.output;
    $(".tl-body", lastCheckpoint).append(el("div", { class: "hook-out", text: txt }));
  });
  on("tool_use", (d) => {
    $$(".tl.pending").forEach((n) => n.remove());
    const li = tlItem("Tool call", "tool", el("span", { class: "tool-name", text: d.name }),
      el("pre", { text: JSON.stringify(d.input, null, 2) }));
    li.dataset.tool = d.name;
    toolItems.set(d.id, li);
    pending();
  });
  on("tool_result", (d) => {
    const li = toolItems.get(d.tool_use_id);
    const det = el("details", {}, el("summary", { text: d.is_error ? "Result (error)" : "Result" }), el("pre", { text: d.content }));
    if (li) $(".tl-body", li).append(det);
    else tlItem("Tool result", "tool", det);
  });
  on("assistant", (d) => {
    $$(".tl.pending").forEach((n) => n.remove());
    tlItem("Agent", "say", richText(d.text)).dataset.text = d.text;
    pending();
  });
  on("result", (d) => {
    $$(".tl.pending").forEach((n) => n.remove());
    const said = $$(".tl.say").pop();
    if (said && d.result && said.dataset.text.trim() === d.result.trim()) said.remove(); // shown as the answer
    const cost = [d.num_turns != null ? `${d.num_turns} turns` : null, d.duration_ms != null ? ms(d.duration_ms) : null,
      d.total_cost_usd != null ? `$${d.total_cost_usd.toFixed(4)}` : null].filter(Boolean).join(", ");
    tlItem(d.is_error ? "Finished with an error" : "Answer", d.is_error ? "answer err" : "answer", richText(d.result || "(no text)"), cost ? el("div", { class: "cost", text: cost }) : null);
  });
  live.addEventListener("error", (ev) => {
    if (ev.data) { // a server-sent `error` event: the run failed
      const d = JSON.parse(ev.data);
      tlItem("Run failed", "err", d.message || "unknown error");
      return;
    }
    // a transport error: close now so EventSource never reconnects (that would start a new run)
    stopLive(live && live.readyState === EventSource.CLOSED ? "Connection closed." : "Lost the connection to the demo server.");
  });
  on("done", () => {
    stopLive();
    if (session) {
      liveStatus(`Session ${session} finished. `, el("a", { href: "#replay", onclick: (ev) => { ev.preventDefault(); openReplay(session); }, text: "Replay its checkpoints" }));
    }
  });
}

function initLive() {
  $("#live-form").addEventListener("submit", startLive);
  $("#live-stop").addEventListener("click", () => stopLive("Stopped. The server cancels the agent run."));
}

/* -- replay ------------------------------------------------------------------ */

const replay = { records: [], index: 0 };

async function loadSessions(select) {
  const sel = $("#session-select");
  let sessions = [];
  try { sessions = (await api("/api/audit/sessions")).sessions; } catch { sessions = []; }
  sel.replaceChildren(...sessions.map((s) => el("option", { value: s.session },
    `${s.session}${s.sample ? " (sample)" : ""}: ${s.records} checkpoint${s.records === 1 ? "" : "s"}${s.first_text ? `, “${s.first_text.slice(0, 48)}”` : ""}`)));
  $("#replay-empty").hidden = sessions.length > 0;
  $("#replay-body").hidden = sessions.length === 0;
  if (!sessions.length) return;
  sel.value = select && sessions.some((s) => s.session === select) ? select : sessions[0].session;
  await loadSession(sel.value);
}

async function loadSession(name) {
  const data = await api(`/api/audit/${encodeURIComponent(name)}`);
  replay.records = data.records;
  replay.index = 0;
  const pills = $("#step-pills");
  pills.replaceChildren(...replay.records.map((r, i) => {
    const t = tone(toCheckpoint(r));
    const label = r.point === "prompt" ? "P" : r.point === "skill" ? "S" : "T";
    return el("li", {}, el("button", { type: "button", class: t, title: `${r.point}${r.tool_name ? ` ${r.tool_name}` : ""}${r.agent_type ? ` (inside ${r.agent_type})` : ""}: ${r.action}`,
      "aria-label": `Checkpoint ${i + 1}, ${r.point}, ${r.action}`, onclick: () => showStep(i) }, `${i + 1}${label}`));
  }));
  showStep(0);
}

function showStep(i) {
  const n = replay.records.length;
  if (!n) return;
  replay.index = Math.max(0, Math.min(n - 1, i));
  const rec = replay.records[replay.index];
  renderCheckpoint($("#replay-board"), rec, { title: `Checkpoint ${replay.index + 1} of ${n}: ${POINT_LONG[rec.point] || rec.point}` });
  const board = $("#replay-board");
  if (rec.text) board.insertBefore(el("p", { class: "muted", text: `Prompt: ${rec.text}` }), board.children[1]);
  board.insertBefore(el("p", { class: "muted", text: rec.agent_type ? `Called inside the ${rec.agent_type} agent` : "Called on the main thread" }), board.children[1]);
  $$("#step-pills button").forEach((b, j) => (j === replay.index ? b.setAttribute("aria-current", "step") : b.removeAttribute("aria-current")));
  $("#step-prev").disabled = replay.index === 0;
  $("#step-next").disabled = replay.index === n - 1;
}

function openReplay(session) {
  selectTab("replay");
  loadSessions(session);
}

function initReplay() {
  $("#session-select").addEventListener("change", (e) => loadSession(e.target.value));
  $("#session-refresh").addEventListener("click", () => loadSessions($("#session-select").value));
  $("#step-prev").addEventListener("click", () => showStep(replay.index - 1));
  $("#step-next").addEventListener("click", () => showStep(replay.index + 1));
  document.addEventListener("keydown", (e) => {
    if ($("#view-replay").hidden || /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return;
    if (e.key === "ArrowLeft") showStep(replay.index - 1);
    if (e.key === "ArrowRight") showStep(replay.index + 1);
  });
}

/* -- tabs & boot ---------------------------------------------------------------- */

const TABS = { play: "Playground", live: "Live agent", replay: "Replay" };

function selectTab(name) {
  for (const key of Object.keys(TABS)) {
    const on = key === name;
    $(`#tab-${key}`).setAttribute("aria-selected", on ? "true" : "false");
    $(`#view-${key}`).hidden = !on;
  }
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  if (name === "replay" && !replay.records.length) loadSessions();
}

async function boot() {
  for (const key of Object.keys(TABS)) $(`#tab-${key}`).addEventListener("click", () => selectTab(key));
  const [catalog, backends] = await Promise.all([api("/api/catalog"), api("/api/backends")]);
  state.catalog = catalog;
  state.threshold = catalog.threshold;
  catalog.entries.forEach((e) => state.entries.set(e.id, e));
  state.backends = backends.backends;
  $("#shell-note").textContent = catalog.live && catalog.live.allow_shell
    ? "Shell and web tools (Bash, WebFetch) are enabled: the server was started with allow_shell."
    : "Shell and web tools (Bash, WebFetch) are disabled. The router still sees those calls first; the SDK then refuses them. Start the server with --allow-shell to enable them.";
  showThreshold(catalog.threshold);
  if (catalog.mode === "enforce") $("input[name=mode][value=enforce]").checked = true;
  for (const sel of [$("#backend"), $("#live-backend")]) {
    sel.replaceChildren(...state.backends.map((b) => el("option", { value: b.name, disabled: !b.available },
      b.available ? b.name : `${b.name} (not available)`)));
    sel.value = backends.default;
  }
  initPlayground();
  initLive();
  initReplay();
  const hash = location.hash.slice(1);
  selectTab(TABS[hash] ? hash : "play");
}

boot().catch((err) => {
  $("#board").replaceChildren(el("p", { class: "board-empty", text: `Could not reach the demo server: ${err.message}` }));
});
