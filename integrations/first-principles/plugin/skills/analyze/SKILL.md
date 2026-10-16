---
name: analyze
description: Runs one complete first-principles analysis of a question as a conducted workflow. Checks the install, asks the router whether the question belongs to the first-principles agent, composes the delegating prompt, hands it to that agent once, then reads the finished analysis against the published summary contract and reports the answer, confidence, gate result, contract status and file paths. Never edits, re-scores or re-runs the analysis. Invoked only as a slash command.
argument-hint: <question to analyze from first principles>
disable-model-invocation: true
---

# Conduct a first-principles analysis

The question is: $ARGUMENTS

You sequence the run. The first-principles agent owns the analysis; you never edit, rewrite,
re-score or "fix" it, and you run the agent at most once per invocation. Nothing here blocks.
Stop at a step only where it says so.

Helper: `"${CLAUDE_PLUGIN_ROOT}/bin/conduct"` prints one JSON object. Pass the question
through a quoted heredoc so it stays verbatim:
`"${CLAUDE_PLUGIN_ROOT}/bin/conduct" compose "$(cat <<'Q'` ... `Q` `)"`.

1. **Health.** Call the MCP tool `mcp__plugin_agent-router-fp_agent_router__doctor`. If it is
   unavailable, run `"${CLAUDE_PLUGIN_ROOT}/bin/conduct" doctor` with Bash. If any
   check is `FAIL`, show the failing lines and stop. If the plugin root is a `WARN` saying it came
   from the plugin cache, tell the user once that a stale installed copy of the agent may run, and
   that `FP_PLUGIN_ROOT=<plugin dir>` or `"${CLAUDE_PLUGIN_ROOT}/bin/conduct" record-root <plugin dir>`
   fixes it; then continue.
2. **Preflight.** Call `mcp__plugin_agent-router-fp_agent_router__route` with `text` set to the
   question
   (fallback: `"${CLAUDE_PLUGIN_ROOT}/bin/conduct" preflight`). If it does not choose the
   first-principles agent, say this is not a first-principles question and stop, unless the user's
   text insists on an analysis.
3. **Compose.** Run `"${CLAUDE_PLUGIN_ROOT}/bin/conduct" compose` with the question (add
   `--mode focused-<technique>` only if the user asked for one technique). Use Bash, not an MCP
   tool: it also writes the hand-off record the trace uses. Read `agent_type` and `prompt` from
   its output.
4. **Delegate.** Call the Agent tool with `subagent_type` set to the composed `agent_type` and
   `prompt` set to the composed `prompt`, character for character. Add no instructions.
5. **Verify.** Take the analysis path from the agent's final message, or from
   `"${CLAUDE_PLUGIN_ROOT}/bin/conduct" latest-analysis`. Call
   `mcp__plugin_agent-router-fp_agent_router__verify_summary` with that path (fallback:
   `"${CLAUDE_PLUGIN_ROOT}/bin/conduct" verify <path>`, which also lists the reader report and
   trace paths). No analysis file: say so and report the agent's final message as it is.
6. **Report** to the user, from the verification result and nothing re-derived:
   - the Answer excerpt;
   - the conclusion and its confidence;
   - whether the Self-Audit Gate cleared;
   - `contract_status`, and when it is not `valid` one line on what that means: the summary block
     could not be read or did not match the published schema, so the figures above are unverified;
   - the number of ground truths not read at source;
   - paths: the analysis, its reader report (`report-<UTC>.md` / `.pdf` beside it, if present) and
     the trace directory.

   If the contract is not valid, report it as it is. Do not repair the analysis or run the agent
   again.
