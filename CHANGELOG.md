# Changelog

All notable changes to this fork (`chrisdavidson/agent-router`) are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Tool-gap report over past runs.** `make tool-gaps` (`integrations/first-principles/
  tool_gaps.py`) reads the trace hooks' records and the router's audit log from the hooks' state
  and every saved run, puts each thing the agent did in one pattern (compute script, PDF, curl,
  a source without the content, git, file inspection, housekeeping), joins it by `tool_use_id` to
  what the router made of it, and writes `TOOL-GAPS.md`: the router's checkpoint outcomes, one
  row per pattern, and the recurring needs (`--min-calls`, `--min-sessions`) as candidates for
  new tools. Counts, hosts and construct names only, never prompt or command text; `--json`
  writes the same figures for the candidate store that comes next. On this checkout's 71 runs:
  multi-step compute scripts (197 calls), sources without the content (67), PDFs (42), curl
  fetches (30) and git (22) are candidates; the router had no entry for any of them.
- **One name and one address per session across the demo's tabs.** Replay now calls a session
  what the Trace tab does (the delegated task, else the user's words, else the report title) plus
  its short id, e.g. `First-principles LLC analysis · 12be92f6`, instead of the full id and the
  first 48 characters of the prompt. `/api/audit/sessions` rows gain `label`, `label_source` and
  `has_trace`; `/api/trace/sessions` rows gain `has_audit`. The address holds the session
  (`#trace/<id>`, `#replay/<id>`), so refresh, back/forward and shared links open it, and a linked
  Trace session is pinned against Follow live. Replay gains **Open its trace** when the session
  has one, alongside Trace's existing link to the checkpoints.
- **Whether a fetch worked, in the trace.** Each `WebFetch` source record now keeps the page's
  HTTP `status` and `status_text`, its downloaded `bytes`, and an `excerpt` of the reply the agent
  got. A status of 400 or above is `outcome: "http_error"` (a 403 used to read as
  `reported_missing`, and only because "403" appeared in the JSON), and the run's source checks
  count them as `http_error` with `http_error_hosts`. The Trace tab shows the status and size as a
  chip on each source row (e.g. `200 OK · 104 KB`, `403 Forbidden · 0 B`), the reply under "what
  the agent was told", and an "HTTP error" chip in the summary. `chars` is now the reply's length,
  not the length of WebFetch's whole response as JSON. Traces from before this change have no
  status.
- **Why each step happened, in the Trace tab.** The demo server reads the agent's own Claude Code
  transcript (`GET /api/trace/<session>/why`, `demo/why.py`) and joins it to the trace by
  `tool_use_id`. The event log puts each of the agent's messages above the calls it led to, marks
  quiet stretches of 30 s or more, and labels shell rows with the agent's own note on the command
  (Bash `description`). Selecting an event opens a **Why?** tab: what the agent said before it
  (flagged when minutes old), its note on the call, its reasoning if kept, the phase, the router's
  checkpoint on the call (or that its hooks never saw it, with its last check before), the
  delegating prompt's line that offered the tool, outcome and retry, what it said next, and the
  later calls that repeat a calculator result's numbers (a match, not proof). On a narrow screen a
  click scrolls the tab into view; with the log focused, arrow keys step through events. The trace
  hooks now record `transcript_path` (and `agent_transcript_path` at stop) when Claude Code passes
  them; older traces fall back to `~/.claude/projects/*/<session>/subagents/` (or
  `$CLAUDE_CONFIG_DIR`).
- **The why outlives the transcript.** Claude Code deletes old transcripts, so the trace keeps
  its own copy: each tool record carries the agent's note on the call (`purpose`), and `run_end`
  carries `why` (the agent's messages and per-call links, compacted). The Why? tab uses the
  transcript while it exists, then the kept copy. For traces written before this,
  `trace.py --keep-why <trace dir>` copies the same data in while the transcripts still exist
  (additive; each changed trace's original is saved as `<session>.jsonl.bak`).

### Fixed

- **A run could show another run's report.** When the agent wrote its report through a shell
  variable (`D=/out; cat >> "$D/.first-principles/analysis-….md"`), the trace recorded the path
  unexpanded, missed it, and fell back to the newest analysis in the agent's folder, which could
  be days old and about a different question. `trace.py` now expands `VAR=` assignments from the
  command and never falls back to an analysis written before the run started. Traces already
  written that way are flagged in the Trace tab ("another run's report") with their decisions
  and confidence hidden.

### Changed

- **Trace tab layout.** The tab is now about one screen instead of several: a swimlane chart of
  the run (agent, report, sources, compute, router) over the run's clock, a one-line-per-event log
  beside the decisions, each scrolling in its own pane, and the decisions as tabs (assumptions,
  chains, Self-Audit Gate, ground truths, dead ends, techniques not applied, sections). Clicking a
  mark selects its line in the log. Repeated checks of one source fold into one line, the summary
  shows the key numbers and folds the rest under **More about this run**, and a live refresh keeps
  the chosen tab, the selection and the log's scroll position (following the newest event when the
  log was at its end). On a saved 57-event run the page went from about 6,500 px to about
  1,650 px tall in a 1280×1000 window.

### Added

- **Route parity.** A first-principles run started from a plain prompt now ends like one started
  with `/agent-router-fp:analyze`: the same delegating prompt and the same report. New hand-off
  hooks (`plugin/bin/handoff-hook` -> `conduct.py hook`, steering only, never a deny or a block)
  rewrite the main session's `Agent` prompt to the composed one at `PreToolUse`, and at
  `PostToolUse` hand the main session the rendered report, or, for a background run, the report
  command to run when it finishes. One renderer (`integration_tools.render_report`) serves both
  ways. `conduct.py report [--markdown]` is the skill's report step. The trace's `run_end` records
  `launched_by` (`conductor` / `router-hook`), resolved after the run because hooks on one event
  run in parallel. `doctor` fails the wiring check when either half of the pair is missing.
- **Live Trace tab.** The demo's Trace tab follows a run as it happens: with **Follow live** on it
  re-reads `/api/trace/sessions` every 3 seconds and opens a new run when it starts, keeping open
  sections and scroll position. Mid-run the card shows elapsed time, sections, references and
  source checks so far. Session summaries are cached on file size and mtime.
- **Session labels.** Each trace session is named by the hand-off's `description` (now recorded
  in the trace's `delegation` record, at most 120 characters), else the user's first prompt from
  the audit log, else the report title, and shows `running` / `unfinished` (open, quiet for 10
  minutes) / `finished`, last activity and the conclusion's confidence.
- **`agent-router demo --state-dir <root>`** reads `<root>/audit` and `<root>/trace`
  (`--audit-dir` / `--trace-dir` win). **`make trace`** runs it on the hooks' state root
  (`$AGENT_ROUTER_STATE_DIR`, else `$XDG_STATE_HOME/agent-router`), or `STATE=<dir>`.
- **Marketplace install.** `.claude-plugin/marketplace.json` lists `agent-router-fp`, so
  `claude plugin install agent-router-fp@agent-router` works. An installed copy finds the
  checkout's integration directory through `AGENT_ROUTER_FP_INTEGRATION`, read only when the
  plugin does not sit in a checkout (`plugin/bin/_resolve.sh`, `AR_INTEG`).

### Changed

- **Neither way of starting a run stops it** (chosen 2026-10-16). `compose` runs the `doctor`
  checks and the router's preflight, time-bounded, and keeps them in the hand-off record;
  `conduct report --handoff <sha256>` shows whatever is not clean ("Install health", "Router
  preflight: ... analysed anyway", or "Run checks: not recorded"). The conductor skill no longer
  stops on a `doctor` FAIL or a declined preflight, so it and a plain-prompt run behave alike.

### Fixed

- The MCP `verify_summary` result now carries the paths of the analysis, its reader report and
  the trace (only the CLI had them), plus `report_markdown`.
- A cut Answer excerpt is marked: `answer_truncated` in the result, and a note in the report.

## [0.2.0] — 2026-10-16

A robust, loosely coupled integration with the first-principles plugin (works with
first-principles 9.21.0, and falls back to a pinned identity for earlier versions). Plan:
`docs/plans/2026-10-15-fp-robust-integration.md`; live results:
`integrations/first-principles/VERIFICATION.md`.

### Added

- **Reading the summary contract** (`agent_router.contracts`). The trace reads the analysis's
  structured-summary block and checks it against the publisher's schema file. Only when the
  block is missing or invalid does it fall back to parsing the prose. Every run records
  `contract_status` and `decisions_source`, and `--report` ends with a line saying how many runs
  were read from the block.
- **Integration manifest.** The first-principles plugin's name, agent, paths and schema now
  come from its published `references/integration.json`, falling back to a pinned copy, instead
  of being hard-coded. A descriptor names each integration.
- **`agent-router doctor --integration <dir|name>`.** It runs 15 install checks, including a
  real MCP round trip, and warns when the plugin found is a stale copy from the plugin cache.
  `agent-router --version` is also new.
- **Calculator.** The new `calc_script` tool runs straight-line arithmetic scripts: it parses
  them and never executes them. `log`, `exp`, `pi` and `e` work, returning approximate values.
  A matching fit check and catalog entry let the router suggest it.
- **Integration MCP tools:** `route`, `verify_summary` and `doctor`.
- **The conductor `/agent-router-fp:analyze`.** It runs one first-principles analysis end to
  end: health check, preflight, composing the prompt, delegating, verifying and reporting. It
  never edits, re-scores or re-runs the analysis. `conduct.py` offers the same steps as
  commands that print JSON.
- **Test coverage:** committed fixtures, golden tests that freeze the trace's output, and a
  benchmark that fails if hook latency exceeds twice its recorded baseline.

### Changed

- **Fail-open hooks.** The hook scripts no longer `exec` the router. A crash, a hang (cut off at
  12 s), empty output or any non-object output becomes `{}`.
- **Install order.** The scripts look for the router in this order: an explicit
  `AGENT_ROUTER_BIN` / `AGENT_ROUTER_PYTHON`, then the checkout's `.venv`, then `PATH`.
- **Example runs.** `run_examples.py` reads worked examples from the installed plugin and sets
  the print-mode wait ceiling (`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`) to its own timeout.

### Fixed

- **Lost session state.** Concurrent hooks in one session no longer overwrite each other's
  updates. Writes are merged under a lock, and a burst of hooks yields exactly one note.
- **Never blocking first-principles.** The router never denies a first-principles call, even
  in enforce mode: a would-be deny is downgraded to advice and recorded in the audit log.
- **Repeated stops.** A run that stops more than once (the delivery guard retrying it) is
  counted once.
- **Killed example runs.** When print mode stops a background agent, `run_examples.py` reports
  a failed run, not a partial one.
- **`route` parameter.** The `route` tool accepts `question` as another name for `text`.

## [0.1.0]

Initial MVP (upstream `usathyan/agent-router`).
