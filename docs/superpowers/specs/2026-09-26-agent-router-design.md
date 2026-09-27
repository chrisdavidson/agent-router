# agent-router — Design Spec

Status: approved decisions (2026-09-26) · License: MIT

## Goal

An MIT-licensed router embedded in an "inner" Claude agent built with the Claude Agent SDK
(Python). At each interception point (user prompt, native tool call, skill invocation) the
router asks a **decision model** whether an MIT-licensed open-source alternative from a
**fixed catalog** fits. The decision model is a pure classifier: it can only return a catalog
id or `none`. It never writes a tool call or an instruction for the agent.

Inspired by Tenjin (BackTrackCo/tenjin-agent, non-MIT, design ideas only, no code reused),
which asks TypeSafe's hosted **Jev** model the same question.

## Decisions

| Fork | Decision |
|---|---|
| Decision model | Own classifier built to Jev's `choice` spec (default, offline, MIT). Pluggable backends: `semantic-router` (MIT, optional extra) and hosted Jev (opt-in via `TYPESAFE_API_KEY`). |
| On match | Advisory by default (templated `additionalContext` hint). `mode: enforce` denies the native tool at PreToolUse with a templated reason. |
| Catalog | Offline, runnable MIT dev tools + one MIT skill. |
| Language | Python 3.11+, uv, pytest, ruff, FastAPI demo. |

## The Jev contract (what every decider implements)

Mirrors `POST https://api.typesafe.ai/v1/systemone` with a `choice` question
(docs.typesafe.ai/primitives/choice.md):

```
decide(state: str, options: dict[id, OptionSpec]) -> ChoiceResult
ChoiceResult = { choice: str, probabilities: {id: float} (sum=1), confidence: float 0..1 }
```

