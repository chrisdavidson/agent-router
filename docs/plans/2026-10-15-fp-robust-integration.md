# Plan: a robust, loosely coupled first-principles integration for agent-router

Status: **plan for review. Nothing here has been executed.**
Date: 2026-10-15 · Companion analysis: [`OPTIONS.md`](OPTIONS.md) (the three options and the coupling inventory K1–K7).
Target repo: `~/Projects/agent-router`, on the **fork** `chrisdavidson/agent-router` (not upstream).
Secondary repo, minimal touch: `~/Projects/first-principles-skill`.

This document serves as the **idea document for `/bm:new-project --auto`** in agent-router (see §9).
It is written so that GSD's roadmapper can lift the requirements (§5) and phases (§6) directly.

---

## 1. Goal

Make agent-router the robust, observable infrastructure that a first-principles analysis runs
on, without either project depending on the other's internals. Concretely:

- agent-router reads first-principles' output **only through published contracts**: the
  structured-summary block, its schema, and a small integration manifest. It never parses
  prose by default.
- A **conductor skill** in agent-router's integration plugin owns the run's shape: pre-flight
  routing, prompt composition, delegation, post-flight verification and the report. That is
  Option B of `OPTIONS.md`, built on Option A's contracts.
- The router's hooks, state, install path and diagnostics are **hardened**: proven fail-open,
  race-safe, installable outside a checkout, and self-diagnosing.
- first-principles changes by **one data file** (the manifest) and nothing else.

## 2. Locked decisions

| ID | Decision | Source |
|---|---|---|
| D-01 | All agent-router work stays on the fork `chrisdavidson/agent-router`. No upstream PR is a goal; upstream-friendliness is not a constraint. | user, 2026-10-15 |
| D-02 | The router **never blocks** inside a first-principles run: no `deny` on any tool call made by `first-principles:first-principles`, and no `decision: "block"` on its `SubagentStop`. Delivery enforcement belongs to first-principles' delivery guard alone. Advisory notes and record-only hooks remain allowed. | user, 2026-10-15 |
| D-03 | The conductor lives under `agent-router/integrations/first-principles/`, shipped as a skill inside the existing `agent-router-fp` plugin (one install, one plugin dir). | user, 2026-10-15 |
| D-04 | A first-principles-side integration manifest is acceptable. It is the **only** first-principles change in scope. | user, 2026-10-15 |
| D-05 | Minimize first-principles impact; put effort into agent-router robustness. Every router feature must work **without** the manifest present, falling back to pinned defaults. | user, 2026-10-15 |
| D-06 | Contracts over prose. The structured-summary block is the primary source of decisions. Prose parsing is a labelled fallback that records `null` rather than guessing. | `docs/plans/2026-09-30-beyond-first-principles.md` §2 items 1–2 |
| D-07 | Fail open everywhere. Any router error yields `{}` and the session continues unchanged. | router README / adapters doc |
| D-08 | Record-only hooks stay record-only (always `{}`). Steering hooks are separate and named as steering. | beyond-first-principles §2 item 6 |
| D-09 | One owner per concern, as in the table below. | `OPTIONS.md` §2.1 |

| Concern | Owner | Other side may only… |
|---|---|---|
| Technique selection, phases, Self-Audit Gate | first-principles | observe |
| Delivery completeness (file + reader report) | first-principles (delivery guard) | observe |
| Output contract (summary block + schema) | first-principles | consume, validate, report |
| Integration identity (agent name, paths, schema versions) | first-principles (manifest) | read; fall back to pinned copy |
| Routing, deterministic tools, audit, trace, UI, eval harnesses | agent-router | FP may use if present, never requires |
| Run orchestration (the conductor) | agent-router integration plugin | — |

## 3. Non-goals

- No change to the first-principles agent body, rubric, template, skills, delivery guard or
  version stamps.
- No enforce mode inside first-principles runs (D-02). No contract gate that blocks.
- No headless SDK host for first-principles (Option C). It is deferred; see §8.
- No generalisation of the trace to other agents yet. It is designed not to preclude that
  (§5 TRACE-05), but it isn't built.
- No new deterministic tools (unit conversion, statistics, fetch fallback). Those are
  backlog items in `beyond-first-principles.md` §3.3 and §3.5.

