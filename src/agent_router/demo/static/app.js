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
  // The bar the chosen entry was held to: per-entry thresholds differ from the router's.
  // Records written before `applied_threshold` existed still name it in their reason.
  const reasonThr = /threshold (\d*\.\d+)/.exec(d.reason || "");
  const entryThr = d.entry_id && state.entries.get(d.entry_id) ? state.entries.get(d.entry_id).threshold : null;
  const thr = d.applied_threshold ?? (reasonThr ? Number(reasonThr[1]) : null) ?? entryThr
    ?? src.threshold ?? (src.thresholds && src.thresholds.threshold) ?? state.threshold;
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
    case "suggest": return { title: `Points to ${name}`, pill: `Hint injected: ${vsThreshold(p, cp.threshold)}` };
    case "enforce": return { title: `Blocks ${cp.tool || "the call"}, points to ${name}`, pill: `Call denied: ${vsThreshold(p, cp.threshold)}` };
    case "gated": return { title: `Leans to ${name}, not enough`, pill: vsThreshold(p, cp.threshold) };
    case "error": return { title: "Classifier failed, agent continues", pill: "Fail open" };
    case "skipped": return { title: skipTitle(cp.reason), pill: "Skipped" };
    default: return { title: "None fits, agent's own tools", pill: "Native path" };
  }
}

/** "69.6% is below the 80.0% threshold": which side of the bar the chosen option landed on. */
function vsThreshold(p, thr) {
  if (p == null || thr == null) return "";
  const side = p > thr ? "above" : p < thr ? "below" : "at";
  // one more decimal when rounding would print the same figure on both sides
  const fmt = (x) => (side !== "at" && pct(p) === pct(thr) ? `${(x * 100).toFixed(2)}%` : pct(x));
  return `${fmt(p)} is ${side} the ${fmt(thr)} threshold`;
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
        el("span", { class: `thr-tag ${edge}`, style: `left:${thr * 100}%`, text: `threshold ${pct(thr)}` })),
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
      "aria-label": `${meta.name}: ${pct(p)}${chosen ? ", chosen" : ""}${chosen && showThr && !isNone ? `, ${vsThreshold(p, thr).replace(/^\S+ is /, "")}` : ""}`,
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
      ? `Nothing. ${cp.entryId ? optionMeta(cp.entryId).name : "The top option"} is at ${vsThreshold(cp.probabilities[cp.entryId], cp.threshold).replace(/ is /, ", ")}, so the hook returns {} and the agent carries on unchanged.`
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
      const cp = renderCheckpoint(card, { ...d, threshold: d.applied_threshold ?? state.threshold, mode }, { compact: true });
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
      liveStatus(`Session ${session} finished. `, el("a", { href: sessionAddress("replay", session), text: "Replay its checkpoints" }));
    }
  });
}

function initLive() {
  $("#live-form").addEventListener("submit", startLive);
  $("#live-stop").addEventListener("click", () => stopLive("Stopped. The server cancels the agent run."));
}

/* -- one name per session ------------------------------------------------------- */

/** A session's short id: the first 8 characters of a Claude Code session id (as Claude Code
    shows it), or a live run's whole id (``20261017-142301-a3f9c1``: its first 8 are only a date). */
const shortId = (id) => (/^[0-9a-f]{8}-[0-9a-f]{4}-/i.test(String(id)) ? String(id).slice(0, 8) : String(id));

/** What a session is called in every tab: what it was about (the server's ``label``, the same
    for Replay and Trace) and its short id, e.g. "First-principles LLC analysis · 12be92f6". */
const sessionName = (s) => (s.label ? `${s.label} · ${shortId(s.session)}` : `session ${shortId(s.session)}`);

/* -- replay ------------------------------------------------------------------ */

const replay = { records: [], index: 0, session: null, sessions: new Map() };