- `options` always includes `none` (Jev has no built-in abstention; its docs say add one).
- ≤255 options. `choice` ∈ options, always. Anything else is coerced to `none` by the router.
- `OptionSpec` = `{what, not_for, examples}` (Jev's structured-criteria form).

## Architecture

```
            ┌──────────────── inner Claude (claude-agent-sdk) ────────────────┐
 prompt ──▶ │ UserPromptSubmit hook ─┐                                        │
            │ PreToolUse hook (Bash, │  adapters/claude_sdk.py (thin)          │
            │   WebFetch, Read, Skill)┘          │                            │
            └────────────────────────────────────┼────────────────────────────┘
                                                 ▼ RouterEvent
                          core/router.py  Router.route(event) -> Decision
                            1. gates: disabled? own tool? already suggested this turn?
                            2. eligible options = catalog ∩ hook point ∩ replaces(tool)
                            3. decider.decide(state, options + none) -> ChoiceResult
                            4. accept iff choice≠none ∧ p(choice) ≥ threshold
                            5. hint = template(catalog entry)   (never model text)
                            6. audit.jsonl ← record
                                                 │
                     deciders/local.py (default) │ semantic_router.py │ typesafe.py
```

`core/` must not import `claude_agent_sdk`. Adapters translate host events to/from
`RouterEvent`/`Decision`. MVP ships the Claude SDK adapter; Codex CLI and Gemini CLI hook
mappings are documented in `docs/adapters.md`.

### Types (`core/types.py`)

- `HookPoint = prompt | tool | skill`
- `RouterEvent{point, session_id, turn_id, text, tool_name?, tool_input?, recent: list[str]}`
- `ChoiceResult{choice, probabilities, confidence, backend, latency_ms}`
- `Decision{action: suggest|enforce|native|skipped, entry_id?, hint?, result?, reason}`

### Catalog (`catalog.yaml`, `core/catalog.py`)

Entry: `id, kind (tool|skill), name, project, license, url, what, not_for, examples[],
points[], replaces[], target` (MCP tool name or skill name). The loader **rejects any entry
whose license is not `MIT`** and validates the schema. `none` is reserved.

Demo catalog (all verified MIT):

| id | kind | target | backs onto | replaces |
|---|---|---|---|---|
| `exact-calc` | tool | `mcp__agent_router__calc` | own code (MIT) | Bash (python -c, bc) |
| `json-query` | tool | `mcp__agent_router__json_query` | jmespath (MIT) | Bash (jq/python), Read |
| `html-to-markdown` | tool | `mcp__agent_router__html_to_markdown` | markdownify (MIT) | Read, WebFetch, Bash |
| `repo-stats` | tool | `mcp__agent_router__repo_stats` | own code (MIT) | Bash (wc/find/cloc), Glob |
| `commit-writer` | skill | `commit-writer` | own skill (MIT) | Skill (other skills), prompt |

### Local Jev-spec decider (`deciders/local.py`)

- Embedder: model2vec `minishlab/potion-base-8M` (MIT, numpy-only). Tests use a
  deterministic `HashingEmbedder` (char n-gram, numpy) so they run offline.
- Per option score = α·max-cos(state, examples ∪ what) + (1−α)·lexical overlap, minus a
  penalty when the state matches `not_for` better than `what`.
- `none` score = max(τ_none, max-cos to the catalog-wide `native` exemplars).
- `probabilities = softmax(scores / T)`; `confidence = 1 − H(p)/log(n)`.
- τ_none, T, α, threshold are calibrated by `agent-router eval` on `evals/eval_set.yaml`
  (positives per entry + negatives where native tools suffice + decoys).

### Router rules (enforced in code, tested)

1. Output ∈ catalog ∪ {none}; anything else → `none`.
2. Hints are rendered from a template over catalog fields only.
3. Never route a call to the router's own tools (`mcp__agent_router__*`) or to the target
   skill it just suggested (loop guard).
4. At most one suggestion per entry per turn.
5. Decider failure/timeout → `native` (fail open), logged.

### Hook behavior (Claude SDK adapter)

- `UserPromptSubmit`: advisory `additionalContext` only.
- `PreToolUse` on native tools and `Skill`: advisory `additionalContext`; in enforce mode
  `permissionDecision: deny` + templated reason.
- Adapter also exposes `build_mcp_server()` with the catalog tools and a demo workspace with
  `.claude/skills/commit-writer/SKILL.md`.
- Verified on SDK 0.2.160 / CLI 2.1.283: Skill calls arrive at PreToolUse as
  `tool_name="Skill", tool_input={skill, args}`; `additionalContext` from both hooks reaches
  the model; local Claude Code login works without an API key.

### Audit log (`core/audit.py`)

Append-only JSONL, one record per decision: ts, session, turn, point, tool_name,
state_sha256, options, probabilities, choice, confidence, action, backend, latency_ms,
catalog_version, thresholds. Hints/text are stored truncated; secrets are not redacted in the MVP
(local only).

## Demo (`agent_router/demo/`)

FastAPI + one static HTML page (no build step), `make run` → http://127.0.0.1:8765.

1. **Playground** (zero token cost): enter text, choose hook point/pending tool/backend →
   probability bars for every option incl. `none`, decision, rendered hint.
2. **Live agent**: prompt → inner Claude runs in a demo workspace; timeline streams (SSE)
   hook events, router decisions, tool calls, assistant text, result.
3. **Replay**: load any audit JSONL session to step through decisions.

## Testing

- Unit (offline, deterministic): catalog validation/MIT enforcement, decider contract
  (probabilities sum to 1, choice ∈ options), router rules 1–5, hint templating, tools,
  adapter hook output shapes (with fake inputs), audit records.
- Eval (`-m model`, downloads potion-8M once): accuracy and false-positive rate on the eval
  set; thresholds asserted (target: top-1 accuracy ≥ 0.85, FPR on negatives ≤ 0.10).
- Live e2e (`-m live`, opt-in): real SDK run confirms a hint is injected and the agent calls
  a catalog tool.

## Out of scope (MVP)

Codex/Gemini adapters (documented only), network tools, payments, secret redaction,
trained classifier heads.