## 4. Current state (verified 2026-10-15, read-only)

agent-router (`main`, 412 test functions, offline by default):
- `integrations/first-principles/` holds the sidecar plugin `agent-router-fp`:
  - `bin/hook` handles routing; it is advisory and fails open.
  - `bin/mcp` serves `calc` only.
  - `bin/trace` writes a record-only trace.
  - `hooks/hooks.json` wires these on `UserPromptSubmit`, `PreToolUse(Agent|Bash)`, `SubagentStart/Stop` and `PostToolUse*`.
  - It also holds `catalog.yaml`, `calibration.json`, `trace.py` (930 lines), `run_examples.py`, `battery.py` and `calibrate.py`.
- `trace.py` derives decisions by **regex over report prose** (`parse_analysis`, `_gate_passes`,
  `_assumptions`). It has no reader for the structured-summary block (no `schema_version`
  reference anywhere).
- The catalog hard-codes `first-principles:first-principles` and
  `mcp__plugin_agent-router-fp_agent_router__calc`. `bin/hook` hard-codes the skip regexes
  `\.first-principles\b` and `^\s*/first-principles:`.
- `bin/hook`, `bin/mcp` and `bin/trace` locate the router via the checkout's `.venv` (an
  `AGENT_ROUTER_BIN` / `AGENT_ROUTER_PYTHON` override exists).
- `adapters/claude_code.py` writes the session state atomically (temp file plus `replace`), but as
  an unlocked **read-modify-write**. Concurrent hook processes in one session can lose an
  update, for example the once-per-turn hint set, which would then produce duplicate notes.
- `run_examples.py` reads first-principles' **source tree** (`shared/examples/*.md`).
- `integrations/first-principles/runs/` is **untracked**. No run capture or report is a
  committed fixture, so trace behaviour has no regression net.

first-principles (9.20.0):
- The structured-summary block is shipped. `first-principles/references/summary-schema.json`
  is a **hand-validatable field table, not JSON Schema** (keys: `schema_version`,
  `versioning`, `block`, `required`, `fields`, `invariants`, `example`). Its evolution rule is
  add-only: removing or renaming a field, or narrowing an enum, bumps `schema_version`.
- The block is the last element of the analysis file under `## Structured summary (process
  output)`. It is never carried in the agent's final message.
- JSON spine references are emitted through `SPINE_JSON_REFERENCES = ("summary-schema",)` in
  `scripts/sync-content.py`. A second JSON reference is a one-tuple-entry change.

## 5. Requirements

IDs are stable and intended to map 1:1 into `.planning/REQUIREMENTS.md`. Each one has an
acceptance check that can fail.

### CONTRACT: read decisions from the summary block

- **CONTRACT-01** `trace.py` extracts exactly one structured-summary block from an analysis
  (the heading plus one fenced `json` block, last in the file). Zero blocks, more than one, a
  misplaced block, or invalid JSON each produce a distinct, recorded `contract_status`
  (`absent`, `multiple`, `misplaced`, `invalid_json`). None of these raises.
  *Accept:* a fixture per status; each yields its own status code.
- **CONTRACT-02** A router-owned, stdlib-only **field-table validator** checks the block against
  the schema file *read at runtime from the installed first-principles plugin*. The
  validator interprets the schema's own keys; it does not embed a copy of the fields.
  *Accept:* validating a shipped worked example's block passes. Mutating one enum value, one
  required key, or one id pattern each fails with a field path.
- **CONTRACT-03** Accepted `schema_version`s are an explicit set pinned in router config
  (initially `{1}`). An unknown version is recorded as `contract_status: unsupported_version`,
  and the block's decisions are still surfaced as `unverified`. The trace does not drop them.
  *Accept:* a fixture with `schema_version: 2` yields `unsupported_version` and populated
  `decisions`.
- **CONTRACT-04** When a valid block exists, `decisions` come from the block, with
  `analysis_source: block`. Prose parsing runs only when there is no valid block, and is then
  labelled `analysis_source: prose`. Fields it cannot determine are `null`, never a guess.
  *Accept:* on a fixture where prose and block disagree, the trace reports the block's value
  and lists the disagreement under `contradictions`.
