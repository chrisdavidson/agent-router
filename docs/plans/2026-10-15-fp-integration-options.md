# Loosely coupling first-principles and agent-router: three options

Date: 2026-10-15 · Status: **proposal only. Nothing here has been executed.**
Repos read (read-only): `~/Projects/first-principles-skill` at `d9c71a13` (plugin 9.20.0) and
`~/Projects/agent-router` on `main` (fork `chrisdavidson/agent-router`, upstream
`usathyan/agent-router`, with the `feat/first-principles-integration` branch merged in).

---

## 1. What each project is, in one paragraph

**first-principles** is a Claude Code plugin. It ships one analysis agent
(`first-principles:first-principles`, `maxTurns: 90`, no `Write`/`Edit`/`Agent`/`Skill`),
fifteen slash-only skills, and one executable piece: a `SubagentStop` **delivery guard**
that blocks the agent's stop up to twice until `.first-principles/analysis-*.md` is
assembled and its reader report exists. Each report ends with a **structured-summary JSON
block** whose contract is `references/summary-schema.json` (schema_version 1, add-only
evolution, checked by SUMM-BLOCK). The repo applies heavy gate discipline: you edit only
`shared/`, and the generated tree, version stamps, and claim surfaces are all gated.

**agent-router** is a Python package and CLI that puts a checkpoint at the host's hook
points. It classifies each prompt, tool call, or skill call against a small, fixed catalog
of approved entries (`kind: tool | skill | agent`). It either injects a templated note
(advisory) or denies the call (enforce), and it **always fails open**. It ships these pieces:
- **Hook adapters.** An in-process Agent SDK adapter, plus a Claude Code command-hook adapter (`agent-router hook`).
- **A stdio MCP server** with deterministic tools (`calc`, `json_query`, `html_to_markdown`, `repo_stats`).
- **Logs.** A per-session audit log.
- **CLI commands.** `route --json`, `eval`, `calibrate`.
- **An SDK runner** (`agent.py`, SDK 0.2.161, whose `ClaudeAgentOptions` has a `plugins` field).
- **A demo UI** with Playground, Live, Replay, and Trace tabs.

## 2. What already exists: a working first integration (call it "Option 0")

`agent-router/integrations/first-principles/` already holds a sidecar plugin,
`agent-router-fp`. It is loaded next to first-principles with two `--plugin-dir` flags, and
it never edits first-principles. It provides these pieces:

| Piece | Hook / surface | Effect |
|---|---|---|
| Delegation nudge | `UserPromptSubmit`, `PreToolUse(Agent)` | advisory note: "delegate this to `first-principles:first-principles`" |
| Exact recompute | `PreToolUse(Bash)` scoped to the FP agent + MCP `calc` | note pointing at the calculator when a one-expression `python -c`/`bc` call fits |
| Decision trace | `SubagentStart/Stop`, `PostToolUse*` (record-only, always `{}`) | per-run JSONL: sections written, refs read, assumptions, gate, conclusion, note follow-through |
| Measurement | `battery.py`, `run_examples.py`, `calibrate.py` | live A/B on FP's routing catalog; the 14 worked examples run through the agent |

So the question is not *whether* the two can cooperate; they already do. The real question
is **where the coupling still binds them tightly, and how far we want orchestration to move
toward the router's infrastructure.**

### 2.1 Coupling inventory: where the two are bound today

