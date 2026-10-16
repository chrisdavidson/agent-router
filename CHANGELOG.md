# Changelog

All notable changes to this fork (`chrisdavidson/agent-router`) are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