- **CONTRACT-05** The router cross-checks only the block-internal invariants that need no prose
  parsing: ids are unique, every `rests_on` id resolves inside the block, and
  `gate.cleared` is consistent with the last pass. It records violations and never repairs
  them. Prose-to-block agreement remains first-principles' SUMM-BLOCK gate's job; the router
  does not re-implement it.
  *Accept:* a fixture with a dangling `rests_on` id yields one recorded violation.
- **CONTRACT-06** The `--report` output and the demo Trace tab show `contract_status` and
  `analysis_source` per run.
  *Accept:* a demo-server test renders both fields for one block run and one prose run.

### MANIFEST: integration identity, owned by first-principles and optional

- **MANIFEST-01** The router defines a manifest format (`integration.json`, its own
  `manifest_version` integer starting at 1, add-only). It contains:
  - `plugin_name`, `agent_type`;
  - the output path glob (`.first-principles/analysis-*.md`);
  - the command namespace prefix (`/first-principles:`);
  - the launcher command;
  - the schema file path relative to the plugin root;
  - the accepted `schema_version` set;
  - optional `capabilities_used` (e.g. `exact-arithmetic`).

  The format spec lives in agent-router (`integrations/first-principles/MANIFEST.md`).
  *Accept:* the spec plus a loader test over a valid and an invalid manifest.
- **MANIFEST-02** The loader finds the first-principles plugin root in this order:
  1. `FP_PLUGIN_ROOT`;
  2. the first-principles `--plugin-dir` recorded by the conductor;
  3. the Claude plugin cache;
  4. a pinned fallback manifest shipped in agent-router.

  Resolution order and outcome are logged once per session.
  *Accept:* a test for each resolution branch, including "no FP plugin found".
- **MANIFEST-03** The catalog's agent target, the calculator tool name, and both skip regexes
  are **derived** from the resolved manifest, plus the plugin's own name, at hook start.
  Nothing in `bin/hook` or `catalog.yaml` hard-codes `first-principles` strings any more,
  except the pinned fallback.
  *Accept:* a grep test over `plugin/` and `catalog.yaml` finds no literal outside the fallback
  file. Renaming `agent_type` in a test manifest re-targets the catalog.
- **MANIFEST-04** A manifest whose `manifest_version` is unknown, or whose schema path does not
  exist, degrades to the pinned fallback with a recorded warning. It never fails a hook.
  *Accept:* fixture tests.

### INSTALL: runs outside a checkout, and explains itself

- **INSTALL-01** `bin/hook`, `bin/mcp` and `bin/trace` resolve the router binary and Python
  in this order: `AGENT_ROUTER_BIN` / `AGENT_ROUTER_PYTHON`, then `PATH` (a `uv tool install`
  of the fork), then the checkout `.venv`.
  *Accept:* a shell test drives each branch with a stub binary.
- **INSTALL-02** A new `agent-router doctor --integration first-principles` command checks and
  reports, one line each, PASS / WARN / FAIL with a reason:
  - the binary;
  - catalog load;
  - calibration load;
  - the decider backend;
  - the FP plugin root and how it was found;
  - the manifest (version, or fallback);
  - schema file presence and version;
  - MCP `calc` server start;
  - the hooks wiring in `hooks.json`;
  - state-dir writability.

  It exits non-zero only on FAIL.
  *Accept:* tests covering a healthy fixture tree and one broken item per check.
- **INSTALL-03** The README's *Use it* section documents both the checkout install and the
  `uv tool install` install, and states `doctor` as the first troubleshooting step.

### HOOK: hardening, proven

- **HOOK-01** Fail-open matrix as tests. Each of the following yields `{}` and exit 0 for every
  hook entry point (`hook`, `trace`):
  - malformed stdin JSON;
  - empty stdin;
  - a missing or unwritable state dir;
  - an unreadable catalog or calibration file;
  - a decider exception;
  - a manifest error;
  - a trace parse exception.

  *Accept:* a parametrised test over the matrix, run through the real `bin/` scripts.
- **HOOK-02** Session state updates are **race-safe**: read-modify-write is serialised per
  session (an `fcntl` lock on a sidecar lock file, with a bounded wait; on timeout, fail open
  without writing).
  *Accept:* a test spawning N concurrent hook processes on one session ends with every
  expected key present and no duplicate once-per-turn note.
