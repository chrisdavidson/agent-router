# Fixtures for the first-principles integration (TRACE-01)

Committed inputs and golden outputs for `tests/test_fp_characterisation.py`, plus the latency
baseline for `tests/test_bench_hook_latency.py`. Assembled 2026-10-15 on branch
`feat/fp-robust-integration`. Nothing here was written by hand except the files marked
"synthetic" or "hand-built". No secrets: the files were checked for API-key shapes and e-mail
addresses (none), and home-directory paths were rewritten (see captures).

Do not edit a fixture to make a test pass. Goldens in `expected/` are regenerated with
`UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_fp_characterisation.py`, and the resulting diff is
reviewed: it is the list of intended behaviour changes. The goldens freeze `trace.py` as it is,
wrong answers on the negatives included.

## reports/valid/ (5 reports, each with one structured-summary block)

| file | provenance |
|---|---|
| `live-estimate-fermi.md` | Real agent output from the local live run `integrations/first-principles/runs/structured-summary-live/` (2026-09-30/10-01, untracked), example `estimate-fermi`. The analysis file was gone, so the text is the `analysis_text` of that run's `run_end` record in `state/trace/93ec2541-*.jsonl`. `analysis-20261001T012816Z.md`. |
| `live-personal-general.md` | Same run, example `personal-general`, `state/trace/d9a65ac1-*.jsonl`, `analysis-20261001T013849Z.md`. |
| `live-software-systems.md` | Same run, example `software-systems`, `state/trace/e183726d-*.jsonl`, `analysis-20261001T020055Z.md`. |
| `example-product-business.md` | Shipped worked example, copied from `~/Projects/first-principles-skill/first-principles/references/examples/product-business.md` (first-principles 9.20.0 working tree). Legacy layout: no Self-Audit Gate section. |
| `example-theoretical-limit-carnot.md` | Same source directory, `theoretical-limit-carnot.md`. |

FP version of the three live reports is not recorded in the run directory. The block shipped in
first-principles 9.16 (`integrations/first-principles/handoff/v9.16-structured-summary-report.md`),
and each of these three reports carries one (checked 2026-10-15). The two examples are 9.20.0.

## reports/negative/ (synthetic, six cases)

All six are minimal edits of `reports/valid/live-estimate-fermi.md` (it has a Self-Audit Gate
section before the block, which `misplaced` needs). The block section is the final
`## Structured summary (process output)` heading and its one fenced `json` block.

| file | edit |
|---|---|
| `absent.md` | the block section (heading and fence) removed; file ends after the Self-Audit Gate section |
| `multiple.md` | the whole block section appended a second time at the end of the file |
| `misplaced.md` | the block section moved to just before `## Self-Audit Gate (process output)`, so it is no longer last |
| `invalid_json.md` | block closing brace removed and a trailing comma left, so the fence holds truncated JSON |
| `unsupported_version.md` | `"schema_version": 1` changed to `2`; nothing else |
| `dangling_rests_on.md` | `"GT-99"` appended to chain C1's `rests_on` (no `GT-99` in the block) |

## schema/summary-schema.json

Pinned copy of `~/Projects/first-principles-skill/first-principles/references/summary-schema.json`
(9.20.0, last touched in commit 2628e725 of that repo). A field table, not JSON Schema. For the
Phase 2 validator tests, so they do not depend on a first-principles checkout.

## captures/

* `estimate-fermi.jsonl` (104 KB): a `claude -p --output-format stream-json` capture, from
  `runs/structured-summary-live/estimate-fermi/run.jsonl` (295 KB). Chosen because it replays to
  one finished run with decisions, a failed and a successful source check, reference reads and
  nine appended sections. Rewritten and trimmed by these rules; replaying the original and the
  trimmed file gives identical trace records except the `chars` of `source` records, which are
  the lengths of web results that were cut:
  * home-directory paths and the local username rewritten to `user`, and the run directory to
    `/fixture/run`;
  * dropped events: `system` events other than `init`, `task_started`, `task_updated`,
    `task_notification`; all `rate_limit_event`, `tool_progress`, `result`;
  * `init` reduced to `type, subtype, cwd, session_id`;
  * dropped `thinking` blocks, `usage` and `uuid` keys; `text` blocks and tool-result text
    cut to 600 characters;
  * everything else (tool_use inputs, so the heredocs that build the report, Agent prompt and
    result, timestamps) kept verbatim.
* `guard-blocked-payloads.json` (hand-built): no real capture shows a guard block. The
  first-principles captures in `tests/pointer-fix`, `tests/example-rerun-2` and
  `tests/skip-paired` were recorded without the SubagentStop guard active; the guard's gate
  (`scripts/check-delivery-guard.py`) feeds them to the guard offline and only names which runs
  it would block. Replay of such a capture synthesises one `SubagentStop`, so it cannot show
  a block. So this is an ordered list of `{ts, payload}` hook payloads in the shapes
  `trace.py` already handles: delegation `PreToolUse`, `SubagentStart`, `Bash` post-tool calls that
  create and append report sections, then `SubagentStop` with `stop_hook_active` false (guard
  blocks), more tool calls, `SubagentStop` with `stop_hook_active` true (blocks again), one more
  append, and a final `SubagentStop` (`stop_hook_active` true, allowed). The test feeds them to
  `trace.handle`. Today this yields three `run_end` records; HOOK-05 will change that.

## The 9.21 schema fix (2026-10-16)

first-principles 9.21 marks `conclusion.rests_on` `"optional": true`: a block written before
that field existed may leave the key out. Against that schema the three live reports read as
`valid`. They failed the 9.20.0 schema (`schema/summary-schema.json`, kept as the pin of that
break). `schema/summary-schema-9.21.json` is the current copy, byte-identical to the trace's
pinned `integrations/first-principles/contract/summary-schema.json`.

* `reports/negative/schema_violation.md`: `live-estimate-fermi.md` with one edit, the block's
  `chains[0].confidence` set to `"CERTAIN"` (not in the enum). It is the fixture for "a block
  that does not match the schema", the role the live reports played under 9.20.0.

## expected/

Golden outputs: `<valid|negative>-<name>.json` is `parse_analysis` of that report;
`capture-<name>.json` is every trace record the capture produces (state-dir path normalised,
`analysis_text` shown as a length; timestamps come from the capture and are deterministic).

## latency-baseline.json

HOOK-04 baseline from `tests/test_bench_hook_latency.py` (`make bench`): p50 and p95 in
milliseconds over 20 runs of `bin/hook`, for a routed `UserPromptSubmit` and a `PreToolUse`
`Bash` call from `first-principles:first-principles`. Recorded on one host (named in the file);
the test fails at 2x the baseline p95. Rewrite with `UPDATE_BASELINE=1 make bench`.
