# Tool calls for robustness: what was added, what it measured, what is next

Date: 2026-10-15 · Branch: `feat/fp-robust-integration` · Companion to
[`2026-10-15-fp-robust-integration.md`](2026-10-15-fp-robust-integration.md).

The question: where does replacing improvised shell work with a **structured tool call** make
agent-router (and the agents it sits beside) more robust? A tool call has typed input, a
typed result, no shell quoting, its own permission entry, and errors the model can read
(`ToolError`), where a Bash pipeline fails silently or differently every time.

## 1. Added in this branch

| Tool (MCP, `agent_router` server) | Who calls it | Replaces | Phase |
|---|---|---|---|
| `calc_script(script)` | the first-principles agent, on the router's note | multi-line `python3` arithmetic scripts | 6a |
| `calc` + `log`/`ln`/`log10`/`log2`/`exp`/`pi`/`e` | the agent | `math.log` scripts the calculator refused (it answered "log() is not supported") | 6a |
| `route(text, point, tool, tool_input_json, agent_type)` | the conductor (main session) | `agent-router route --json` through Bash | 6a |
| `verify_summary(path)` | the conductor | reading and judging the report's summary block by hand | 6a |
| `doctor()` | the conductor, step 0 | ad-hoc "is it installed right?" debugging | 6a |

All are read-only and advisory. None can block (D-02); `route` honours the never-block set and
writes no audit record.

### Measured (offline, 65 local captures, `integrations/first-principles/CALC-SCRIPT-COVERAGE.md`)

| | Interpreter calls inside the agent |
|---|---|
| total | 156 |
| `calc_expression` fits (one expression) | 2 (1%) |
| `calc_script` fits (straight-line script) | 10 (6%) |
| refused by both | 144 (92%) |
| agreement on the 10 accepted | 10/10 calls, 172/172 values within 1e-6 |

So the script tool is **correct but narrow**. The refusals, by cause:

| Cause | Calls | Could a tool take it safely? |
|---|---|---|
| python written to a file by heredoc, then run | 34 | no as one call; the write and the run are two tool calls |
| `cd <dir> &&` prefix | 32 | **yes**: strip a leading `cd <literal path> &&` in the fit check; the script is the same |
| `for` loops | 17 | **partly**: `for x in [literal list]` with an iteration cap is still a finite, parse-only evaluation |
| function definitions | 9 | no (keep the evaluator non-Turing-complete) |
| awk / bc / dc / expr / node | 9 | some already via `calc_expression`; the rest are multi-statement |
| imports other than `math` | 8 | no (statistics/numpy: out of scope for an exact calculator) |
| lists / `sum` / `min` / `max` | 7 | **yes**: list literals plus `sum`/`min`/`max`/`len` over them |

Widening the three "yes" rows could take the script tool from 10 to at most about 50 of 156
calls. That is an upper bound, since a call refused for one cause may also hit another.
Measure it with the same script before claiming it.

## 2. Next candidates, ranked by evidence over effort

1. **Widen `calc_script` (the three "yes" rows above).** The evidence is in the table. Effort
   is small. Re-run `measure_calc_fit.py` and keep the 100% agreement bar.
2. **Offer `verify_summary` to the agent itself, advisory only.** On the Phase 1 fixtures, 3 of
   3 live reports failed the published schema (`conclusion.rests_on` missing), and the agent
   never learned this. A `SubagentStart` note ("you can check your summary block with
   `…verify_summary` before you finish") lets the agent self-check without the router blocking
   anything. The stop decision stays with first-principles' own delivery guard. Measure the
   contract-valid rate in live runs before and after.
3. **`SessionStart` health note.** Run the doctor checks once per session from a hook. Add one
   line only when something is FAIL or the plugin root is the stale cache. On this machine the
   cache holds 9.15.0 against a 9.20.0 working tree, which no one would otherwise notice.
4. **`fetch_with_fallback(url)`, a source broker.** On 2026-09-29 one host failed in 4 runs, and
   a ground truth stayed `?` each time. The tool tries the page, then an archived copy, and
   returns Markdown (reusing `html_to_markdown`). A note after a failed `WebFetch` points at it.
   Measure ground truths moved from `?` to read.
5. **`trace_report(session)`.** The conductor's final report could add what the trace saw (tool
   failures, calculator use, guard retries). Today it needs a path and a separate CLI.

What not to do: tools that write the agent's report, change its gate, or decide when it may
stop. Those belong to first-principles (D-09), and a router tool there would be a strong
coupling in disguise.