- **HOOK-03** **Never-block invariant (D-02)**, enforced in two ways:
  1. a static test asserts that no hook in the integration plugin is wired to emit
     `permissionDecision: "deny"` or `decision: "block"` for the first-principles agent;
  2. a runtime test with `AGENT_ROUTER_MODE=enforce` forced in the environment confirms that
     calls carrying the FP `agent_type` still yield at most `additionalContext`.

  *Accept:* both tests pass. Each has a must-fail control that injects a deny or block and
  turns the test red.
- **HOOK-04** Latency budget: the routed hook path stays under a recorded p95 (baseline it in
  Phase 1, then fail the test on a regression of more than 2×). Fast paths that avoid Python
  stay in the shell script.
  *Accept:* a benchmark test with the baseline committed.
- **HOOK-05** Coexistence with first-principles' `SubagentStop` delivery guard: when the guard
  blocks (one or two times), the trace records a single `run_end`, attached to the final stop,
  with `stop_attempts` = number of SubagentStop events seen.
  *Accept:* a replay test from a fixture containing guard-blocked stops.

### TRACE: a regression net and source independence

- **TRACE-01** A committed fixture set under `tests/fixtures/fp/` contains:
  - a small number of analysis reports with valid blocks (from shipped worked examples
    and/or the 2026-09-29 runs);
  - synthetic negatives for every CONTRACT status;
  - at least one replayable stream-json capture, trimmed;
  - at least one capture with guard-blocked stops.

  *Accept:* fixtures load in tests, and the fixture README states each one's provenance.
- **TRACE-02** Characterisation tests freeze the current `trace.py` output on the fixtures
  **before** CONTRACT work starts, so every later diff in trace output is intentional.
  *Accept:* the tests exist and pass on the pre-change code.
- **TRACE-03** `run_examples.py` reads worked examples from the **installed plugin tree**
  (`<fp-plugin-root>/references/examples/`), resolved via MANIFEST-02, never from
  first-principles' `shared/`.
  *Accept:* a test with a fake plugin root; `--dry-run` lists examples from it.
- **TRACE-04** The `--report` output adds a contract coverage line, as numbers rather than a
  bug list: `block valid N/M · prose fallback K · unsupported V`.
  *Accept:* a test over fixtures.
- **TRACE-05** The block reader and validator live in a module that has no first-principles
  names in its code (`integrations/contracts/` or `core/contract.py`), parametrised by
  manifest. This is design only; no other agent is wired.
  *Accept:* a grep test for `first-principles` / `first_principles` literals in that module.

### CONDUCT: the conductor skill (Option B, D-03)

- **CONDUCT-01** A skill `skills/analyze/SKILL.md` in the `agent-router-fp` plugin, invoked as
  `/agent-router-fp:analyze <question>`, slash-only (`disable-model-invocation: true`).
- **CONDUCT-02** The deterministic steps live in a helper `integrations/first-principles/conduct.py`
  with three sub-commands. The skill only sequences them and makes the judgement calls:
  - `preflight "<q>"` runs `route --json` with the integration catalog and returns `delegate`
    or `not-fp`, the score, and the entry;
  - `compose "<q>"` returns the delegating prompt: the problem statement per FP's Input
    Contract, plus a calculator capability line when the MCP `calc` server is reachable. This
    fixes K7 at its measured lever;
  - `verify <analysis-path>` runs the CONTRACT reader and returns status, decisions summary,
    `answer_excerpt` and the report path.
- **CONDUCT-03** Flow: preflight → (if `not-fp`: say so and stop, unless the user insists) →
  compose → `Agent(<agent_type from manifest>)` with the composed prompt → verify → report.
  The report contains: the Answer section, the conclusion and its confidence,
  `contract_status`, `gate.cleared`, and the path to the reader report and trace. The
  conductor never rewrites or "fixes" the analysis (D-02, D-09).
- **CONDUCT-04** No double delegation: while the conductor is active, the delegation nudge is
  silent. `AGENT_ROUTER_SKIP_PROMPT` is derived to also match `^\s*/agent-router-fp:`.
  *Accept:* a hook test showing no note on a conductor-launched prompt.
- **CONDUCT-05** A conductor run is traceable end to end. The `delegation` trace record
  carries `launched_by: conductor` and the composed prompt's hash.
  *Accept:* a replay test.
