# calc_script coverage (offline measurement)

Counts only; no prompt or command text. Regenerate with
`python3 integrations/first-principles/measure_calc_fit.py --write`.
Measured 2026-10-16 over 65 local captures
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
   `calc.evaluate_script` runs the script; each number it prints must be found among the
   numbers in the recorded stdout of the real call, within 1e-06 relative
   (1e-09 absolute), each real number used at most once. The check is directional
   because the real output's labels also contain digits. A call whose script prints no
   number the calculator can show, and a call that failed, are not compared.

## Result

| Measure | Calls |
|---|---|
| interpreter calls (excluding report commands) | 156 |
| accepted by `calc_expression` (one expression) | 2 (1%) |
| accepted by `calc_script` | 10 (6%) |
| accepted by either | 12 (8%) |
| refused by both | 144 (92%) |
| failed calls among the interpreter calls | 3 |
| report commands excluded | 224 |
| duplicate calls dropped | 0 |

### Agreement on the `calc_script`-accepted calls

| Measure | Count |
|---|---|
| compared | 10 |
| agree (every calculator value found in the real output) | 10 (100%) |
| values compared / found | 172 / 172 |
| accepted but the call failed | 0 |
| accepted but no numeric value printed | 0 |

### Why the other calls are refused (by both)

| Reason | Calls |
|---|---|
| shape: python, not a heredoc or -c script | 34 |
| shape: cd ... && prefix | 32 |
| script: for loop is not supported | 17 |
| shape: awk/bc/dc/expr/node | 9 |
| script: function definition is not supported | 9 |
| script: only 'X' is supported | 8 |
| script: list is not supported | 7 |
| shape: other shell command | 7 |
| script: only 'X' assignments are supported | 7 |
| script: lambda is not supported | 3 |
| script: cannot assign to 'X': it is a function or constant | 3 |
| script: dict is not supported | 2 |
| script: unknown function 'X' | 2 |
| script: only plain calls to supported functions are allowed | 2 |
| script: comprehension is not supported | 1 |
| script: name 'X' is not defined | 1 |

## Reading it

Acceptance is what the router can offer; agreement is whether following the note would
have produced the same figures. A disagreement is a calculator-vs-float difference or a
script the real interpreter treated differently (integer division, rounding), not a
decision the router made.
