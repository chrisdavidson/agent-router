# Changelog

All notable changes to this fork (`chrisdavidson/agent-router`) are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- The plugin root is now found from Claude Code's install record (`installed_plugins.json`),
  the copy the Agent tool actually runs, before the plugin cache is searched; it carries no
  stale-cache warning. In the cache, roots rank by manifest, then version, then file date,
  never by a directory's date: a leftover stub of 9.20.0, touched when 9.21.0 was installed,
  had been reported as the plugin root with a pinned-fallback warning.

## [0.3.0] — 2026-10-18

The first-principles integration grows: a live, swimlane Trace tab that says why each step happened,
a tool-gap report over past runs, a fuller `calc_script` and a new `document_text` tool for PDFs.

### Added

- **`document_text`: a PDF's own text.** A new MCP tool (`tools/document_text.py`, on
  pdfminer.six, MIT; not poppler's `pdftotext`, GPL, nor PyMuPDF, AGPL) returns the text of a PDF
  from a workspace file or an http(s) link, with a `[page N]` marker per page, `pages` to limit
  it (`"1-3,7"`) and `find` to return only the passages naming given terms. A link is fetched
  with httpx as `agent-router-document-text`, never posing as a browser; a scanned PDF (no text
  layer) is an error. The first-principles plugin serves it (`bin/mcp --tools`), traces it (a
  `document` record; the gap report counts it as covered) and names it in the conductor's
  composed prompt. Catalog `fp-2026-10-17.1` adds the `document-text` entry (`replaces: [Bash,
  WebFetch]`, `fits: reads_pdf`, threshold 0.8 calibrated: 8 of 8 cal cases, 3 of 3 holdout);
  the hooks still route only `Agent|Bash`. Re-run over the recorded PDF reads
  (`measure_document_text.py --fetch`): of 29 WebFetch calls on a PDF link, WebFetch's summary
  was useful once and said the fact was missing 22 times; `document_text` returned the
  document's text for 22 (the other 7: six hosts the agent guessed that do not resolve, one
  404) and the terms the agent asked for in 20. Where `pdftotext` output was recorded and the
  PDF is still on disk (2), `document_text` returns 98.8% of its words.

- **`calc_script` takes loops, lists and small functions.** The calculator's script form is now
  its own interpreter (`tools/calc_script.py`), still a walk over the syntax tree with exact
  fractions and nothing executed: `for`/`while`, `if`, comparisons, lists, tuples, dicts,
  indexing and slicing, comprehensions, tuple unpacking, non-recursive `def` and `lambda` (with
  defaults, `*args`, `**kw`), f-strings with format specs, `print(sep=, end=)`, `import math as
  m`, `from fractions import Fraction`, `float('inf')`, and the builtins the agents used (`sum`,
  `min`, `max` with `key=`, `round`, `range`, `zip`, `enumerate`, `sorted`, `len`, `dict`,
  `isinstance`, ...). Still no files, input, network, imports other than math, attributes other
  than a few container methods, or recursion; a step budget (200,000) and a time budget (10 s)
  stop a runaway loop, and an approximate value in a loop is kept to 60 digits instead of
  growing. An awk `BEGIN{...}` program is translated to the same language
  (`tools/awk_begin.py`). The router's `calc_script` fit check now also takes a script written
  with `cat > x.py <<'EOF'` and run with `python3 x.py`, a leading `cd DIR &&`, a trailing
  `2>&1` and the awk form, and gives the script 0.25 s inside the hook. Measured on this
  checkout's recordings (`measure_calc_fit.py`, which now also reads the tool-gap report's 197
  compute-script calls through their transcripts): the fit check accepts 80 of 156 captured
  interpreter calls (was 12) and 50 of the 53 plain-arithmetic calls in the trace (was 7 of
  197 compute calls); on the accepted calls, 3,041 of 3,043 numbers the calculator prints are
  in the real output (the two differ at an exact half-way `round`, where exact and binary
  floating point round apart). One script sits at the 0.25 s budget, so a run can count 79. Catalog `fp-2026-10-17.1`: the entry's `what`, `not_for` and
  examples say so; eval cases for loops, functions, write-then-run and awk.

- **Tool-gap report over past runs.** `make tool-gaps` (`integrations/first-principles/
  tool_gaps.py`) reads the trace hooks' records and the router's audit log from the hooks' state
  and every saved run, puts each thing the agent did in one pattern (compute script, PDF, curl,
  a source without the content, git, file inspection, housekeeping), joins it by `tool_use_id` to
  what the router made of it, and writes `TOOL-GAPS.md`: the router's checkpoint outcomes, one
  row per pattern, and the recurring needs (`--min-calls`, `--min-sessions`) as candidates for
  new tools. Counts and construct names only: never prompt or command text, URLs or host names
  (a pattern keeps how many distinct hosts it touched, not which); `--json`
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

- **Trace tab layout.** The tab is now about one screen instead of several: a swimlane chart of
  the run (agent, report, sources, compute, router) over the run's clock, a one-line-per-event log
  beside the decisions, each scrolling in its own pane, and the decisions as tabs (assumptions,
  chains, Self-Audit Gate, ground truths, dead ends, techniques not applied, sections). Clicking a
  mark selects its line in the log. Repeated checks of one source fold into one line, the summary
  shows the key numbers and folds the rest under **More about this run**, and a live refresh keeps
  the chosen tab, the selection and the log's scroll position (following the newest event when the
  log was at its end). On a saved 57-event run the page went from about 6,500 px to about
  1,650 px tall in a 1280×1000 window.


- **Neither way of starting a run stops it** (chosen 2026-10-16). `compose` runs the `doctor`
  checks and the router's preflight, time-bounded, and keeps them in the hand-off record;
  `conduct report --handoff <sha256>` shows whatever is not clean ("Install health", "Router
  preflight: ... analysed anyway", or "Run checks: not recorded"). The conductor skill no longer
  stops on a `doctor` FAIL or a declined preflight, so it and a plain-prompt run behave alike.

### Fixed

- **A run could show another run's report.** When the agent wrote its report through a shell
  variable (`D=/out; cat >> "$D/.first-principles/analysis-….md"`), the trace recorded the path
  unexpanded, missed it, and fell back to the newest analysis in the agent's folder, which could
  be days old and about a different question. `trace.py` now expands `VAR=` assignments from the
  command and never falls back to an analysis written before the run started. Traces already
  written that way are flagged in the Trace tab ("another run's report") with their decisions
  and confidence hidden.


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