- **CONDUCT-06** Every `conduct.py` sub-command is unit-tested offline: route stubbed,
  fixtures for verify, and golden outputs for compose.

### FP: the single first-principles-side change (D-04, D-05)

- **FP-01** Add `shared/spine/references/integration.json` (MANIFEST-01 format, values for
  first-principles 9.20.x), and add `"integration"` to `SPINE_JSON_REFERENCES` so it is
  emitted to `first-principles/references/integration.json`.
  *Accept:* `python3 scripts/sync-content.py --check` passes, and
  `bash scripts/check-firewall-battery.sh` reports GREEN. Any derived-count or claim-surface
  regeneration the battery demands is done via the generators, never by hand.
- **FP-02** The manifest carries **no** plugin version stamp, so VERSION-01 is not
  extended. Its own `manifest_version` is independent.
- **FP-03** A CHANGELOG line, and a patch release only if first-principles' release process
  requires one for a new reference file. No agent-body, rubric, template or skill edits.

### VERIFY: live acceptance, manual and recorded rather than gated

- **VERIFY-01** One live conductor run on a fresh question, with both plugins loaded via
  `--plugin-dir` (never the plugin cache). It must record: `contract_status: valid`, the
  delivery guard's behaviour, no router deny or block, and the trace `run_end` once.
- **VERIFY-02** The worked-example rerun via `run_examples.py` (serial, pinned `--model`) on a
  small subset. It reports block-valid coverage and calculator use, compared with the
  2026-09-29 baseline.
- **VERIFY-03** The results are written to `integrations/first-principles/VERIFICATION.md`, with
  K-of-N readings stated as observations, not gates.

## 6. Phases

Ordered by dependency. Phase 0 is the first-principles track: it is independent, and no
router phase blocks on it (D-05).

| # | Phase | Requirements | Depends on | Size |
|---|---|---|---|---|
| 1 | **Safety net**: fixtures, characterisation tests, latency baseline | TRACE-01, TRACE-02, HOOK-04 (baseline only) | — | S |
| 2 | **Contract reader**: block extraction, field-table validator, version policy, block-first decisions | CONTRACT-01…06, TRACE-04, TRACE-05 | 1 | M |
| 3 | **Integration manifest (router side)**: format, loader, derivation, pinned fallback | MANIFEST-01…04, TRACE-03 | 1 | M |
| 4 | **Hook hardening**: fail-open matrix, race-safe state, never-block invariant, guard coexistence | HOOK-01…05 | 1 (3 for manifest-error rows) | M |
| 5 | **Install & doctor** | INSTALL-01…03 | 3, 4 | S–M |
| 6 | **Conductor skill** | CONDUCT-01…06 | 2, 3, 4 | M |
| 7 | **Live verification & docs** | VERIFY-01…03 | 5, 6 (and Phase 0 if available) | S |
| 0 | **first-principles manifest** (in FP repo, via `/bm:quick` there) | FP-01…03 | MANIFEST-01 spec frozen (end of Phase 3) | XS |

Phases 2, 3 and 4 can run in parallel after Phase 1. They touch disjoint files:
- Phase 2: `trace.py` and the new contract module;
- Phase 3: the loader, `catalog.yaml` derivation and `bin/hook` env;
- Phase 4: `adapters/claude_code.py`, `bin/*` and tests.

The one shared file, `bin/hook`, must be sequenced 3 → 4.

### Phase success criteria

1. **Safety net:** fixtures committed; `make test` green; trace output frozen;
   p95 hook latency recorded in-repo.
2. **Contract reader:** every CONTRACT acceptance test green. All fixture reports with blocks
   are read as `analysis_source: block`. Characterisation diffs are exactly the intended
   ones, and each is listed in the phase summary.
3. **Manifest:** the grep test finds no hard-coded FP literals. All four resolution branches
   are tested. The router works unchanged with no manifest present.
4. **Hook hardening:** the fail-open matrix is green through the real `bin/` scripts. The
   concurrency test is green with N ≥ 8. The never-block tests are green, and their must-fail
   controls are red when injected.
5. **Install & doctor:** `doctor` is green on a healthy fixture tree, with one FAIL per broken
   item. The `uv tool install` path is tested.