| # | Coupling point | Direction | Strength | Why it matters |
|---|---|---|---|---|
| K1 | `trace.py` regex-parses FP's **prose** (section headings, "Gate result", re-entry wording) | router → FP template wording | **Strong, implicit** | Every FP wording change silently breaks the trace (8 commits in 23 and still 2/14 misreads, per the router's own notes). FP shipped the summary block (v9.16) to end this, but `trace.py` does **not read it yet** (no `schema_version` reference in `trace.py`). |
| K2 | Catalog hard-codes `first-principles:first-principles` and `mcp__plugin_agent-router-fp_agent_router__calc` | both ways | Medium, explicit | Renaming either plugin or agent breaks routing silently (fail-open hides it). |
| K3 | `.first-principles\b` skip regex; `^/first-principles:` prompt skip | router → FP file layout | Medium | Encodes FP's output directory and command namespace. |
| K4 | `run_examples.py` parses FP's `shared/examples/*.md` labels (`**Scenario.**`, …) | router → FP source tree | Strong, implicit | Reaches into FP's *source*, not its shipped plugin. |
| K5 | `bin/hook`, `bin/mcp` resolve the router's `.venv` by relative path | plugin → its own repo | Medium | The sidecar is not installable outside a checkout (`AGENT_ROUTER_BIN` override exists). |
| K6 | Two independent `SubagentStop` hooks on the same agent (FP's blocking delivery guard + router's record-only trace) | none (co-resident) | Latent | Harmless today because the trace never blocks. **It becomes a real conflict the moment the router adds a blocking contract gate** (its own plan §3.1): two blockers, undefined order, and separate retry budgets. |
| K7 | Calculator use depends on the *delegating prompt*, not the note | behavioural | Soft | Measured 0/5 unprompted under FP 9.14 vs 13/15 under 9.13. Orchestration, not hooks, is the lever. |

**Design rules carried into every option** (taken from both repos' own lessons):
1. **One owner per concern**, set out in the table below.
2. **Contracts over prose.** The only FP output the router may parse is the schema-validated summary block.
3. **Fail open, advisory by default.** Anything that steers is named as steering.
4. **Record-only stays record-only.**
5. **No edits to `first-principles/` generated files.** Any FP-side change goes through `shared/` and its gates, and is tiered product vs apparatus.

| Concern | Owner | The other side may only… |
|---|---|---|
| Whether to run an analysis | router (nudge) + FP (its own description) | — |
| Technique selection, phases, Self-Audit Gate | **first-principles** | observe |
| Delivery completeness (file + reader report) | **first-principles** (delivery guard) | observe |
| Output contract (summary block) | **first-principles** (schema) | consume, validate |
| Deterministic tools (calc, html→md, fetch fallback) | **agent-router** | FP may use them if present, never require them |
| Audit, trace, replay, UI, eval harnesses | **agent-router** | FP emits data, never depends on them |

---

## 3. Option A: Contract-first sidecar (evolve what exists)

**Idea.** Keep the current shape (two independent plugins, side by side) and replace each
implicit coupling with an explicit, versioned contract that each side publishes and the
other reads. Orchestration stays where it is: the Claude Code main session plus hooks.

```
        Claude Code session (main)
          │ UserPromptSubmit / PreToolUse ──► agent-router-fp hook ──► note (advisory)
          │ Agent(first-principles:first-principles)
          ▼
   first-principles agent ──Bash python -c──► router note ──► mcp calc (optional)
          │ writes .first-principles/analysis-*.md  (+ summary JSON block)
          ▼ SubagentStop
   FP delivery-guard (may block ≤2)    router trace (record-only, reads JSON block)
```

**Changes (all on the router side, plus one optional FP-side manifest):**
1. **K1 → read the contract.** `trace.py` reads the structured-summary block first and
   validates it against `summary-schema.json`, *read from the installed FP plugin at
   runtime* (`${fp_plugin}/references/summary-schema.json`). Prose parsing becomes a labelled
   fallback for legacy runs (`analysis_source: prose`), and it records `null` rather than guessing.
   This is the open TRACE-01 item.
2. **K2/K3 → a capability manifest.** FP publishes a small, versioned
   `references/integration.json`: agent name, output path glob, schema path and version,
   command namespace, and the names of optional tool capabilities it can use ("exact-arithmetic").
   The router's catalog and skip regexes are generated from it at hook start, so hard-coded
   copies go away. *Optional:* if FP doesn't ship it, the router keeps its own copy and pins it.
3. **K4 → shipped examples only.** `run_examples.py` reads `first-principles/references/examples/`
   (the shipped plugin tree), never `shared/`.
4. **K5 → installable sidecar.** Resolve `agent-router` from `PATH` / `uv tool install`
   before falling back to the checkout `.venv`.
5. **K6 → declared hook etiquette.** The router commits in its README that it never blocks
   on `SubagentStop` for `first-principles:*`, because FP owns delivery. If a contract gate is
   ever wanted, it is FP's delivery guard that enforces the schema, not a second blocker.
6. **K7 → a prompt-level capability hint.** Advertise the calculator once with
   `SubagentStart` → `additionalContext` (verified working on 2026-09-30), instead of per-call notes.

**Where Claude's capabilities do the harmonising:** plugin co-loading, hooks (`additionalContext`,
`SubagentStart`), MCP tool discovery with ToolSearch, and the main session as the delegator.

