# calc_script coverage (offline measurement)

Counts only; no prompt or command text. Regenerate with
`python3 integrations/first-principles/measure_calc_fit.py --write`.
Measured 2026-10-18 over 65 local captures
(`runs/*/*/run.jsonl`, untracked; they are not in the repository, so the figures are a
snapshot of this checkout's recordings, not reproducible from a fresh clone).

## Method

1. `trace.replay_payloads` rebuilds the hook payloads of the plugin's agent from
   each capture. A call is every Bash call whose command matches `trace.INTERPRETER`.
   Commands naming the plugin's report directory are the agent writing its report; the
   router never routes them, so they are counted apart and left out of the rates. Calls
   repeated across captures (same session and tool-use id) are counted once.
2. `calc_expression` and `calc_script` (`core/fit.py`) are applied to each call's input,
   as the router's fit check does. They never both accept one call.
3. AGREEMENT, for calls `calc_script` accepts and whose real result was recorded:
   `calc_script.run` runs the script; each number it shows (a `<source> = <value>`
   value, a list item, an f-string field as formatted) must be found among the
   numbers in the recorded stdout of the real call, within 1e-06 relative
   (1e-09 absolute), each real number used at most once. The check is directional
   because the real output's labels also contain digits. A call whose script prints no
   number the calculator can show, and a call that failed, are not compared.

## Result

| Measure | Calls |
|---|---|
| interpreter calls (excluding report commands) | 156 |
| accepted by `calc_expression` (one expression) | 2 (1%) |
| accepted by `calc_script` | 78 (50%) |
| accepted by either | 80 (51%) |
| refused by both | 76 (49%) |
| plain arithmetic (see Method) | 86 |
| plain arithmetic accepted | 80 (93%) |
| failed calls among the interpreter calls | 3 |
| report commands excluded | 224 |
| duplicate calls dropped | 0 |

### Agreement on the `calc_script`-accepted calls

| Measure | Count |
|---|---|
| compared | 78 |
| agree (every calculator value found in the real output) | 76 (97%) |
| values compared / found | 3043 / 3041 |
| accepted but the call failed | 0 |
| accepted but no numeric value printed | 0 |

### Why the other calls are refused (by both)

| Reason | Calls |
|---|---|
| shape: python, not a heredoc or -c script | 46 |
| script: only 'X' is supported | 11 |
| shape: other shell command | 10 |
| script: result too large | 2 |
| shape: awk/bc/dc/expr/node | 2 |
| script: accepted by evaluate_script but refused by the fit check | 2 |
| script: method .read() is not supported | 1 |
| script: math.radians is not supported | 1 |
| script: step budget exceeded (limit 200000): a loop runs too long | 1 |

### Disagreements

- decompose-irreducibility: 68/69 values found
- science-engineering: 51/52 values found

## Over the trace: the tool-gap report's compute-script calls

The population `tool_gaps.py` reports as *Multi-step compute scripts*, from the hooks'
state and every saved run's. Each call's full text comes from a capture, else the
agent's Claude Code transcript, else the trace's own command when it was not cut off
at 200 characters.

| Measure | Calls |
|---|---|
| compute-script calls in the trace | 197 |
| full text found | 135 |
|   from a capture | 84 |
|   from a Claude Code transcript | 42 |
|   the trace's own (not cut off) | 9 |
| full text gone (cut off, no transcript) | 62 |
| accepted by either fit check | 50 (37%) |
| plain arithmetic | 53 |
| plain arithmetic accepted | 50 (94%) |
| agreement: calls compared / agree | 46 / 44 |
| agreement: values compared / found | 2270 / 2268 |

| Why the other calls are refused (by both) | Calls |
|---|---|
| shape: python, not a heredoc or -c script | 60 |
| shape: other shell command | 10 |
| script: only 'X' is supported | 9 |
| shape: awk/bc/dc/expr/node | 2 |
| script: result too large | 1 |
| script: method .read() is not supported | 1 |
| script: accepted by evaluate_script but refused by the fit check | 1 |
| script: step budget exceeded (limit 200000): a loop runs too long | 1 |

## Reading it

Acceptance is what the router can offer; agreement is whether following the note would
have produced the same figures. A disagreement is a calculator-vs-float difference or a
script the real interpreter treated differently (integer division, rounding), not a
decision the router made.