6. **Conductor:** `conduct.py` is fully unit-tested offline. The skill file passes
   `claude plugin validate` on the plugin dir.
7. **Live:** `VERIFICATION.md` records VERIFY-01 and 02, with costs.
0. **FP manifest:** FP battery GREEN, sync check clean, and the emitted
   `first-principles/references/integration.json` is loaded by the router's MANIFEST loader in
   a test pointed at the real FP checkout.

### Validation commands (agent-router)

```sh
make test                      # offline suite (must stay green every phase)
make lint                      # ruff check + format --check over src tests
.venv/bin/pytest -q tests/test_fp_integration.py   # integration-focused subset
claude plugin validate integrations/first-principles/plugin
.venv/bin/agent-router doctor --integration first-principles    # from Phase 5
```

Note: `make lint` covers `src tests` only. Phase 1 should extend it to
`integrations/first-principles/*.py` so the integration code is linted too.

## 7. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Characterisation tests freeze *wrong* current behaviour, and later fixes look like regressions | medium | Phase 2 lists every intended diff; a reviewer checks the list against CONTRACT-04 |
| Fixtures drawn from the 2026-09-29 runs predate the block (FP 9.14) | high | use the shipped worked examples (14/14 carry a block, checked 2026-10-15) plus `runs/structured-summary-live` (14 reports with a block); synthesise negatives |
| FP schema gains fields (add-only) and the validator rejects unknown keys | medium | the validator ignores unknown *fields* but rejects unknown *schema keywords*, mirroring FP's own SUMM-BLOCK checker |
| `fcntl` locking is POSIX-only | low (Linux/macOS) | fall back to no lock on platforms without `fcntl`, recording it in `doctor` |
| Conductor drift: the model skips `verify` | medium | `verify` is the step that produces the report; the skill's final output is generated by it, not composed freehand |
| The in-session Agent tool runs the **stale cached** FP plugin | high | VERIFY uses `claude --plugin-dir` for both plugins; `doctor` reports which FP root resolved |
| Fork diverges from upstream | accepted (D-01) | keep `src/` changes small (state locking, `doctor`); put the rest under `integrations/` |
| Live runs drain usage | medium | serial runs, pinned `--model`, small subsets; never parallel fan-out |

## 8. Deferred (backlog, not this milestone)

- Option C: headless SDK host with `plugins=`, after a probe that FP's hooks and
  `${CLAUDE_PLUGIN_ROOT}` links work under the SDK.
- An MCP `route` tool, so the conductor needs no Bash.
- Generic subagent trace for other agent types (TRACE-05 leaves the door open).
- Source broker for failed fetches; more deterministic tools; eval-hygiene deny. (The
  eval-hygiene deny conflicts with D-02 inside FP runs, so it needs its own decision.)
- Cross-run regression view in the demo.

## 9. How to run this with /bm

agent-router has no `.planning/` yet. From the agent-router checkout:

```sh
cd ~/Projects/agent-router
git switch -c feat/fp-robust-integration          # on the fork (D-01)
# copy this file in so the planning record lives with the code:
cp ~/Projects/first-principles-skill/orchestrate-first-principles-router-agent/PLAN.md \
   docs/plans/2026-10-15-fp-robust-integration.md
```

Then in Claude Code, in that directory:

1. `/bm:new-project --auto @docs/plans/2026-10-15-fp-robust-integration.md`.
   This creates PROJECT.md, REQUIREMENTS.md (§5 IDs) and ROADMAP.md (§6 phases 1–7).
   Pick granularity *standard*, and keep `plan_check` and `verifier` on.
2. Check that ROADMAP.md kept the §6 dependencies, the parallel group (2, 3, 4) and the
   locked decisions D-01…D-09. If not, edit ROADMAP.md before planning.
3. `/bm:plan-phase 1` → `/bm:execute-phase 1` → `/bm:code-review` → repeat per phase.
4. Phase 0 (first-principles) runs **in the first-principles repo** once Phase 3 has frozen the
   manifest format: `/bm:quick` there, with FP-01…03 as the task, followed by
   `bash scripts/check-firewall-battery.sh`.
5. Phase 7 is live and costs tokens. Run it manually and record it in `VERIFICATION.md`.