| | |
|---|---|
| Coupling after | data contracts only (schema + manifest, both versioned); no code imports either way |
| FP changes | none required; optional `integration.json` via `shared/` (one new spine reference + gate registration) |
| Router changes | `trace.py` block reader, catalog-from-manifest, installable `bin/` |
| Effort | **small to medium**; about 80% already exists |
| Determinism | low to medium: orchestration is still the main session's judgement plus advisory notes |
| Strengths | cheapest; no new moving parts; fail-open preserved; each repo still runs alone |
| Weaknesses | "orchestration" stays implicit (nudge-driven); the run shape isn't owned by anyone; K7 (prompt-dependence) only partly addressed |
| Key risk | Schema drift: mitigated by `schema_version` + add-only rule, and the router pins the versions it accepts |

---

## 4. Option B: Claude as the conductor (a third, thin orchestration layer)

**Idea.** Neither repo learns about the other. A **third artifact**, a small Claude Code
plugin or project skill (this folder, `orchestrate-first-principles-router-agent/`, is a natural home), owns the *workflow*.
It talks to each side only through its public interface:
- the router's CLI (`agent-router route --json`) and MCP server;
- FP's launcher or agent, its output file, and its summary schema.

Claude is the glue: a skill describes the run, and the main session executes it with
subagents, MCP tools, and hooks.

```
 /fp-orchestrate "<question>"            (conductor skill, main session)
   1. Pre-flight   ── Bash: agent-router route --json "<q>"   → delegate? entry? confidence
                   ── decide mode: full analysis / focused technique / "not a FP question"
   2. Compose      ── build the delegating prompt: problem statement per FP's Input Contract,
                      plus "an exact calculator is available: load it with ToolSearch" when the
                      router MCP is present (fixes K7 at its real lever: the prompt)
   3. Run          ── Agent(first-principles:first-principles)   [FP hooks: delivery guard]
                      [agent-router-fp hooks optional: notes + trace]
   4. Verify       ── read .first-principles/analysis-*.md, extract the summary block,
                      validate against FP's shipped summary-schema.json
   5. Report       ── agent-router trace --report  / open the demo's Trace tab;
                      present Answer + confidence + any contract findings to the user
   6. (optional) Follow-up ── a second subagent challenges the weakest chain, or a
                      persona view (/first-principles:persona) for the target reader
```

**Pieces to build (all new, in the conductor; zero edits to either repo):**
- A conductor skill (`SKILL.md`) with the six steps, disable-model-invocation as FP does,
  plus a thin script for steps 1, 4, and 5 so the deterministic parts aren't left to the model.
- A config file naming the two plugin dirs, the router binary, and the accepted
  `schema_version` set (the manifest from Option A, but owned by the conductor).
- Optional: expose `route` as an MCP tool, so the conductor needs no Bash. That would be a
  small router-side addition, kept on the fork.

**Where Claude's capabilities do the harmonising:** skills as workflow definitions, the
Agent tool for delegation, ToolSearch and MCP for the calculator, Bash for the deterministic
steps, and optionally a `Stop` hook so the main session can't end before step 4 has run.

