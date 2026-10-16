# Beyond first-principles: what agent-router can inject, and where it pays off

Date: 2026-09-30 · Branch: `feat/first-principles-integration` · Scope: this repository only.
Nothing here changes another repository; every idea ships as agent-router code, a catalog entry,
or a plugin under `integrations/`.

## 1. What the host lets us inject

"Inject" means one of five things. Each row states how sure we are.

| Lever | Hook / surface | What it does | Status |
|---|---|---|---|
| **Note to the model** | `UserPromptSubmit`, `PreToolUse` → `additionalContext` | text the model reads before it acts | verified (SDK 0.2.160 / CLI 2.1.283, `docs/adapters.md`); in use |
| **Deny a call** | `PreToolUse` → `permissionDecision: "deny"` + reason | the call does not run; the reason returns to the agent | verified; in use (enforce mode) |
| **Tools** | plugin `.mcp.json` → `mcp__plugin_<plugin>_agent_router__*` | new deterministic tools the agent can load | verified; in use (calculator) |
| **Note to a subagent at birth** | `SubagentStart` → `additionalContext` | text the subagent reads before its first turn | **verified 2026-09-30** (probe below) |
| **Send a subagent back once** | `SubagentStop` → `decision: "block"` + reason | the subagent keeps working with the reason as its next instruction; `stop_hook_active` is true on the retry, which stops loops | **verified 2026-09-30** (probe below) |
| Subagent's final text | `SubagentStop` input `last_assistant_message`, `agent_transcript_path` | read the answer and the full subagent transcript at stop | **verified 2026-09-30** |
| Rewrite a call's input | `PreToolUse` → `updatedInput` | e.g. add a flag, redirect a path | documented, not probed here |
| Rewrite an MCP tool's output | `PostToolUse` → `updatedMCPToolOutput` | e.g. shrink or annotate a result | documented, not probed here |
| Note after a call | `PostToolUse` → `additionalContext` / `decision: "block"` | react to what a call returned | documented, not probed here |
| Session-wide note | `SessionStart` → `additionalContext` | once per session instead of once per call | documented, not probed here |
| Main-session stop gate | `Stop` → `decision: "block"` | keep the main agent working until a check passes | documented (the `/goal` hook works this way) |
| Non-command hooks | `type: "prompt"` / `"agent"` / `"http"` / `"mcp_tool"` | an LLM or service decides instead of a script | documented, not probed here |

**Probe (2026-09-30, CLI 2.1.283, Haiku, throwaway plugin in the session scratchpad):** a
`SubagentStart` hook for `general-purpose` returned `additionalContext: "end your final answer
with ZEBRA-42"`, and a `SubagentStop` hook blocked once with `"also add the line: CHECKED-7"`.
The subagent's reply was `hello / ZEBRA-42 / CHECKED-7`. The stop hook fired twice, the second
time with `stop_hook_active: true`, and let it through.

Rule for the rows marked "documented": probe each one the same way before building on it. An
earlier summary of the hooks docs said `PreToolUse` has no `additionalContext`, which this repo
had already disproved.

## 2. What we learned from the first-principles work

These hold for any agent the router is attached to.

**Tracing**

1. **Prefer a contract to parsing prose.** A regex over free text fails a little differently
   on every new scenario (`trace.py` took 8 commits in 23 and still misread 2 of 14 reports on
   2026-09-29). Where the agent's output matters, get it as a fixed block (section 3.1).
2. **Say "unknown" rather than guess.** A missing field costs little. A wrong one (the
   personal-general re-entry read as "fired" from a denial) misleads every table built on
   it. A parser that is unsure records `null` and the source line it tried.
3. **Measure coverage as a number, not a bug list.** "gate result found in 12/14" is a
   metric to watch across runs; each miss is not a ticket.
4. **Separate fixed regression sets from exploratory scenarios.** The 14 worked examples
   compared across code versions show regressions. New scenarios test the agent, and will
   always surface new phrasings.
5. **Keep the raw evidence.** The trace keeps the report text and its hash, and the audit keeps
   `tool_use_id` / `agent_id`, so any conclusion can be rechecked later without rerunning.
6. **Record-only hooks stay record-only.** Tracing hooks always answer `{}`, so observing never
   changes what is observed. Hooks that steer are separate and are named as such.
7. **Flag contamination.** A run that opens its own answer key (`self-application †`) is
   marked and left out of comparisons. Generalise: any eval can declare paths the agent must
   not read (section 3.4).

**Routing and injection**

8. **Fit check before the classifier.** `fits: calc_expression` rejected 67 calls it could not
   run, so no note pointed at a tool that would have failed.
9. **Credit a note only with what changed after it.** Use that had already started is not the
   note's effect.
10. **Once per turn, scoped by `agent_type`, never on the agent's own writes.** Otherwise the
    agent is flooded with notes.
11. **Advisory by default, fail open always.** A broken router must never block the agent.
12. **Watch hook cost.** About 0.45 s per routed call; the report-write skip avoided 190 of 285
    checkpoints on the 14-example run. Cheap prefilters in the shell script come first.

## 3. Opportunities, for first-principles and any other agent

Ordered by value for effort. Each says which lever it uses and how to test it.

### 3.1 Output-contract gate for any subagent (SubagentStart + SubagentStop)

A catalog-like file names, per `agent_type`, a contract: a JSON schema for a fenced block the
agent must end with, plus cross-checks against its prose. At `SubagentStart` the router injects
one short note describing the block. At `SubagentStop` it reads `last_assistant_message` (or
the report file the agent names), validates the block, and if it is missing or invalid blocks
**once** with the specific error. On the retry (`stop_hook_active: true`) it always lets the
agent stop and records the result, pass or fail.

