# agent-router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an MIT router that, at each hook point of a Claude Agent SDK agent, asks a Jev-spec classifier whether an MIT alternative from a fixed catalog fits, plus a visual demo.

**Architecture:** Host-agnostic `core/` (types, catalog, router, audit, hints) + pluggable `deciders/` implementing Jev's `choice` contract + thin `adapters/claude_sdk.py` mapping SDK hooks. Demo = FastAPI + single static HTML page with a zero-cost playground, live agent timeline (SSE) and audit replay.

**Tech Stack:** Python 3.11, uv, claude-agent-sdk 0.2.160, model2vec (potion-base-8M), numpy, pyyaml, jmespath, markdownify, FastAPI/uvicorn, httpx, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-09-26-agent-router-design.md`

## Global Constraints

- License of this repo: MIT. Catalog entries: `license: MIT` only (loader enforces).
- `src/agent_router/core/**` and `src/agent_router/deciders/**` MUST NOT import `claude_agent_sdk`.
- Decider output: `choice ∈ options`; `sum(probabilities) == 1 ± 1e-6`; `0 ≤ confidence ≤ 1`; `none` always present.
- Hints/deny reasons are rendered ONLY from catalog fields via `core/hints.py`; never model text.
- Unit tests run offline and deterministically (no network, no model download). Use markers `model` (needs potion weights) and `live` (real SDK) for the rest.
- Python ≥3.11, use `.venv/bin/python` / `uv run`; lint with `ruff check` and `ruff format`.
- Commit after each task with a conventional message ending in
  `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Do not modify files owned by another task (see Files lists). Foundation files are frozen
  except via the task that names them.

---

### Task 1: Foundation (DONE by lead)

**Files:** `pyproject.toml`, `.gitignore`, `src/agent_router/core/types.py`,
`src/agent_router/core/catalog.py`, `src/agent_router/deciders/base.py`,
`src/agent_router/catalog.yaml`

**Produces:**
- `types.py`: `NONE_ID="none"`, `HookPoint{PROMPT,TOOL,SKILL}`, `Action{SUGGEST,ENFORCE,NATIVE,SKIPPED}`,
  `OptionSpec(what, not_for, examples)`, `ChoiceResult(choice, probabilities, confidence, backend, latency_ms)`,
  `RouterEvent(point, session_id, turn_id, text, tool_name, tool_input, recent)`,
  `Decision(action, reason, entry_id, hint, result, options)`.
- `catalog.py`: `CatalogEntry(... .option() -> OptionSpec)`, `Catalog(version, entries, native_examples)`
  with `.get(id)`, `.eligible(point, tool_name)`, `.owns_target(tool_name, skill)`;
  `load_catalog(path=DEFAULT_CATALOG)`, `CatalogError`.
- `deciders/base.py`: `Decider` protocol (`name`, `decide(state, options) -> ChoiceResult`),
  `DeciderError`, `MAX_OPTIONS=255`.

- [ ] Add `tests/test_catalog.py`: default catalog loads 5 entries; non-MIT entry → `CatalogError`;
  `id: none` → error; duplicate id → error; `eligible(TOOL,"Bash")` excludes `commit-writer`;
  `eligible(SKILL,"Skill") == [commit-writer]`; `owns_target("mcp__agent_router__calc")`.

### Task 2: Local Jev-spec decider

**Files:** Create `src/agent_router/deciders/embedders.py`, `src/agent_router/deciders/local.py`,
`tests/test_local_decider.py`

**Interfaces:**
- Consumes: `OptionSpec`, `ChoiceResult`, `NONE_ID`, `Decider`, `DeciderError`.
- Produces:
  - `class Embedder(Protocol): def encode(self, texts: list[str]) -> np.ndarray` (L2-normalised rows).
  - `class HashingEmbedder` (deterministic, numpy only: lowercase, word unigrams+bigrams and
    char 3–5-grams hashed into 2**14 dims, sublinear tf, L2 norm).
  - `class Model2VecEmbedder(model="minishlab/potion-base-8M")` (lazy load, normalised).
  - `def default_embedder() -> Embedder` (Model2Vec; falls back to Hashing if load fails, logging a warning).
  - `@dataclass class LocalParams: alpha=0.8, none_floor=0.35, temperature=0.07, not_for_penalty=0.5`
  - `class LocalJevDecider(embedder=None, params=None, native_examples=())` with `name="local"`
    and `decide(state, options) -> ChoiceResult`.

**Algorithm (spec §Local decider):**
1. Validate: `NONE_ID in options`, `len(options) <= MAX_OPTIONS` else `DeciderError`.
2. For each non-none option: dense = max cosine(state, [what, *examples]); lexical = Jaccard of
   content tokens (lowercased, stopwords removed) between state and best-matching exemplar;
   score = alpha*dense + (1-alpha)*lexical; nf = max cosine(state, not_for) — if nf > dense,
   score -= not_for_penalty*(nf-dense).
3. none score = max(none_floor, max cosine(state, native_examples)) (none option's own `what`/`examples` also count if given).
4. probabilities = softmax(scores/temperature) over all options (dict keyed by option id, sum 1).
5. choice = argmax; confidence = 1 - H(p)/log(n) (n = number of options; n==1 → 1.0).
6. Cache exemplar embeddings per (option id, text) to keep latency low. Record latency_ms.

- [ ] Tests (HashingEmbedder only, offline): contract (choice ∈ options, sum==1, conf in [0,1]);
  missing none → DeciderError; 256 options → DeciderError; "compute 2**200 exactly" picks
  `exact-calc` from the real catalog options; "git status" picks `none` when native_examples given;
  deterministic across two calls; not_for penalty lowers a matching option's probability.
- [ ] Test marked `@pytest.mark.model`: Model2VecEmbedder returns (n, d) normalised rows.
- [ ] Commit `feat(decider): local Jev-spec classifier with abstention`.

### Task 3: Catalog tools, MCP server and MIT skill

**Files:** Create `src/agent_router/tools/calc.py`, `tools/json_query.py`, `tools/html_to_markdown.py`,
`tools/repo_stats.py`, `src/agent_router/adapters/claude_tools.py`,
`demo_workspace/.claude/skills/commit-writer/SKILL.md`, demo fixtures under `demo_workspace/`
(`data/orders.json`, `docs/release.html`, a few small source files), `tests/test_tools.py`

**Interfaces:**
- Produces pure functions (no SDK import) returning `str`:
  - `calc.evaluate(expression: str) -> str` — safe AST evaluator (no eval/exec): ints, Fractions,
    `+ - * / // % **`, unary, parentheses, `%` postfix handled as "N% of M" helper
    `percent_of`, functions `sqrt, factorial, gcd, lcm, abs, round, comb, perm`; exact Fraction
    results printed as `a/b (≈ decimal)`; exponent guard (|exp| ≤ 10000); raises `ValueError`.
  - `json_query.query(expression: str, path: str | None = None, text: str | None = None, root: Path) -> str`
    (jmespath; path resolved inside `root`, reject escapes; pretty JSON output).
  - `html_to_markdown.convert(path: str | None = None, html: str | None = None, root: Path) -> str`
    (markdownify, strip script/style, ATX headings).
  - `repo_stats.stats(path: str = ".", root: Path) -> str` (files+lines per language by extension,
    skip .git/.venv/node_modules/__pycache__, top 5 largest files; markdown table output).
- `adapters/claude_tools.py`: `SERVER_NAME = "agent_router"`,
  `build_mcp_server(root: Path) -> McpSdkServerConfig` via `create_sdk_mcp_server` with tools
  `calc(expression)`, `json_query(expression, path?, text?)`, `html_to_markdown(path?, html?)`,
  `repo_stats(path?)`; each returns `{"content":[{"type":"text","text":...}]}` and on error
  `{"content":[...], "is_error": True}`. `TOOL_NAMES = [f"mcp__agent_router__{n}" ...]`.
- SKILL.md frontmatter: `name: commit-writer`, `description:` (Conventional Commits writer), license MIT line in body.

- [ ] Tests for each pure function incl. security: `calc.evaluate("__import__('os')")` raises;
  `2**100000` raises; path traversal `../../etc/passwd` rejected; exact `3/7+5/11 == "68/77 (≈ 0.8831168831)"`.
- [ ] Test `build_mcp_server` returns a config dict with `type == "sdk"` and name `agent_router`.
- [ ] Commit `feat(tools): MIT catalog tools, in-process MCP server and commit-writer skill`.

### Task 4: Router, hints and audit

**Files:** Create `src/agent_router/core/router.py`, `core/hints.py`, `core/audit.py`, `core/config.py`,
`tests/test_router.py`

**Interfaces:**
- `config.py`: `@dataclass RouterConfig(mode: Literal["advisory","enforce"]="advisory", threshold: float=0.5,
  enabled: bool=True, audit_path: Path|None=None, points: tuple[HookPoint,...]=all)`;
  `RouterConfig.from_env()` reading `AGENT_ROUTER_MODE`, `AGENT_ROUTER_THRESHOLD`,
  `AGENT_ROUTER_DISABLED`, `AGENT_ROUTER_AUDIT`.
- `hints.py`: `render_hint(entry: CatalogEntry, point: HookPoint, prob: float) -> str` and
  `render_deny(entry, tool_name) -> str`. Hint template:
  `"[agent-router] An MIT-licensed alternative may fit this step: {name} ({project}, MIT) — {what} {how} Optional: ignore it if your current approach is better."`
  where `how` = `"Call tool {target}."` for tools or `"Invoke the Skill tool with skill=\"{target}\"."` for skills.
  Deny: `"[agent-router] Blocked {tool_name}: {name} ({project}, MIT) fits this step. {how}"`.
  All fields come from the entry; strip newlines; cap 400 chars.
- `audit.py`: `class AuditLog(path: Path|None)`; `.record(event, decision, catalog_version, config) -> dict`
  appends one JSON line (fields per spec §Audit) and returns it; `.subscribe(callback)` for live
  listeners (used by demo); `read_audit(path) -> list[dict]`. Keep `state_sha256`, `text` truncated to 300 chars.
- `router.py`: `class Router(catalog: Catalog, decider: Decider, config: RouterConfig|None=None, audit: AuditLog|None=None)`
  with `route(event: RouterEvent) -> Decision`. Rules in order:
  1. disabled or point not enabled → SKIPPED("disabled").
  2. loop guard: `catalog.owns_target(tool_name, skill=tool_input.get("skill"))` or tool_name starts
     with `mcp__agent_router__` → SKIPPED("own tool").
  3. options = eligible entries; none → SKIPPED("no eligible entries").
  4. state = `build_state(event)`: prompt text; for TOOL/SKILL: `"{text}\npending {tool_name}: {compact json of tool_input, 500 chars}"`; plus up to 3 `recent` lines prefixed `previous:`.
  5. `decider.decide(state, {id: entry.option()} | {none: OptionSpec("the agent's own tools are enough")})`;
     any exception → NATIVE("decider error: ...") (fail open).
  6. choice not in options (defensive) → coerce to none.
  7. choice == none or p < threshold → NATIVE.
  8. already suggested (session, turn, entry) → SKIPPED("already suggested this turn").
  9. enforce mode and point is TOOL → ENFORCE with `render_deny`; else SUGGEST with `render_hint`.
  Every route() call writes one audit record (including SKIPPED).
- [ ] Tests with a `FakeDecider` returning scripted ChoiceResults: each rule 1–9; hint contains only
  catalog text (assert a decider-injected string never appears); decider exception → NATIVE;
  unknown choice → NATIVE; audit line count == calls; enforce only at TOOL (PROMPT stays SUGGEST).
- [ ] Commit `feat(router): gated routing, templated hints and JSONL audit`.

### Task 5: Optional backends and adapter docs

**Files:** Create `src/agent_router/deciders/typesafe.py`, `deciders/semantic_router_backend.py`,
`deciders/registry.py`, `docs/adapters.md`, `tests/test_backends.py`

**Interfaces:**
- `TypeSafeJevDecider(api_key=None, model="jev-latest", base_url="https://api.typesafe.ai", timeout=2.0, client: httpx.Client|None=None)`,
  `name="jev"`. POST `/v1/systemone` body `{"state": state, "model": model, "questions": {"route": {"type":"choice","instructions": "Which catalog tool, if any, fits this agent step? Choose none if the agent's own tools are enough.", "criteria": {id: {"what":..., "not_for":[...], "examples":[...]}}}}}`,
  header `Authorization: Bearer`. Parse `answers.route.{choice,probabilities,confidence}`. Non-2xx / missing key → `DeciderError`.
- `SemanticRouterDecider(encoder=None)`, `name="semantic-router"`: import `semantic_router` lazily
  (raise `DeciderError("pip install agent-router[semantic-router]")` if absent); build routes from
  examples+what; use its local `TfidfEncoder` fitted on the utterances by default (no network);
  convert per-route similarity scores into the Jev contract (softmax incl. none floor 0.35/T 0.07).
- `registry.py`: `available_backends() -> dict[str, bool]`, `make_decider(name: str, catalog: Catalog) -> Decider`
  for `local` (passes `catalog.native_examples`), `semantic-router`, `jev`.
- `docs/adapters.md`: mapping table RouterEvent ↔ Claude Agent SDK (`UserPromptSubmit`, `PreToolUse`
  incl. `Skill`), Codex CLI (`UserPromptSubmit`, `PreToolUse`, stdin/stdout JSON), Gemini CLI
  (`BeforeAgent`, `BeforeTool`), with a 20-line stdin/stdout shim sketch.
- [ ] Tests: Jev backend with `httpx.MockTransport` (request body shape, parse, 422 → DeciderError, no key → DeciderError);
  semantic-router test `pytest.importorskip("semantic_router")`; registry lists `local` as available.
- [ ] Commit `feat(deciders): hosted Jev and semantic-router backends behind one contract`.

### Task 6: Claude Agent SDK adapter and inner agent runner

**Depends on:** Tasks 2–4. **Files:** Create `src/agent_router/adapters/claude_sdk.py`,
`src/agent_router/agent.py`, `tests/test_claude_adapter.py`, `tests/test_live.py`

**Interfaces:**
- `class ClaudeRouterHooks(router: Router)`: tracks `turn_id` per session (increments on each
  UserPromptSubmit) and the last prompt per session (for TOOL/SKILL state and `recent`).
  - `async on_user_prompt(input, tool_use_id, context) -> dict`
  - `async on_pre_tool_use(input, tool_use_id, context) -> dict` (tool_name `Skill` → HookPoint.SKILL)
  - `hooks() -> dict[str, list[HookMatcher]]` for `ClaudeAgentOptions.hooks`.
  - `on_decision(callback)` for demo streaming.
  - Output: SUGGEST → `{"hookSpecificOutput":{"hookEventName":..., "additionalContext": hint}}`;
    ENFORCE → `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason": hint}}`;
    else `{}`.
- `agent.py`: `build_options(router, workspace: Path, model: str = "claude-haiku-4-5-20251001", max_turns=8) -> ClaudeAgentOptions`
  (setting_sources=["project"], cwd=workspace, mcp_servers={"agent_router": build_mcp_server(workspace)},
  allowed_tools = TOOL_NAMES + ["Skill","Read","Glob","Grep","Bash","WebFetch"], permission_mode="default";
  never `bypassPermissions`. Listed tools run without prompts; the demo runs the agent in a disposable
  temp copy of `demo_workspace/`);
  `async run_agent(prompt, router, workspace, on_event) -> str` streaming AssistantMessage text/tool_use
  and ResultMessage to `on_event(dict)`.
- [ ] Unit tests call hook methods with fake input dicts (no SDK session): prompt → additionalContext;
  Bash `python3 -c "print(2**200)"` → hint for exact-calc; Skill `release-notes` + commit prompt → hint for commit-writer;
  own tool → `{}`; enforce mode → deny.
- [ ] `@pytest.mark.live` test: real run on a temp copy of demo_workspace with prompt
  "What is 2**200 exactly?" asserts an audit record with action suggest/enforce and a ToolUse of
  `mcp__agent_router__calc` appeared.
- [ ] Commit `feat(adapter): Claude Agent SDK hooks and inner agent runner`.

### Task 7: Eval set, calibration and CLI

**Depends on:** Tasks 2, 4. **Files:** Create `evals/eval_set.yaml`, `src/agent_router/evaluate.py`,
`src/agent_router/cli.py`, `tests/test_eval.py`

- `eval_set.yaml`: ≥60 cases `{text, point, tool_name?, tool_input?, expected}` with ≥8 positives per
  entry written differently from catalog examples, ≥20 negatives (`expected: none`), ≥5 decoys
  (near-miss e.g. "plot a graph of sales", "validate this JSON schema").
- `evaluate.py`: `run_eval(router_factory, cases) -> EvalReport(accuracy, fpr, per_entry, confusions)`;
  `calibrate(cases, grid) -> LocalParams, threshold` (grid-search none_floor×temperature×threshold,
  objective = accuracy subject to FPR ≤ 0.10); results written to `src/agent_router/calibration.json`
  and loaded by `LocalJevDecider` defaults when present.
- `cli.py` (`agent-router`): `route "text" [--point --tool --backend --json]`, `eval [--backend]`,
  `calibrate`, `demo [--port 8765]`, `run "prompt"` (live agent, prints timeline).
- [ ] `@pytest.mark.model` test: eval with calibrated local decider: accuracy ≥ 0.85, FPR ≤ 0.10.
- [ ] Offline test: CLI `route` with `--backend local --embedder hashing` returns JSON with choice.
- [ ] Commit `feat(eval): labeled eval set, calibration and CLI`.

### Task 8: Visual demo

**Depends on:** Tasks 5–7. **Files:** Create `src/agent_router/demo/server.py`,
`src/agent_router/demo/static/index.html`, `tests/test_demo_server.py`

- API: `GET /api/catalog`, `GET /api/backends`, `POST /api/route {text, point, tool_name?, tool_input?, backend}` →
  `{decision, result, options, hint, latency_ms}`, `GET /api/run?prompt=...&mode=advisory|enforce` (SSE: events
  `hook`, `decision`, `assistant`, `tool_use`, `result`, `error`, `done`), `GET /api/audit/sessions`,
  `GET /api/audit/{session}`.
- UI (single file, no build, works offline except optional Google Fonts): three tabs
  Playground / Live agent / Replay. Playground shows per-option probability bars incl. `none`,
  threshold line, chosen option, rendered hint, backend compare (run all available backends side-by-side).
  Live shows a vertical timeline: prompt → hook point card (point, tool, decision, bars) → tool calls →
  answer. Replay steps through audit records. Preset example prompts for each hook point.
  Light/dark via prefers-color-scheme. Responsive ≥400px.
- [ ] TestClient tests for `/api/catalog`, `/api/route` (hashing embedder via env
  `AGENT_ROUTER_EMBEDDER=hashing`), `/api/backends`, audit endpoints with a temp audit file.
- [ ] Commit `feat(demo): playground, live agent timeline and audit replay UI`.

### Task 9: Docs, Makefile, verification, PR

**Files:** `README.md`, `Makefile`, `docs/architecture.md` (mermaid), `docs/research.md` (survey
with arxiv ids), `audit/sample-session.jsonl`, `docs/plans/2026-09-26-agent-router-TODO.md`

- Makefile targets: help, venv, install, clean, test, test-model, test-live, lint, format, eval,
  calibrate, run (demo server), route.
- Run full verification: `make lint test test-model`, `make eval`, one live run recorded to
  `audit/sample-session.jsonl`, screenshots of demo.
- Push branch, open PR to `main`.