| | |
|---|---|
| Coupling after | **lowest**: both repos are unaware of each other; the conductor depends on two published interfaces (CLI/MCP + schema/output path) |
| FP changes | none |
| Router changes | none (optional `route` MCP tool) |
| Effort | **medium**: a new small artifact, plus a deterministic helper script and its tests |
| Determinism | medium: the run *shape* is fixed by the skill; judgement inside steps is still model-driven |
| Strengths | explicit, reviewable orchestration; fixes K7 at the prompt; easy to extend (persona step, second-opinion step, other router-routed agents); either repo can change freely behind its interface |
| Weaknesses | a third thing to version and maintain; conductor steps run in the main session's context and token budget; a skill is followed, not enforced, so drift is possible without a `Stop` hook |
| Key risk | Duplicated responsibility: the conductor's pre-flight and the router's nudge hook can both decide "delegate". Pick one: with the conductor active, set `AGENT_ROUTER_SKIP_PROMPT` to the conductor's command so the nudge stays silent |

---

## 5. Option C: Router as runtime host (a headless SDK pipeline)

**Idea.** Flip the host. Rather than Claude Code hosting both plugins, **agent-router's
Agent SDK runner hosts the first-principles agent**. The router's in-process hooks, its
in-process MCP tools, the audit log, and the demo UI become the runtime. The FP plugin is
loaded unmodified through the SDK's `plugins` option (present in the installed SDK
0.2.161). Orchestration is code: a named pipeline profile, run from the CLI, batched for
evals, and replayed in the demo. This is the router's own "predefined graph of steps" next
stage, applied to one agent.

```
 agent-router run --profile first-principles "<question>"      (Python, Agent SDK)
   ClaudeAgentOptions(
     plugins=[{type: local, path: ~/…/first-principles-skill/first-principles}],
     hooks=ClaudeRouterHooks(catalog=fp-profile),     # in-process, no subprocess per call
     mcp_servers={agent_router: in-process calc/html/fetch-fallback},
   )
   graph:  route ─► delegate(first-principles:first-principles) ─► [FP delivery guard]
                 ─► contract check (summary block vs schema, record-only)
                 ─► trace + audit ─► demo Live / Replay / Trace / regression view
```

**Pieces to build (router side, kept under `integrations/first-principles/` on the fork):**
1. A `profile` concept: catalog + calibration + plugin list + pipeline steps, in one YAML.
2. SDK runner support for `plugins=` and for `SubagentStart/SubagentStop` record hooks
   (the router's SDK adapter today handles `UserPromptSubmit`/`PreToolUse`).
3. The contract check from Option A, step 1, run as a pipeline step rather than as a hook.
4. The router's own backlog items, now applied naturally:
   - eval-hygiene deny (plan §3.4): the agent can't read its own answer key, instead of `†` after the fact;
   - source-broker fallback for failed fetches (§3.3);
   - cross-run regression view (§3.10).

**Where Claude's capabilities do the harmonising:** the Agent SDK (plugins, hooks, in-process
MCP, subagent definitions); Claude Code becomes the *launcher*, via Bash, `/loop`, or a
scheduled routine for batch evals, rather than the host.

| | |
|---|---|
| Coupling after | FP still unaware of the router; the **router** takes a runtime dependency on FP's plugin format (agent name, hooks, schema), confined to one profile file |
| FP changes | none |
| Router changes | **largest**: profile system, SDK plugin loading, subagent hooks, pipeline steps |
| Effort | **medium to large** |
| Determinism | **highest**: the run is code; every step is audited; batch and regression runs are first-class |
| Strengths | best observability and repeatability; eval hygiene becomes prevention; one process instead of a hook subprocess per call (about 0.45 s each today); natural home for the router's "graph" roadmap; the demo UI becomes the review surface |
| Weaknesses | runs outside the interactive Claude Code session (SDK tokens, separate auth and cost); the tool and permission envelope differs from interactive use, so results may not transfer to `claude --plugin-dir` usage; the router fork diverges further from upstream |
| Key risks | **Unverified:** that plugin *hooks* (FP's delivery guard) and `${CLAUDE_PLUGIN_ROOT}` links resolve when a plugin is loaded through the SDK; probe before building (the same probe discipline as the router's §1 table). FP agent `maxTurns: 90` × SDK runs is expensive: pin `--model`, run serially (lesson from the earlier `claude -p` fan-out that hit usage limits). |