async function loadSessions(select) {
  const sel = $("#session-select");
  let sessions = [];
  try { sessions = (await api("/api/audit/sessions")).sessions; } catch { sessions = []; }
  replay.sessions = new Map(sessions.map((s) => [s.session, s]));
  sel.replaceChildren(...sessions.map((s) => el("option", { value: s.session, title: s.session },
    `${sessionName(s)}${s.sample ? " (sample)" : ""} · ${since(new Date(s.mtime * 1000).toISOString())} · ${s.records} checkpoint${s.records === 1 ? "" : "s"}`)));
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
  replay.session = name;
  $("#replay-trace").hidden = !(replay.sessions.get(name) || {}).has_trace;
  if (!$("#view-replay").hidden) setAddress("replay", name);
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

function initReplay() {
  $("#session-select").addEventListener("change", (e) => { setAddress("replay", e.target.value, true); loadSession(e.target.value); });
  $("#replay-trace").addEventListener("click", () => go("trace", replay.session));
  $("#session-refresh").addEventListener("click", () => loadSessions($("#session-select").value));
  $("#step-prev").addEventListener("click", () => showStep(replay.index - 1));
  $("#step-next").addEventListener("click", () => showStep(replay.index + 1));
  document.addEventListener("keydown", (e) => {
    if ($("#view-replay").hidden || /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return;
    if (e.key === "ArrowLeft") showStep(replay.index - 1);
    if (e.key === "ArrowRight") showStep(replay.index + 1);
  });
}

/* -- trace ------------------------------------------------------------------- */
/* Decision traces from an integration's record-only hooks (integrations/first-principles/
   trace.py): what the agent did, what it decided, and where the router's notes landed. */

const trace = { data: null, runs: [], index: 0, sessions: null, pinned: false, timer: null, selected: null, decTab: "assumptions", factsOpen: false };
const BAND_TONE = { Rigorous: "suggest", Sound: "gated", "Hand-wavy": "enforce", Absent: "enforce" };
const CONF_TONE = { HIGH: "suggest", MEDIUM: "gated", LOW: "enforce" };
const VERDICT_TONE = { Accept: "native", Challenge: "gated", Discard: "enforce" };
const ACTION_TONE = { suggest: "suggest", enforce: "enforce", gated: "gated", native: "native", skipped: "native" };
const REPORT_OP = { create: "Creates the report file", revise: "Revises the report in place", check: "Checks the report" };

const chip = (text, tone = "native", title) => el("span", { class: `chip ${tone}`, title, text });
const when = (ts) => Date.parse(ts);
const clock = (s) => {
  if (s == null) return "";
  const r = Math.round(s); // round once, so 59.6 s reads 1:00, not 0:60
  return `${Math.floor(r / 60)}:${String(r % 60).padStart(2, "0")}`;
};
/** The calculator's result text, unwrapped from its JSON envelope when it has one. */
function calcResult(text) {
  try {
    const v = JSON.parse(text);
    if (v && typeof v === "object") return v.result ?? v.value ?? text;
  } catch { /* plain text, or an envelope the trace cut short */ }
  const cut = /^\{"(?:result|value)":"([\s\S]*)$/.exec(String(text || ""));
  return cut ? `${cut[1].replace(/"\}?$/, "").replace(/\\n/g, "\n").replace(/\\"/g, '"')}…` : text;
}
/** A multi-line command as one short line: `python3 -c "` alone says nothing. */
const oneLine = (cmd, n = 90) => {
  const flat = String(cmd || "").replace(/\s*\n\s*/g, " ⏎ ").trim();
  return flat.length > n ? `${flat.slice(0, n - 1)}…` : flat;
};
const minutes = (s) => (s == null ? "–" : s >= 90 ? `${(s / 60).toFixed(1)} min` : `${Math.round(s)} s`);

const TRACE_POLL_MS = 3000;
const STATUS_MARK = { running: "● running", unfinished: "◌ unfinished", finished: "✓" };
const since = (ts) => {
  const s = (Date.now() - when(ts)) / 1000;
  if (!Number.isFinite(s)) return "";
  if (s < 60) return `${Math.max(0, Math.round(s))} s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(when(ts)).toLocaleDateString(undefined, { month: "short", day: "numeric" });
};

/** One picker line: whether it is still running, what was asked, when, and how sure it ended. */
function sessionOption(s) {
  const runs = s.runs > 1 ? ` · ${s.finished}/${s.runs} runs` : "";
  const conf = s.status === "finished" && s.confidence ? ` · ${s.confidence}` : "";
  return el("option", { value: s.session, title: s.question ? `${s.session}\n${s.question}` : s.session },
    `${STATUS_MARK[s.status] || ""} ${sessionName(s)} · ${since(s.last_at)}${runs}${conf}`);
}

async function loadTraceSessions(select) {
  let body = { sessions: [] };
  try { body = await api("/api/trace/sessions"); } catch { /* shown as empty */ }
  trace.sessions = new Map(body.sessions.map((s) => [s.session, s]));
  const sel = $("#trace-select");
  sel.replaceChildren(...body.sessions.map(sessionOption));
  const none = body.sessions.length === 0;
  $("#trace-empty").hidden = !none;
  $("#trace-body").hidden = none;
  renderLiveLine();
  if (none) {
    trace.data = null;
    $("#trace-empty").replaceChildren(
      el("p", { text: "No decision traces yet." }),
      el("p", { class: "small-print", text: `Looking in ${body.trace_dir || "the trace folder"}. The first-principles integration's hooks write one trace per session; trace.py --replay makes one from a saved run. With Follow live on, a run appears here as soon as it starts.` }));
    return;
  }
  sel.value = select && trace.sessions.has(select) ? select : body.sessions[0].session;
  await loadTrace(sel.value);
}

/** Re-read the picker; reload the shown session only if its trace grew, and switch to a session
    that started since the last look. Never steals the view from a run the user picked by hand
    while that run is still going. */
async function pollTrace() {
  let body;
  try { body = await api("/api/trace/sessions"); } catch { return; }
  const before = trace.sessions || new Map();
  trace.sessions = new Map(body.sessions.map((s) => [s.session, s]));
  const sel = $("#trace-select");
  const shown = sel.value;
  const fresh = body.sessions.find((s) => !before.has(s.session) && s.status === "running");
  const shownLive = (before.get(shown) || {}).status === "running";
  const target = fresh && !(trace.pinned && shownLive) ? fresh.session : shown;
  sel.replaceChildren(...body.sessions.map(sessionOption));
  if (!body.sessions.length) { if (before.size) loadTraceSessions(); return; }
  if (!trace.data) { await loadTraceSessions(target); return; }
  sel.value = trace.sessions.has(target) ? target : body.sessions[0].session;
  const now = trace.sessions.get(sel.value);
  const was = before.get(sel.value);
  if (sel.value !== trace.data.session) {
    trace.pinned = false;
    await loadTrace(sel.value);
  } else if (!was || was.size !== now.size || was.mtime !== now.mtime) {
    await loadTrace(sel.value, { keep: true });
  } else {
    renderLiveLine();
  }
}

function renderLiveLine() {
  const line = $("#trace-live");
  const s = trace.data && trace.sessions && trace.sessions.get(trace.data.session);
  const follow = $("#trace-follow").checked;
  if (!s || (s.status === "finished" && !follow)) { line.hidden = true; return; }
  line.hidden = false;
  const running = s.status === "running";
  const text = running
    ? `Running · last activity ${since(s.last_at)}${follow ? " · updating every few seconds" : " · Follow live is off"}`
    : s.status === "unfinished"
      ? `No new activity since ${since(s.last_at)}: the run ended without a stop event (killed, crashed or print mode ended)`
      : "Following: a run that starts will open here";
  line.replaceChildren(el("span", { class: `live-dot${running && follow ? "" : " idle"}` }), el("span", { text }));
}

/** The open/closed state of every <details>, keyed so it survives a re-render. */
function detailsKey(d) {
  const li = d.closest("[data-key]");
  if (li) return li.dataset.key;
  const sum = d.querySelector("summary");
  return (sum ? sum.textContent : "").replace(/\s*\(.*$/, "");
}
const detailsState = (root) => new Map($$("details", root).map((d) => [detailsKey(d), d.open]));
function restoreDetails(root, saved) {
  $$("details", root).forEach((d) => { const k = detailsKey(d); if (saved.has(k)) d.open = saved.get(k); });
}

async function loadTrace(session, { keep = false } = {}) {
  const [data, why] = await Promise.all([api(`/api/trace/${encodeURIComponent(session)}`),
    api(`/api/trace/${encodeURIComponent(session)}/why`).catch(() => null)]); // no transcript: the log still works
  trace.why = why;
  const prev = keep && trace.data && trace.data.session === session
    ? { index: trace.index, last: trace.index === trace.runs.length - 1,
      open: [$("#trace-timeline"), $("#trace-decisions")].map(detailsState), scroll: logScroll() }
    : null;
  if (!prev) trace.selected = null;
  trace.data = data;
  if (!$("#view-trace").hidden) setAddress("trace", session); // follow-live's switches replace, not push
  if (trace.sessions) { const { records: _r, audit: _a, ...row } = data; trace.sessions.set(session, row); }
  const byRun = new Map();
  let handoff = []; // the main session's Agent call(s) that start the next run
  for (const r of data.records) {
    if (r.kind === "delegation" && !r.agent_id) { handoff.push(r); continue; }
    const key = r.agent_id || "run";
    if (!byRun.has(key)) { byRun.set(key, handoff); handoff = []; }
    byRun.get(key).push(r);
  }
  // delegated, agent not started yet: show the hand-off as a run of its own
  if (handoff.length) byRun.set("pending", handoff);
  trace.runs = [...byRun.entries()].map(([id, recs]) => ({
    id, recs, start: recs.find((r) => r.kind === "run_start"),
    // a delivery guard that refuses the stop makes one run_end per attempt: the last one is the run's end
    end: recs.filter((r) => r.kind === "run_end").at(-1),
  }));
  const pills = $("#run-pills");
  pills.hidden = trace.runs.length < 2;
  pills.replaceChildren(...trace.runs.map((r, i) => el("li", {}, el("button", {
    type: "button", class: r.end ? "suggest" : "gated", onclick: () => showRun(i),
    "aria-label": `Run ${i + 1}${r.end ? "" : ", not finished"}`,
  }, `Run ${i + 1}`))));
  // following a live session: stay on the newest run; otherwise stay where the user was
  const last = trace.runs.length - 1;
  showRun(prev ? Math.min(prev.last ? last : prev.index, last) : 0);
  if (prev) [$("#trace-timeline"), $("#trace-decisions")].forEach((root, i) => restoreDetails(root, prev.open[i]));
  if (prev) restoreLogScroll(prev.scroll);
  renderLiveLine();
}

/** Where the event log is scrolled, so a live refresh neither jumps to the top nor stops following
    the newest event when the log was at its end. */
function logScroll() {
  const pane = $("#trace-timeline");
  return { top: pane.scrollTop, end: pane.scrollTop + pane.clientHeight >= pane.scrollHeight - 4 };
}
function restoreLogScroll(s) {
  const pane = $("#trace-timeline");
  pane.scrollTop = s.end ? pane.scrollHeight : s.top;
}

/** The router's notes that fired inside this run (or, for the prompt, just before it). */
function routerMarks(run) {
  const start = run.start ? when(run.start.ts) : -Infinity;
  const end = run.end ? when(run.end.ts) : Infinity;
  return (trace.data.audit || []).filter((a) => a.agent_type && ["suggest", "enforce"].includes(a.action)
    && when(a.ts) >= start && when(a.ts) <= end);
}

function appliedThreshold(rec) {
  if (rec.applied_threshold != null) return rec.applied_threshold;
  const m = /threshold (\d*\.\d+)/.exec(rec.reason || "");
  return m ? Number(m[1]) : null;
}

function fixRepeat(d) {
  if (d.gate && d.gate.fix_repeat) return "yes";
  const edge = d.re_entry || {};
  if (edge.fired && /fix\/repeat/i.test(edge.disclosure || "")) return "yes (disclosed)";
  return "no";
}

function showRun(i) {
  if (i !== trace.index) trace.selected = null;
  trace.index = i;
  const run = trace.runs[i];
  $$("#run-pills button").forEach((b, j) => (j === i ? b.setAttribute("aria-current", "step") : b.removeAttribute("aria-current")));
  renderTraceSummary(run);
  renderTraceTimeline(run);
  renderDecisions(run);
}

/** Calculator notes and calls, with what came before the note so it is not credited for it. */
function calcSummary(rt) {
  const plural = (n, w) => `${n ?? 0} ${w}${n === 1 ? "" : "s"}`;
  const parts = [plural(rt.calc_notes, "note"), plural(rt.calc_calls, "call")];
  if (rt.calc_calls_before_note != null) {
    parts.push(`${rt.calc_calls_before_note} before the note, ${rt.calc_calls_after_note} after`);
    if (rt.calc_loaded_before_first_note) parts.push("already loaded before the note");
  } else if (rt.calc_note_followed != null) {
    parts.push(rt.calc_note_followed ? "note followed" : "note not followed"); // older traces
  }
  if (rt.delegation_prompt_names_calc) parts.push("the delegating prompt named it");
  if (rt.interpreter_calls_calc_could_run != null) {
    parts.push(`${rt.interpreter_calls_calc_could_run} of ${plural(rt.interpreter_calls, "interpreter call")} it could run`);
  }
  return parts.join(", ");
}

/** The run facts the summary always shows; the others are under "More about this run". */
const TRACE_KEY_STATS = ["Duration", "Elapsed", "Sections written", "Failed calls", "Source checks", "Self-Audit Gate", "Chains"];

const countBy = (xs) => xs.reduce((m, x) => ({ ...m, [x]: (m[x] || 0) + 1 }), {});

/** Source checks as chips: what was read, what lacked the content, what failed (hosts on hover). */
function sourceCell(src) {
  const hosts = Object.keys(src.failed_hosts || {});
  return el("span", { class: "chips" }, chip(`${src.ok} ok`, "native"),
    src.reported_missing ? chip(`${src.reported_missing} without the content`, "gated") : null,
    src.http_error ? chip(`${src.http_error} HTTP error`, "enforce", Object.keys(src.http_error_hosts || {}).join("\n") || undefined) : null,
    src.failed ? chip(`${src.failed} failed`, "enforce", hosts.join("\n") || undefined) : null);
}

const CONTRACT_TONE = { valid: "native", unsupported_version: "gated" };

/** contract_status of the report's structured-summary block, with its violations as a tooltip. */
function contractCell(end) {
  const c = end.contract;
  if (!c) return end.analysis_sha256 ? "not read (no contract reader)" : "–";
  const found = (c.violations || []).filter((v) => v.severity !== "warning");
  const title = found.map((v) => `${v.path || "block"}: ${v.message}`).join("\n") || undefined;
  return el("span", { class: "chips" }, chip(c.contract_status, CONTRACT_TONE[c.contract_status] || "enforce", title),
    c.schema_version != null ? chip(`schema v${c.schema_version}`, "outline") : null);
}

/** Where the decisions came from: the block, or the prose fallback. */
function decisionsCell(end) {
  if (!end.decisions_source) return "–";
  const note = end.decisions_source === "block"
    ? (end.decisions_verified === false ? "block, version not verified" : "block")
    : "prose (the block could not be used)";
  return el("span", { class: "chips" }, chip(note, end.decisions_source === "block" && end.decisions_verified !== false ? "native" : "gated"));
}

/** A report on disk written before the run started belongs to another run: older traces picked
    the newest analysis in the agent's folder when the run's own report path did not resolve. */
function staleReport(run) {
  const end = run.end || {};
  return Boolean(end.analysis_mtime && run.start && end.analysis_mtime * 1000 < when(run.start.ts) - 5000);
}

function renderTraceSummary(run) {
  const box = $("#trace-summary");
  const end = staleReport(run) ? { ...run.end, decisions: null } : run.end || {};
  const d = end.decisions || {};
  const rt = end.routing || {};
  const concl = d.conclusion || {};
  const conf = concl.confidence;
  const status = (trace.sessions && trace.sessions.get(trace.data.session) || {}).status;
  const lastRec = run.recs.at(-1);
  const open = !run.end && status === "running" && trace.index === trace.runs.length - 1;
  const ran = run.start && lastRec ? clock((when(lastRec.ts) - when(run.start.ts)) / 1000) : null;
  const headline = staleReport(run) ? "Finished; this run's own report was not found"
    : run.end ? (concl.recommended || "Finished; no recommendation found in the report")
    : !run.start ? (open ? "Delegated; waiting for the agent to start" : "Delegated; the agent never started")
      : open ? `Running: ${ran} in, ${run.recs.filter((r) => r.kind === "section_written").length} sections written so far`
        : "Run not finished (no SubagentStop recorded)";
  const question = trace.data.question
    ? el("p", { class: "trace-question" }, el("b", { text: "Asked: " }), trace.data.question) : null;
  const head = el("div", { class: "verdict" },
    el("h3", { text: headline }),
    conf ? el("span", { class: `pill ${CONF_TONE[conf] || "native"}`, text: `Confidence ${conf}` }) : null);
  const deleg = rt.delegation || null;
  const delegText = !deleg ? "–" : deleg.action === "suggest"
    ? `note sent (${vsThreshold(deleg.p, deleg.applied_threshold)})` : `no note (p ${deleg.p == null ? "–" : pct(deleg.p)})`;
  const gate = d.gate || {};
  const bands = Object.entries(gate.bands || {});
  const criteria = gate.criteria || {};
  const gt = d.ground_truths || {};
  const chains = d.chains || [];
  const confCount = {};
  chains.forEach((c) => { confCount[c.confidence || "?"] = (confCount[c.confidence || "?"] || 0) + 1; });
  const stats = [
    ["Duration", minutes(end.duration_s)],
    ["Sections written", end.sections_written ?? run.recs.filter((r) => r.kind === "section_written").length],
    ["Report restarts / revisions", `${end.report_restarts ?? 0} / ${end.report_revisions ?? 0}`],
    ["References opened", el("span", { class: "chips" }, ...(end.references_read || run.recs.filter((r) => r.kind === "reference_read").map((r) => r.file))
      .map((f) => chip(f.replace(/\.md$/, ""), "native")))],
    ["Stops", end.stop_attempt ? `${end.stop_attempt}${end.stop_attempt > 1 ? " (earlier stop events)" : ""}` : "–"],
    ["Contract", contractCell(end)],
    ["Decisions from", decisionsCell(end)],
    ["Delegation", delegText],
    ["Calculator", calcSummary(rt)],
    ["Self-Audit Gate", bands.length ? el("span", { class: "chips" }, ...Object.entries(countBy(bands.map(([, b]) => b))).map(([b, n]) =>
      chip(`${n} ${b}`, BAND_TONE[b], bands.filter(([, x]) => x === b).map(([k]) => `${k}. ${criteria[k] || "Criterion"}`).join("\n")))) : "–"],
    ["Fix/Repeat", run.end ? fixRepeat(d) : "–"],
    ["Ground truths", gt.count == null ? "–" : `${gt.count}, ${(gt.unverified || []).length} not read at source`],
    ["Chains", chains.length ? el("span", { class: "chips" }, chip(String(chains.length), "native"),
      ...Object.entries(confCount).map(([c, n]) => chip(`${n} ${c}`, CONF_TONE[c]))) : "–"],
    ["Failed calls", end.tool_failures ?? run.recs.filter((r) => r.kind === "tool_failed").length],
    ["Source checks", end.sources ? sourceCell(end.sources) : "–"],
  ];
  if (!run.end) { // mid-run: only what the hooks have recorded so far
    const src = run.recs.filter((r) => r.kind === "source");
    const ok = src.filter((r) => r.outcome === "ok").length;
    stats.splice(0, stats.length,
      ["Elapsed", ran || "–"], ...stats.filter(([k]) => ["Sections written", "References opened", "Calculator", "Failed calls"].includes(k)),
      ["Source checks", src.length ? `${ok} ok, ${src.length - ok} not ok, so far` : "–"]);
  }
  // the headline numbers stay in view; the rest folds away so the chart and the log start higher
  const cell = ([k, v]) => el("div", { class: "stat" }, el("span", { class: "stat-k", text: k }), el("span", { class: "stat-v" }, v));
  const key = (k) => TRACE_KEY_STATS.includes(k);
  const grid = el("div", { class: "stats" }, ...stats.filter(([k]) => key(k)).map(cell));
  const foot = el("p", { class: "small-print" },
    `Session ${trace.data.session}, agent ${String(run.id).slice(0, 12)}. `,
    end.analysis ? el("code", { text: end.analysis }) : null);
  const rest = stats.filter(([k]) => !key(k));
  const more = el("details", { class: "facts", open: trace.factsOpen, ontoggle: (e) => { trace.factsOpen = e.target.open; } },
    el("summary", { text: `More about this run (${rest.length})` }), el("div", { class: "stats" }, ...rest.map(cell)), foot);
  if (trace.data.audit && trace.data.audit.length) head.append(el("button", { type: "button", class: "secondary replay-link",
    onclick: () => go("replay", trace.data.session), text: `Step through the router's ${trace.data.audit.length} checkpoints` }));
  const stale = staleReport(run) ? el("p", { class: "stale-report" }, chip("another run's report", "enforce"),
    ` The trace picked up ${end.analysis}, written ${new Date(end.analysis_mtime * 1000).toLocaleString()}, before this run started. Its decisions are not shown. Traces written from now on find the run's own report.`) : null;
  box.replaceChildren(...[question, head, stale, grid, more].filter(Boolean));
}

/** A shell call that runs an interpreter (``math`` in traces before 2026-09-30). */
const interp = (rec) => Boolean(rec.interpreter ?? rec.math);

/* The time chart's swimlanes: one row per kind of work, the router's notes on a row of their own. */
const LANES = [["agent", "Agent"], ["report", "Report"], ["sources", "Sources"], ["compute", "Compute"], ["router", "Router"]];
const LANE_OF = {
  delegation: "agent", run_start: "agent", tool_loaded: "agent", run_end: "agent",
  section_written: "report", report_op: "report", reference_read: "sources", source: "sources",
  calc: "compute", shell: "compute",
};
function laneOf(rec) {
  if (rec.kind !== "tool_failed") return LANE_OF[rec.kind] || "agent";
  const tool = String(rec.tool_name || "");
  if (/^Web(Fetch|Search)$/.test(tool)) return "sources";
  if (/^(Write|Edit|MultiEdit)$/.test(tool)) return "report";
  return /Bash|calc/.test(tool) ? "compute" : "agent";
}

/** Time since the agent started, for the log's first column. */
function stamp(ts, t0) {
  if (t0 == null) return "";
  const dt = (when(ts) - t0) / 1000;
  return dt < -0.5 ? "before" : `+${clock(Math.max(0, dt))}`;
}

/** One line of the event log: time, what happened, the detail (folded when it is long). */
const evRow = (cls, at, kind, ...body) => el("li", { class: `ev ${cls}`.trim() },
  el("span", { class: "ev-at", text: at }), el("span", { class: "ev-kind", text: kind }), el("div", { class: "ev-body" }, ...body));

function traceItem(rec, t0) {
  let label; let cls = ""; let body;
  switch (rec.kind) {
    case "run_start":
      label = "Agent starts"; cls = "prompt";
      body = el("span", { text: `first-principles run ${String(rec.agent_id || "").slice(0, 12)}` });
      break;
    case "reference_read":
      label = "Opens a reference";
      body = el("span", {}, el("span", { class: "tool-name", text: rec.file }), ` ${rec.meaning}`);
      break;
    case "section_written":
      label = "Writes to the report"; cls = "write";
      body = el("span", {},
        el("ul", { class: "headings" }, ...(rec.headings || []).map((h) => el("li", { text: h }))),
        rec.restarts ? chip("empties the report first", "enforce") : null,
        rec.revises ? chip("also revises earlier text", "gated") : null,
        (rec.headings || []).length ? null : el("span", { class: "muted", text: `${rec.chars} characters, no heading` }));
      break;
    case "report_op":
      label = REPORT_OP[rec.op] || "Report file"; cls = rec.op === "revise" ? "write" : "";
      body = el("details", {}, el("summary", { text: rec.op === "revise" ? "rewrites part of the report" : "command" }), el("pre", { text: rec.command }));
      break;
    case "calc":
      label = "Exact calculator"; cls = "calc";
      body = el("code", { text: `${rec.expression} = ${calcResult(rec.result)}` });
      break;
    case "shell":
      label = interp(rec) ? "Runs an interpreter" : "Shell command"; cls = interp(rec) ? "math" : "";
      body = el("details", {}, el("summary", { text: oneLine(rec.command) }), el("pre", { text: rec.command }));
      break;
    case "delegation":
      label = "Main session delegates"; cls = "prompt";
      body = el("span", { text: `prompt of ${rec.prompt_chars} characters${rec.prompt_names_calc ? ", tells the agent to use the calculator" : ""}` });
      break;
    case "source":
      label = rec.tool === "WebSearch" ? "Searches for a source" : "Checks a source";
      cls = rec.outcome === "ok" ? "" : rec.outcome === "http_error" ? "err" : "gated";
      body = el("span", {}, el("code", { text: rec.host || rec.target || "" }), httpChip(rec),
        rec.outcome === "reported_missing" ? chip("page did not have it", "gated") : null,
        rec.excerpt ? el("details", {}, el("summary", { text: "what the agent was told" }), el("pre", { text: rec.excerpt })) : null);
      break;
    case "tool_loaded":
      label = "Loads tools"; cls = rec.calc ? "calc" : "";
      body = el("code", { text: rec.query });
      break;
    case "tool_failed":
      label = `${rec.was === "calc" ? "Exact calculator" : rec.tool_name ? rec.tool_name.replace(/^mcp__.*__/, "") : "Call"} failed`; cls = "err";
      body = el("span", { text: rec.error || "" });
      break;
    case "run_end":
      label = `Agent stops after ${minutes(rec.duration_s)}${rec.stop_attempt > 1 ? ` (stop ${rec.stop_attempt})` : ""}`; cls = "answer";
      body = el("details", {}, el("summary", { text: "its final message" }), el("pre", { text: rec.final_message || "" }));
      break;
    default:
      label = rec.kind;
      body = el("details", {}, el("summary", { text: "record" }), el("pre", { text: JSON.stringify(rec, null, 1) }));
  }
  return evRow(cls, stamp(rec.ts, t0), label, body);
}

function routerItem(rec, t0) {
  const name = rec.entry_id ? optionMeta(rec.entry_id).name : "an option";
  const p = rec.entry_id ? (rec.probabilities || {})[rec.entry_id] : null;
  return evRow(`cp ${rec.action}`, stamp(rec.ts, t0), `Router ${rec.action === "enforce" ? "blocks" : "note"}`,
    `Points to ${name} on the next ${rec.tool_name || "call"}: `, el("b", { text: vsThreshold(p, appliedThreshold(rec)) || rec.reason }));
}

/** A fetch's HTTP status and page size, e.g. "200 OK · 104 KB"; traces before 2026-10-17 have none. */
function httpChip(rec) {
  if (rec.status == null) return null;
  const size = rec.bytes == null ? "" : ` · ${rec.bytes < 1024 ? `${rec.bytes} B` : `${Math.round(rec.bytes / 1024)} KB`}`;
  const tone = rec.status < 300 ? "native" : rec.status < 400 ? "gated" : "enforce";
  return chip(`${rec.status}${rec.status_text ? ` ${rec.status_text}` : ""}${size}`, tone,
    rec.status < 400 ? "HTTP status and size of the page WebFetch downloaded" : "the site refused or did not have this page");
}

/** Consecutive calculator calls, plain shell calls or checks of one source fold into one item. */
function groupItem(recs, t0) {
  if (recs[0].kind === "source") {
    const row = traceItem(recs[0], t0);
    row.querySelector(".ev-kind").textContent += ` ×${recs.length}`;
    const targets = [...new Set(recs.map((r) => r.target).filter(Boolean))];
    if (targets.length > 1) row.querySelector(".ev-body").append(el("details", {}, el("summary", { text: `${targets.length} pages` }), el("pre", { text: targets.join("\n") })));
    return row;
  }
  const calc = recs[0].kind === "calc";
  const label = calc ? `Exact calculator ×${recs.length}` : `${recs.length} shell commands`;
  const lines = recs.map((r) => (calc ? `${r.expression} = ${calcResult(r.result)}` : oneLine(r.command)));
  return evRow(calc ? "calc" : "", stamp(recs[0].ts, t0), label,
    el("details", {}, el("summary", { text: lines[0].slice(0, 90) + (recs.length > 1 ? ` … and ${recs.length - 1} more` : "") }),
      el("pre", { text: lines.join("\n") })));
}

/** The run's events in time order, consecutive calculator/shell calls folded, the router's notes interleaved. */
function runItems(run) {
  const foldable = (r) => r.kind === "calc" || r.kind === "source" || (r.kind === "shell" && !interp(r));
  // the same source checked again and again (paging through one site) is one line, not ten
  const sameAs = (a, r) => a.kind === r.kind && (r.kind !== "source"
    || (a.tool === r.tool && a.outcome === r.outcome && (a.host || a.target) === (r.host || r.target)));
  const items = [];
  for (const r of run.recs) {
    const last = items[items.length - 1];
    if (foldable(r) && last && last.group && sameAs(last.group[0], r)) last.group.push(r);
    else items.push({ ts: when(r.ts), order: 1, group: foldable(r) ? [r] : null, rec: r, lane: laneOf(r), key: `${r.ts}|${r.kind}` });
  }
  const marks = routerMarks(run).map((r) => ({ ts: when(r.ts), order: 0, router: r, lane: "router", key: `router|${when(r.ts)}` }));
  return [...items, ...marks].sort((a, b) => a.ts - b.ts || a.order - b.order);
}

/** The why-data for one run (``/api/trace/<session>/why``): the agent's messages and, per tool
    call, what it said before and after, what its prompt offered and where the result went. */
const runWhy = (run) => (trace.why && trace.why.runs && trace.why.runs[run.id]) || null;
const QUIET_S = 30; // a stretch this long without a tool call shows in the log

/** One of the agent's own messages, heading the calls that follow it. */
function intentRow(say, t0) {
  const n = el("span", { class: "n" });
  const row = el("li", { class: "ev-say", title: "Click to show the whole message" },
    el("span", { class: "ev-at", text: stamp(say.ts, t0) }), el("span", { class: "say" }, el("span", { class: "q", text: say.text }), n));
  return { row, n, count: 0 };
}

function renderTraceTimeline(run) {
  const t0 = run.start ? when(run.start.ts) : null;
  const list = runItems(run).map((x) => {
    const row = x.router ? routerItem(x.router, t0)
      : x.group && x.group.length > 1 ? groupItem(x.group, t0) : traceItem(x.rec, t0);
    row.dataset.key = x.key;
    return { ...x, row };
  });
  trace.items = list;
  const calls = (runWhy(run) || {}).calls || {};
  for (const x of list) { // a shell row says what the command is for, in the agent's words
    const r = x.rec;
    const note = r && r.kind === "shell" && !x.group?.[1] && ((calls[r.tool_use_id] || {}).purpose || r.purpose);
    const sum = note && x.row.querySelector(".ev-body summary");
    if (sum) { sum.title = sum.textContent; sum.textContent = note; sum.classList.add("noted"); }
  }
  // the agent's messages, in time order with its calls: each heads the calls made under it
  const says = ((runWhy(run) || {}).narrations || []).map((say) => ({ say, ts: when(say.ts) }))
    .filter((x) => Number.isFinite(x.ts));
  const stream = [...list, ...says].sort((a, b) => a.ts - b.ts || (b.say ? 1 : 0) - (a.say ? 1 : 0));
  const out = [];
  const heads = [];
  let prev = null;
  let head = null;
  for (const x of stream) {
    if (prev != null && x.ts - prev >= QUIET_S * 1000) {
      out.push(el("li", { class: "ev-gap", text: `${minutes((x.ts - prev) / 1000)} with no tool calls` }));
    }
    if (x.say) {
      head = intentRow(x.say, t0);
      heads.push(head);
      out.push(head.row);
    } else {
      if (head) { x.row.classList.add("child"); head.count += 1; }
      out.push(x.row);
    }
    prev = x.ts;
  }
  heads.forEach((h) => { h.n.textContent = h.count ? `${h.count} call${h.count === 1 ? "" : "s"} follow${h.count === 1 ? "s" : ""}` : "no calls follow"; });
  $("#trace-timeline").replaceChildren(...out);
  $("#trace-count").textContent = `${list.length} event${list.length === 1 ? "" : "s"}`
    + (heads.length ? ` · ${heads.length} message${heads.length === 1 ? "" : "s"}` : "");
  renderTraceChart(run, list, t0);
  if (trace.selected) selectEvent(trace.selected);
}

/** Swimlanes over the run's clock: each event a mark at its time, in the lane of its kind of work.
    A mark selects its line in the log. */
function renderTraceChart(run, list, t0) {
  const box = $("#trace-chart");
  if (!list.length) { box.replaceChildren(); return; }
  const origin = t0 ?? list[0].ts;
  const status = (trace.sessions && trace.sessions.get(trace.data.session) || {}).status;
  const live = !run.end && status === "running" && trace.index === trace.runs.length - 1;
  const last = Math.max(...list.map((x) => x.ts), run.end ? when(run.end.ts) : -Infinity, live ? Date.now() : -Infinity);
  const span = Math.max(60, (last - origin) / 1000);
  const at = (ts) => `${(Math.min(span, Math.max(0, (ts - origin) / 1000)) / span) * 100}%`;
  const step = [15, 30, 60, 120, 300, 600, 900, 1800].find((s) => span / s <= 6) || 3600;
  const ticks = [];
  for (let s = 0; s <= span + 0.001; s += step) ticks.push(s);
  const grid = () => ticks.map((s) => el("span", { class: "tc-grid", style: `left:${(s / span) * 100}%` }));
  const rows = LANES.map(([lane, name]) => {
    const here = list.filter((x) => x.lane === lane);
    const marks = here.flatMap((x) => {
      const tone = [...x.row.classList].filter((c) => c !== "ev").join(" ");
      const tip = `${x.row.querySelector(".ev-at").textContent} ${x.row.querySelector(".ev-kind").textContent}: ${x.row.querySelector(".ev-body").textContent.slice(0, 160)}`;
      return (x.group || [x.rec || x.router]).map((r) => el("span", {
        class: `mk ${tone}`.trim(), style: `left:${at(when(r.ts))}`, title: tip, "data-key": x.key,
      }));
    });
    const none = !here.length && lane === "router" ? el("span", { class: "tc-none", text: "no notes or blocks in this run" }) : null;
    return [el("span", { class: "tc-lane" }, name, el("span", { class: "n", text: here.length ? String(here.length) : "" })),
      el("div", { class: "tc-track" }, ...grid(), ...marks, none)];
  });
  const axis = el("div", { class: "tc-axis" }, ...ticks.map((s) => el("span", { class: "tc-tick", style: `left:${(s / span) * 100}%`, text: clock(s) })));
  box.replaceChildren(...rows.flat(), el("span", { class: "tc-lane tc-unit", text: "min" }), axis);
}

/** Highlight one event in the chart and the log; scroll the log to it when asked. */
function selectEvent(key, scroll = false, show = false) {
  trace.selected = key;
  $$("#trace-timeline .ev, #trace-chart .mk").forEach((n) => n.classList.toggle("on", n.dataset.key === key));
  if (show) { trace.decTab = "why"; renderDecisions(trace.runs[trace.index]); }
  if (!scroll) return;
  const pane = $("#trace-timeline");
  const row = $$(".ev", pane).find((n) => n.dataset.key === key);
  if (!row) return;
  const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  pane.scrollTo({ top: row.offsetTop - pane.clientHeight / 3, behavior: smooth ? "smooth" : "auto" });
}

function section(title, open, ...kids) {
  return el("details", { class: "decision", open }, el("summary", { text: title }), ...kids);
}

/** What the agent decided, read from its report when it stopped: one tab per part, so a long
    assumptions table does not push the rest off the page. */
function renderDecisions(run) {
  const box = $("#trace-decisions");
  const tabs = $("#trace-dec-tabs");
  const d = staleReport(run) ? null : (run.end || {}).decisions;
  const sel = trace.selected && (trace.items || []).find((x) => x.key === trace.selected);
  const why = ["why", sel ? `Why? ${sel.row.querySelector(".ev-at").textContent}` : "Why?", null, () => [whyPanel(run, sel)]];
  if (!d) {
    const heads = run.recs.filter((r) => r.kind === "section_written").flatMap((r) => r.headings || []);
    const report = ["report", "Report", heads.length || null, () => [
      el("p", { class: "muted", text: run.end ? "The report file could not be read when the agent stopped." : "Decisions are read from the report when the agent stops." }),
      ...(run.end || !heads.length ? [] : [section(`Report so far (${heads.length} headings)`, true,
        el("ol", { class: "dlist" }, ...heads.map((h) => el("li", { text: h }))))])]];
    showDecisionTabs([why, report], [], trace.decTab === "why" ? "why" : "report");
    return;
  }
  const notes = [];
  if (d.re_entry) notes.push(el("p", { class: `re-entry ${d.re_entry.fired ? "fired" : ""}` },
    chip(d.re_entry.fired ? "re-entry fired" : "no re-entry", d.re_entry.fired ? "gated" : "native"), ` ${d.re_entry.disclosure}`));
  for (const c of d.contradictions || []) notes.push(el("p", { class: "re-entry" }, chip("contradiction", "enforce"), ` ${c}`));
  if (d.run_mode) notes.push(el("p", { class: "re-entry" }, chip(`mode ${d.run_mode}`, "outline"), ` ${d.run_mode_line || ""}`));
  const a = d.assumptions || { rows: [] };
  const gt = d.ground_truths || {};
  const gate = d.gate || {};
  const panels = [
    ["assumptions", "Assumptions", a.count || 0, () => [
      el("p", { class: "chips" }, ...Object.entries(a.by_verdict || {}).map(([v, n]) => chip(`${n} ${v}`, VERDICT_TONE[v])),
        ...Object.entries(a.by_type || {}).map(([t, n]) => chip(`${n} ${t}`, "outline"))),
      el("table", { class: "dtable" },
        el("thead", {}, el("tr", {}, el("th", { text: "Assumption" }), el("th", { text: "Type" }), el("th", { text: "Verdict" }))),
        el("tbody", {}, ...(a.rows || []).map((r) => el("tr", {}, el("td", { text: r.assumption }), el("td", { text: r.type }),
          el("td", {}, chip(r.verdict || "?", VERDICT_TONE[r.verdict]))))))]],
    ["chains", "Chains", (d.chains || []).length, () => [
      el("ul", { class: "dlist" }, ...(d.chains || []).map((c) => el("li", {},
        chip(c.confidence || "?", CONF_TONE[c.confidence]), " ", el("b", { text: c.id }), c.tag ? ` ${c.tag}` : "", `: ${c.title}`)))]],
    ["gate", "Self-Audit Gate", Object.keys(gate.bands || {}).length, () => [
      el("p", { class: "small-print muted", text: `${gate.passes || 0} scoring pass${gate.passes === 1 ? "" : "es"}` }),
      el("table", { class: "dtable" }, el("tbody", {}, ...Object.entries(gate.bands || {}).map(([n, b]) => el("tr", {},
        el("td", { text: `${n}. ${(gate.criteria || {})[n] || "Criterion"}` }), el("td", {}, chip(b, BAND_TONE[b])))))),
      gate.result ? el("p", { class: "small-print", text: gate.result }) : null]],
    ["truths", "Ground truths", gt.count || 0, () => [(gt.unverified || []).length
      ? el("div", {}, el("p", { class: "small-print muted", text: `${gt.unverified.length} of ${gt.count || 0} not read at source:` }),
        el("p", { class: "chips" }, ...gt.unverified.map((g) => chip(g, "gated", "reported or unverified, not read at source"))))
      : el("p", { class: "muted", text: "Every ground truth was read at source." })]],
    ["dead", "Dead ends", (d.dead_ends || []).length, () => [
      el("ul", { class: "dlist" }, ...(d.dead_ends || []).map((x) => el("li", { text: x })))]],
    ["techniques", "Not applied", (d.techniques_not_applied || []).length, () => [
      el("ul", { class: "dlist" }, ...(d.techniques_not_applied || []).map((t) => el("li", {},
        el("b", { text: t.technique }), ` (Phase ${t.phase}): ${t.reason}`)))]],
    ["sections", "Sections", (d.sections || []).length, () => [
      el("ol", { class: "dlist" }, ...(d.sections || []).map((h) => el("li", { text: h })))]],
  ];
  showDecisionTabs([why, ...panels], notes, trace.decTab);
}

/** The tab list over the decisions pane, and the picked tab's panel (notes go above any tab but Why?). */
function showDecisionTabs(panels, notes, want) {
  const box = $("#trace-decisions");
  const tabs = $("#trace-dec-tabs");
  const pick = panels.find((p) => p[0] === want) || panels[1] || panels[0];
  tabs.hidden = false;
  tabs.replaceChildren(...panels.map(([id, name, n]) => el("button", {
    type: "button", role: "tab", id: `dtab-${id}`, "data-tab": id, "aria-controls": "trace-decisions",
    class: id === "why" ? "why-tab" : null,
    "aria-selected": id === pick[0] ? "true" : "false", tabindex: id === pick[0] ? "0" : "-1",
  }, name, n == null ? null : el("span", { class: "n", text: String(n) }))));
  box.setAttribute("role", "tabpanel");
  box.setAttribute("aria-labelledby", `dtab-${pick[0]}`);
  box.replaceChildren(...(pick[0] === "why" ? [] : notes), ...pick[3]().filter(Boolean));
}

const short = (tool) => String(tool || "this tool").replace(/^mcp__.*__/, "");

/** On a narrow screen the Why? tab sits below the log: bring it into view after a click. */
function revealWhy() {
  if (!window.matchMedia("(max-width: 1000px)").matches) return;
  const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  $("#trace-dec-tabs").scrollIntoView({ block: "start", behavior: smooth ? "smooth" : "auto" });
}

/** A ``+m:ss what`` button that selects another event in the log. */
function eventLink(x) {
  return el("button", { type: "button", class: "ev-link", onclick: () => selectEvent(x.key, true, true) },
    el("span", { class: "mono", text: x.row.querySelector(".ev-at").textContent }), " ", x.row.querySelector(".ev-kind").textContent);
}

/** Why the selected event happened: what the agent said just before it, the phase it was in, the
    router's verdict on it, what its prompt offered, the outcome and where the result went. */
function whyPanel(run, sel) {
  const t0 = run.start ? when(run.start.ts) : null;
  if (!sel) {
    return el("p", { class: "muted", text: "Select an event in the log or the chart to see why it happened: what the agent said just before it, the phase it was in, the router's verdict, what its prompt offered, and what came of it." });
  }
  const w = runWhy(run);
  const recs = sel.router ? [sel.router] : sel.group || [sel.rec];
  const first = recs[0];
  const ids = recs.map((r) => r.tool_use_id).filter(Boolean);
  const calls = ids.map((id) => w && w.calls && w.calls[id]).filter(Boolean);
  const call = calls[0] || null;
  const audit = (trace.data.audit || []).filter((a) => a.tool_use_id && ids.includes(a.tool_use_id));
  const items = trace.items || [];
  const at = items.indexOf(sel);
  const rows = [];
  const add = (k, ...v) => rows.push(el("div", { class: "why-row" }, el("b", { text: k }), el("div", { class: "why-v" }, ...v)));
  const said = (x) => el("blockquote", {}, x.text, " ", el("span", { class: "muted small-print", text: `(${stamp(x.ts, t0)})` }));
  const noTranscript = !w || (!w.transcript && !w.kept);

  // -- the cause, in one line of chips
  const chips = [];
  const pushed = audit.find((a) => ["suggest", "enforce"].includes(a.action));
  if (sel.router) chips.push(chip(sel.router.action === "enforce" ? "the router blocked a call" : "the router sent a note", sel.router.action === "enforce" ? "enforce" : "suggest"));
  else if (pushed) chips.push(chip(`router ${pushed.action === "enforce" ? "blocked" : "pointed"} here`, pushed.action === "enforce" ? "enforce" : "suggest"));
  else if ((call && (call.said || call.purpose)) || first.purpose) {
    chips.push(chip(call && call.offered_by ? "the agent chose it; its prompt offered the tool" : "the agent's own choice", "focus"));
  }
  else if (first.kind === "run_start" || first.kind === "delegation") chips.push(chip("started by the main session", "focus"));
  if (!sel.router && ids.length) chips.push(audit.length ? (pushed ? null : chip("router: no note", "native")) : chip("router did not check it", "outline"));
  const sameTool = (x) => x && x.rec && x.rec.tool_name && x.rec.tool_name === first.tool_name;
  const near = (x) => x && Math.abs(x.ts - sel.ts) <= 120000;
  if (first.kind === "tool_failed") {
    chips.push(chip("failed", "enforce"));
    const retry = items.slice(at + 1).find((x) => sameTool(x) && near(x));
    if (retry) chips.push(chip(`retried ${retry.row.querySelector(".ev-at").textContent}`, "gated"));
  }

  // -- the agent's own words
  if (first.kind === "run_start" || first.kind === "delegation") {
    const d = first.kind === "delegation" ? first : run.recs.find((r) => r.kind === "delegation");
    if (d && d.description) add("Asked to", el("span", { text: d.description }));
    if (w && w.prompt) add("Its prompt", el("details", {}, el("summary", { text: `${w.prompt.length.toLocaleString()} characters` }), el("pre", { text: w.prompt })));
    else if (d) add("Its prompt", el("span", { class: "muted", text: `${d.prompt_chars} characters${d.prompt_names_calc ? ", names the calculator" : ""}; the text is in the transcript, which is not on this machine.` }));
  } else if (first.kind === "run_end") {
    add("It said", el("details", {}, el("summary", { text: "its final message" }), el("pre", { text: first.final_message || "" })));
  } else if (sel.router) {
    add("Router", el("span", { text: `${sel.router.reason || ""}` }));
    if (sel.router.hint) add("Its note", el("pre", { class: "hint-text suggest", text: sel.router.hint }));
  } else if (call && call.said) {
    const ago = (sel.ts - when(call.said.ts)) / 1000;
    add("Agent said", said(call.said), ago >= 120
      ? el("span", { class: "muted small-print", text: `said ${minutes(ago)} before this call, with nothing since: it may not be about this call` }) : null);
  } else if (noTranscript) {
    add("Agent said", el("span", { class: "muted", text: "The agent's transcript is not on this machine, so its own words are not available. The router and phase below still are." }));
  } else if (ids.length) {
    add("Agent said", el("span", { class: "muted", text: "Nothing before this call; it was among its first steps." }));
  }
  const purpose = (call && call.purpose) || first.purpose; // the trace keeps it too
  if (purpose) add(short(first.tool_name) === "WebFetch" ? "Looking for" : "Its note", el("span", { class: "purpose", text: purpose }),
    el("span", { class: "muted small-print", text: "written by the agent on the call itself" }));
  if (call && call.thinking) add("Reasoning", el("details", {}, el("summary", { text: "its reasoning in that turn" }), el("pre", { text: call.thinking })));

  // -- the phase: the last reference opened, and a quiet stretch just before
  const ref = run.recs.filter((r) => r.kind === "reference_read" && when(r.ts) <= sel.ts).at(-1);
  const before = at > 0 ? items[at - 1] : null;
  const quiet = before ? (sel.ts - before.ts) / 1000 : 0;
  if (ref || quiet >= 20) {
    add("Phase", el("span", {}, ref ? el("span", {}, "after ", el("code", { text: ref.file }), ref.meaning ? ` (${ref.meaning})` : "") : null,
      quiet >= 20 ? `${ref ? "; " : ""}${minutes(quiet)} since the previous call (${before.row.querySelector(".ev-at").textContent})` : null));
  }

  // -- the router's checkpoint on this call
  if (!sel.router && ids.length) {
    // the router's checks in this run: the one on this call, else the last one before it
    const runAudit = (trace.data.audit || []).filter((a) => a.agent_id === run.id || (a.agent_type && !a.agent_id));
    // in plain words: "skipped" / "native" mean the router had nothing to suggest for that call
    const plain = { skipped: "no suggestion", native: "no suggestion", suggest: "sent a note", enforce: "blocked it", gated: "below its threshold" };
    const cpLine = (a) => el("span", { class: "why-line", title: a.reason || "" }, chip(plain[a.action] || a.action, ACTION_TONE[a.action] || "native"),
      a.entry_id && ["suggest", "enforce"].includes(a.action) ? ` ${optionMeta(a.entry_id).name}` : "",
      ["skipped", "native"].includes(a.action) ? el("span", { class: "muted small-print", text: " none of its approved tools fit that call" }) : ` ${a.reason || ""}`);
    const lastCp = runAudit.filter((a) => when(a.ts) <= sel.ts && a.point === "tool").at(-1);
    const lastAt = lastCp ? items.find((x) => (x.group || [x.rec]).some((r) => r && r.tool_use_id === lastCp.tool_use_id)) : null;
    const notes = runAudit.filter((a) => ["suggest", "enforce"].includes(a.action)).length;
    add("Router", ...(audit.length ? audit.slice(0, 2).map(cpLine) : [
      el("span", { text: `Not checked: the router's hooks did not fire on ${short(first.tool_name)}, so it had no say in this call.` }),
      lastCp ? el("span", { class: "why-line muted" }, "Its last check was on an earlier, different call: ", lastAt ? eventLink(lastAt) : `${stamp(lastCp.ts, t0)} ${lastCp.tool_name || ""}`, " ", cpLine(lastCp)) : null]),
    el("span", { class: "muted small-print", text: notes ? `${notes} router note${notes === 1 ? "" : "s"} or block${notes === 1 ? "" : "s"} in this run, shown as Router lines in the log.` : "The router sent no notes and blocked nothing in this whole run." }));
  }

  // -- what the prompt offered
  if (call && call.offered_by) add("Prompt offered", el("blockquote", { class: "quiet" }, call.offered_by), el("span", { class: "muted small-print", text: "a line of the prompt that started this agent" }));

  // -- what the call was given (the result row shows it for a successful calculator call)
  const input = first.kind === "tool_failed" ? first.expression || first.command : first.kind === "shell" ? first.command : null;
  if (input) add("Input", el("pre", { text: input }), String(input).length >= 290
    ? el("span", { class: "muted small-print", text: "cut short in the trace" }) : null);

  // -- the outcome
  if (first.kind === "tool_failed") add("Outcome", el("span", { text: first.error || "failed" }));
  else if (first.kind === "calc") add("Result", el("pre", { text: recs.map((r) => `${r.expression}\n→ ${calcResult(r.result)}`).join("\n\n") }));
  if (first.kind !== "tool_failed" && sameTool(sel)) {
    const failed = items.slice(0, at).reverse().find((x) => x.rec && x.rec.kind === "tool_failed" && sameTool(x) && near(x));
    if (failed) add("Retry of", eventLink(failed));
  } else if (first.kind === "tool_failed") {
    const retry = items.slice(at + 1).find((x) => sameTool(x) && near(x));
    if (retry) add("Retried", eventLink(retry));
  }
  if (call && call.said_after && (!call.said || call.said_after.ts !== call.said.ts)) add("Next it said", said(call.said_after));

  // -- where a calculator result went
  const used = new Map();
  calls.forEach((c) => (c.used_in || []).forEach((u) => {
    const prior = used.get(u.tool_use_id) || [];
    used.set(u.tool_use_id, [...new Set([...prior, ...u.numbers])]);
  }));
  if (used.size) { // one line per log row, in time order (a folded row can hold several calls)
    const byRow = new Map();
    for (const [id, nums] of used) {
      const x = items.find((y) => (y.group || [y.rec || y.router]).some((r) => r && r.tool_use_id === id));
      if (x) byRow.set(x, [...new Set([...(byRow.get(x) || []), ...nums])]);
    }
    add("Used in", el("ul", { class: "used" }, ...[...byRow.entries()].sort((a, b) => a[0].ts - b[0].ts).map(([x, nums]) =>
      el("li", {}, eventLink(x), " ", el("span", { class: "chips" }, ...nums.slice(0, 5).map((n) => chip(n, "outline")))))),
    el("p", { class: "muted small-print", text: "Later calls whose input repeats a number from this result. A match, not proof." }));
  }

  return el("div", { class: "why" },
    el("div", { class: "why-head" }, el("h3", {}, el("span", { class: "mono", text: sel.row.querySelector(".ev-at").textContent }), " ", sel.row.querySelector(".ev-kind").textContent),
      el("div", { class: "chips" }, ...chips.filter(Boolean))),
    ...rows);
}

function initTrace() {
  $("#trace-select").addEventListener("change", (e) => { trace.pinned = true; setAddress("trace", e.target.value, true); loadTrace(e.target.value); });
  $("#trace-refresh").addEventListener("click", () => loadTraceSessions($("#trace-select").value));
  $("#trace-follow").addEventListener("change", () => { renderLiveLine(); if ($("#trace-follow").checked) pollTrace(); });
  // a mark in the chart selects its line in the log; a line in the log lights its marks
  $("#trace-chart").addEventListener("click", (e) => {
    const mk = e.target.closest(".mk");
    if (mk) { selectEvent(mk.dataset.key, true, true); revealWhy(); }
  });
  $("#trace-timeline").addEventListener("click", (e) => {
    const say = e.target.closest(".ev-say");
    if (say) { say.classList.toggle("open"); return; }
    const row = e.target.closest(".ev");
    if (row && !e.target.closest("summary, pre")) { selectEvent(row.dataset.key, false, true); revealWhy(); }
  });
  $("#trace-timeline").addEventListener("keydown", (e) => { // with the log focused, arrows move the selection
    if (!["ArrowDown", "ArrowUp"].includes(e.key)) return;
    const rows = $$("#trace-timeline .ev");
    if (!rows.length) return;
    e.preventDefault();
    const i = rows.findIndex((r) => r.dataset.key === trace.selected);
    const j = i < 0 ? 0 : Math.max(0, Math.min(rows.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)));
    selectEvent(rows[j].dataset.key, true, true);
  });
  $("#trace-timeline").addEventListener("mouseover", (e) => {
    const key = (e.target.closest(".ev") || {}).dataset?.key;
    $$("#trace-chart .mk").forEach((m) => m.classList.toggle("hot", m.dataset.key === key));
  });
  $("#trace-timeline").addEventListener("mouseleave", () => $$("#trace-chart .mk.hot").forEach((m) => m.classList.remove("hot")));
  const tabs = $("#trace-dec-tabs");
  const pickTab = (btn) => {
    if (!btn) return;
    trace.decTab = btn.dataset.tab;
    renderDecisions(trace.runs[trace.index]);
    $(`#dtab-${trace.decTab}`).focus();
  };
  tabs.addEventListener("click", (e) => pickTab(e.target.closest("[role=tab]")));
  tabs.addEventListener("keydown", (e) => { // arrow keys move between tabs, as in any tab list
    const all = $$("[role=tab]", tabs);
    const i = all.indexOf(document.activeElement);
    const to = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: all.length - 1 }[e.key];
    if (i < 0 || to == null) return;
    e.preventDefault();
    pickTab(all[(to + all.length) % all.length]);
  });
  // poll only while the Trace tab is on screen with Follow live on; a hidden browser tab skips
  trace.timer = setInterval(() => {
    if ($("#view-trace").hidden || !$("#trace-follow").checked || document.visibilityState !== "visible") return;
    if (trace.polling) return;
    trace.polling = true;
    pollTrace().finally(() => { trace.polling = false; });
  }, TRACE_POLL_MS);
}

/* -- tabs & boot ---------------------------------------------------------------- */

const TABS = { play: "Playground", live: "Live agent", replay: "Replay", trace: "Trace" };

/** Show a tab and, on Replay and Trace, a session (the one already shown when none is named).
    The address follows: ``#trace/<session id>``, so refresh, back and a shared link land there. */
function selectTab(name, { session = null, push = false } = {}) {
  for (const key of Object.keys(TABS)) {
    const on = key === name;
    $(`#tab-${key}`).setAttribute("aria-selected", on ? "true" : "false");
    $(`#view-${key}`).hidden = !on;
  }
  if (name === "replay" && (session ? session !== replay.session : !replay.records.length)) loadSessions(session);
  if (name === "trace" && (session ? !trace.data || session !== trace.data.session : !trace.data)) {
    if (session) trace.pinned = true; // a link to a session: follow-live must not switch away from it
    loadTraceSessions(session);
  }
  setAddress(name, session || shownSession(name), push);
}

/** Go to a tab (and session) the way a link does: one step the back button undoes. */
const go = (name, session = null) => selectTab(name, { session, push: true });

const shownSession = (tab) => (tab === "replay" ? replay.session : tab === "trace" && trace.data ? trace.data.session : null);

/** ``#replay/<id>``: the tab, then the session it shows. */
const sessionAddress = (tab, session) => `#${tab}${session ? `/${encodeURIComponent(session)}` : ""}`;

function setAddress(tab, session, push = false) {
  const want = sessionAddress(tab, session);
  if (location.hash !== want) history[push ? "pushState" : "replaceState"](null, "", want);
}

function readAddress() {
  const [tab, ...rest] = location.hash.slice(1).split("/");
  return { tab: TABS[tab] ? tab : "play", session: rest.length ? decodeURIComponent(rest.join("/")) || null : null };
}

/** Back, forward, an edited or pasted address, or a plain ``#replay/<id>`` link. */
function followAddress() {
  const { tab, session } = readAddress();
  selectTab(tab, { session });
}

async function boot() {
  for (const key of Object.keys(TABS)) $(`#tab-${key}`).addEventListener("click", () => go(key));
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
  initTrace();
  followAddress();
  window.addEventListener("popstate", followAddress); // also fires for a plain #trace/<id> link
}

boot().catch((err) => {
  $("#board").replaceChildren(el("p", { class: "board-empty", text: `Could not reach the demo server: ${err.message}` }));
});
