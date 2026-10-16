# Live verification: robust first-principles integration (2026-10-15)

Plan: [`docs/plans/2026-10-15-fp-robust-integration.md`](../../docs/plans/2026-10-15-fp-robust-integration.md),
Phase 7 (VERIFY-01..03). These are **recorded observations from a few live runs, not gates**: each
reading is one run (K of N, N ≤ 2), and a later run can differ.

**Setup for every run:**
- Both plugins come from their working trees via `--plugin-dir`, never the plugin cache:
  - first-principles 9.20.0 on branch `feat/integration-manifest`, which publishes `references/integration.json`;
  - this plugin on branch `feat/fp-robust-integration`.
- `FP_PLUGIN_ROOT` points at the first-principles working tree.
- The model is `sonnet`, runs are serial, and each run has an isolated `AGENT_ROUTER_STATE_DIR`.
- Captures and state stay in the session scratchpad. They are not committed.

## VERIFY-01: one conductor run

`claude -p "/agent-router-fp:analyze Should a ten-person software team move to a four-day work
week, or is the five-day week just a convention we never questioned?"`

| Criterion | Observed |
|---|---|
| The run completes | yes: 8 main-session turns, 380 s for the agent, $1.35 |
| The conductor flow ran | `doctor`, then `route` (the first call used `question`, so it was retried with `text`; fixed in `d302b97`), then `compose`, `Agent`, `verify_summary` |
| `contract_status` | `valid`, 0 violations, `decisions_source: block`, `decisions_verified: true` |
| Manifest resolution | `source: env`, root = the first-principles working tree, `manifest_version` 1, no warnings |
| The delivery guard | did not need to block: `stop_attempt: 1`, `stop_hook_active: false` |
| One `run_end` | 1 |
| Router never blocked (D-02) | 23 audit checkpoints (22 tool `skipped`, 1 prompt `skipped`), 0 `enforce`, 0 downgrades, 0 `permissionDecision` / `block` outputs in the capture |
| Hand-off recognised | `delegation.launched_by: conductor`, `composed_sha256` matched |
| Calculator | the agent loaded both calculator tools via ToolSearch after the composed prompt's capability line, made 2 `calc_script` calls, and made **0** improvised interpreter calls |
| Gate / conclusion | gate cleared; conclusion confidence LOW; 2 ground truths not read at source |

## VERIFY-02: worked examples through `run_examples.py` (launcher entry)

### First attempt: both runs killed by the host (harness defect, fixed)

`estimate-fermi` and `personal-general` both came back `partial: no Self-Audit Gate` ($2.95).
Root cause, read from the captures:
1. In print mode, the main session's `Agent` call ran the agent **in the background**. The main
   session ended its turn after 2 turns.
2. The CLI stopped the background agent 10 minutes later. Its notice: "Background tasks still
   running 10m after the last turn … stopping them. Set CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0
   to wait indefinitely."
3. Each agent had written sections 1–6, with its gate and summary in the `.md.process` sidecar,
   but never assembled the file.
4. `run_examples.py` counted the async-launch acknowledgement as the agent's hand-back. The host
   marks it in `tool_use_result.status`, not in the text, so the killed runs read as `partial`.

Fix (`341c84c`): the harness sets `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` to its own `--timeout`.
It reads the stop notice from the capture and no longer mistakes the launch acknowledgement for
a hand-back. Re-reading the two failed captures with the fix gives `failed` with the true cause.

### Rerun with the fix

| Example | Status | Agent time | Cost | Contract | Decisions from | Gate bands | Fix/Repeat | Calculator | Interpreter calls |
|---|---|---|---|---|---|---|---|---|---|
| estimate-fermi | complete | 404.5 s | $1.14 | valid | block | RRSSRR | no | 0 | 3 (no note: below fit or threshold) |
| personal-general | complete | 890.9 s | $2.43 | valid | block | RRRSRS | yes | 7 calc records in the trace (the run summary counts 8 calc tool calls) | 0 |