---

## 6. Side-by-side

| | A. Contract-first sidecar | B. Claude conductor | C. Router as host |
|---|---|---|---|
| Who orchestrates | main session + hooks (implicit) | a skill + helper script (explicit, in-session) | router pipeline code (explicit, headless) |
| FP repo edits | 0 (1 optional manifest) | 0 | 0 |
| Router repo edits | small–medium | 0 (1 optional MCP tool) | medium–large |
| New artifact | none | conductor plugin/skill | pipeline profile |
| Coupling strength | data contracts | interfaces only (weakest) | runtime plugin dependency (one file) |
| Determinism of run shape | low–medium | medium | high |
| Interactive use | ✅ native | ✅ native | ❌ headless (launch from Claude Code) |
| Batch / eval / regression | via existing scripts | awkward | ✅ first-class |
| Fixes K1 (prose parsing) | ✅ | ✅ (step 4) | ✅ |
| Fixes K6 (two blockers) | ✅ by declaration | ✅ (no router blocker) | ✅ (contract check is a step, not a hook) |
| Fixes K7 (calc via prompt) | partly (`SubagentStart` note) | ✅ (composes the prompt) | ✅ (composes the prompt) |
| Time to first value | shortest | short | longest |

## 7. Recommendation

They aren't mutually exclusive. They stack, and the cheapest order is **A → B, with C only
if batch evaluation becomes the main use.**

1. **Do A's step 1 first, in any case.** Make `trace.py` read the summary block. It removes
   the one strong, implicit coupling (K1), FP already paid for it in v9.16, and Options B
   and C both need it.
2. **Then build B.** It's the option that most literally matches "loosely coupled, with
   Claude's capabilities doing the harmonising": neither repo changes, and the orchestration
   becomes a reviewable artifact that fixes the calculator problem at its measured lever
   (the delegating prompt).
3. **Hold C** until a probe confirms that FP's plugin hooks and `${CLAUDE_PLUGIN_ROOT}`
   links behave under the SDK `plugins=` option, and until there's a concrete batch/eval need
   that the existing `run_examples.py` can't meet.

## 8. Open questions for you

1. **Upstream or fork?** agent-router's upstream is `usathyan/agent-router`. Should
   router-side changes (A's trace reader, C's profiles) be aimed at upstream, or stay on
   `chrisdavidson/agent-router`? This decides how generic they must be.
2. **Steering appetite.** Should the router ever *block* inside an FP run (enforce mode on
   `Bash` math, a contract gate)? Every option above assumes **no**, and leaves blocking to FP's
   delivery guard.
3. **Where does the conductor live (Option B)?** In this folder as a standalone plugin, in
   `agent-router/integrations/`, or in `~/.claude/` as a personal skill? The first keeps
   both repos untouched.
4. **Is an FP-side `integration.json` acceptable?** It would be a new shipped reference, so
   it goes through `shared/`, sync, and gate registration (a product-tier surface). Option A works
   without it, at the cost of the router pinning its own copy.

## 9. Verification to run before committing to an option (not run yet)

| Check | Applies to | How |
|---|---|---|
| `trace.py` reads the block on the 14 frozen example runs | A, B, C | replay `runs/structured-summary-live` with prose parsing disabled; expect 14/14 blocks, 0 schema errors |
| Two `SubagentStop` hooks coexist | A, B | one FP run with both plugins; confirm FP guard blocks still fire and the trace records `run_end` once |
| `SubagentStart` note reaches the FP agent | A | the router's existing ZEBRA-42-style probe, retargeted at `first-principles:first-principles` |
| Conductor pre-flight agrees with the nudge | B | `agent-router route --json` over FP's `tests/routing-catalog.md`; compare with `battery.py` results |
| Plugin hooks + `${CLAUDE_PLUGIN_ROOT}` under SDK `plugins=` | C | throwaway SDK script loading FP; confirm delivery-guard fires and a reference Read resolves |
| Exercise the working tree, not the cache | all | use `claude --plugin-dir …`; the in-session Agent tool runs the stale installed FP copy |