- **For first-principles:** this is recommendation 4 done from this side, with no edit to the
  first-principles repository. It overlaps the handoff prompt in
  `integrations/first-principles/handoff/fp-structured-summary.md`; choose one owner. The
  plugin's own template is the stronger home, since the examples teach the format, but this
  gate works today and works for agents we do not own.
- **For other agents:** a code reviewer ends with `{findings:[{file,line,severity}]}`; a
  researcher ends with `{claims:[{text,source_url}]}`; an Explore agent ends with
  `{files:[...]}`. The trace then reads fields, not prose.
- **Test:** schema fixtures with passing and failing controls; a live A/B on the 14 examples
  (block rate, cost, gate-clear rate, and whether the conclusions change).
- **Risk:** it steers the agent. Keep it opt-in per agent, report block-rate and retry cost,
  and never block twice.

### 3.2 Generic subagent trace

Generalise `trace.py` from first-principles to any `agent_type`: start and stop, duration,
tools used, failed calls, sources fetched, the final message, and the router notes placed on
its timeline. Agent-specific parsing (sections, gate) becomes a plug-in per agent, and falls
back to the contract block of 3.1 when present. The demo's Trace tab already renders this shape.

- **Test:** replay existing captures (`--replay`) for first-principles, then one run each of
  Explore and general-purpose.

### 3.3 Source broker for failed fetches (PostToolUseFailure + a catalog tool)

On 2026-09-29, NREL hosts failed in 4 runs and `science-engineering` got 0 of 2 sources, so
ground truths stayed `?`. A `fetch-with-fallback` MCP tool tries the page, then a
web-archive copy, and returns Markdown (reusing `html_to_markdown`). A note after a failed
`WebFetch` points at it. The trace already records `failed_hosts`, which gives a before and
after measure.

- **Test:** the failing hosts from the 14-example run; count ground truths moved from `?` to read.

### 3.4 Eval hygiene guard (PreToolUse deny, only in eval runs)

When an env var marks a run as an eval, a catalog of forbidden paths (answer keys, gold
outputs, fixtures) is enforced: `Read`/`Grep`/`Bash` on them is denied with a neutral reason.
This turns the `†` flag from after-the-fact detection into prevention, for any benchmark this
repo runs.

- **Test:** rerun `self-application`; the read is denied and logged, and the run completes.

### 3.5 More deterministic tools where agents improvise

The trace shows what agents compute in scripts. 67 interpreter calls in one run did not fit
the calculator. Candidate tools, each MIT, each with a `fits:` check:
- unit conversion with dimensions (pint is BSD, so write our own or find an MIT one)
- date and time arithmetic
- descriptive statistics over a CSV column
- a sandboxed multi-line expression evaluator (names and assignments, no imports or I/O)

Start from the trace data: tabulate `interpreter` calls across runs, cluster them, and add a
tool only where a cluster is large and a fit check can be exact.

### 3.6 Delegation router for more agents (UserPromptSubmit / PreToolUse Agent)

The first-principles delegation note generalises to a catalog of subagents (Explore, Plan, a
code reviewer, a security auditor), each with exemplars and `not_for`. The router already picks
from a fixed list; the entries are agents instead of tools. Known gap to carry over:
quantitative phrasings scored `none` for first-principles, so each entry needs its own
calibration.

- **Test:** the existing `battery.py` pattern: fresh `claude -p` per prompt, with and without
  the plugin.

### 3.7 Loop and cost guards (PreToolUse + trace state)

The per-session state file can count identical calls (same tool, same input hash) and turns per
subagent. On the third identical failing call, add a note; past a turn budget, add a note
asking the agent to write what it has. This stays advisory. The first-principles runs used 3–7
turns, so a budget can be set from data.

### 3.8 Output shaping for large tool results (PostToolUse, MCP only)

`updatedMCPToolOutput` can trim or summarise a large MCP result before it fills the context,
e.g. turn a large JSON result into a JMESPath-selected view. Probe it first. It only applies to
MCP tools, not built-ins.

### 3.9 Session-level catalog note (SessionStart)

One short note at session start listing the approved tools, instead of relying only on
per-call notes. It may raise calculator use without per-call cost. Measure it against the
known gap: use followed the delegating prompt, not the note.

### 3.10 Cross-run regression dashboard (demo)

The demo already reads audit and trace folders. Add a view that lines up the same example
across run folders (`2026-09-29-examples`, `-rerun`, `-latest`, …): status, cost, gate,
calculator use, coverage of each parsed field. This is what tells you whether a code change
helped, rather than whether a new scenario looks odd.

## 4. Suggested order

| # | Item | Why first | Effort |
|---|---|---|---|
| 1 | §2 item 2, "unknown over guess", in `trace.py` | removes the only harmful class of miss | small |
| 2 | 3.10 regression view | makes every later change measurable | small–medium |
| 3 | 3.1 output-contract gate | ends prose parsing; works for agents we do not own | medium |
| 4 | 3.2 generic subagent trace | the same trace for every agent | medium |
| 5 | 3.4 eval hygiene guard | cheap, prevents contaminated runs | small |
| 6 | 3.3 source broker | the largest cause of unverified ground truths | medium |
| 7 | 3.5 / 3.6 / 3.7 / 3.8 / 3.9 | driven by what the trace shows | per item |

Each item keeps the rules in section 2: fail open, advisory unless named, record-only traces,
measured with the fixed example set before and after.