- **Contract coverage line:** `valid 2/2 · prose fallback 0 · unsupported 0 · other 0`. Before
  this branch, every decision came from the prose parser.
- **The wait-ceiling fix mattered:** `personal-general` ran 14.8 minutes, so the 10-minute
  print-mode ceiling would have killed it again.
- **Router:** 41 audit checkpoints, 0 `enforce`, 0 calculator notes. Calculator use followed the
  launcher prompt, not router notes, as before.
- **Contradictions:** no block-vs-prose contradictions in either run.

### Compared with 2026-09-29 (14 examples, prose parser)

- **Then:** the parser misread 2 of 14 reports.
- **Now:** both runs' decisions come from the summary block, with no prose disagreement.
- **The calculator picture is unchanged:** use depends on the delegating prompt. The conductor's
  capability line (VERIFY-01) is the lever that removed improvised interpreter calls in that run.
- **Caveat:** two examples is not a regression set. Re-run all 14 serially before drawing
  conclusions about rates.

## Total live cost

$1.35 (VERIFY-01) + $2.95 (failed first attempt) + $3.57 (rerun) = **$7.87**.

## Route parity: conductor vs plain prompt (2026-10-16)

Branch `feat/route-parity`. The same question as VERIFY-01, three runs per route, run one at a
time and alternating (Route 1 `/agent-router-fp:analyze <q>`, Route 2 the plain question), with
`sonnet`, both plugins from their working trees via `--plugin-dir`, an isolated state dir per
run and `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=1800000`. These are recorded observations, N = 3
per route, not gates.

| Run | Route | Prompt sha256 | Launcher (record / trace) | Reply = report | Contract | Confidence | Gate | Ground truths (not read at source) | Assumptions | Chains | Agent s | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v1a | 1 | `6f87bae330…` | conductor / conductor | exact | valid | MEDIUM | cleared | 4 (3) | 11 | 4 | 725 | $1.91 |
| v1b | 1 | `6f87bae330…` | conductor / conductor | exact | valid | LOW | cleared | 8 (1) | 10 | 4 | 724 | $1.88 |
| v1c | 1 | `6f87bae330…` | conductor / conductor | exact | valid | MEDIUM | cleared | 6 (3) | 10 | 4 | 526 | $1.51 |
| v2a | 2 | `6f87bae330…` | router-hook / router-hook | blank line only | valid | MEDIUM | cleared | 5 (1) | 13 | 5 | 753 | $2.02 |
| v2b | 2 | `6f87bae330…` | router-hook / router-hook | exact | valid | MEDIUM | cleared | 7 (1) | 15 | 5 | 613 | $1.63 |
| v2c | 2 | `6f87bae330…` | router-hook / router-hook | exact | valid | MEDIUM | cleared | 7 (5) | 11 | 4 | 551 | $1.69 |

- **Same input:** all six agents got the byte-identical prompt. In Route 2 the main session
  wrote three different prompts of its own, and the hand-off hook replaced each one.
- **Same output form:** the reply equalled `conduct report` exactly in 5 of 6 runs. In `v2a`
  the model collapsed a double blank line the renderer left after a cut Answer; every word
  matched. The renderer no longer emits that double blank.
- **Analysis variation:** the counts and the trial designs vary as much within a route as across
  the two routes. With identical prompts and agent, the route cannot be the cause; this is the
  agent's own run-to-run spread. Every recommendation took the same direction: no outright
  switch; measure first, then a gated trial.
- An earlier pair before the wording fix (`r2`) added a lead-in sentence and a caveats list
  around the report. That led to the "nothing before or after it" instruction both routes now
  share; `r2b` and v2a–v2c followed it.
- **Total live cost of this section:** $1.85 (r2) + $1.51 (r1) + $1.95 (r2b) + $10.64 (v runs)
  = **$15.95**.
