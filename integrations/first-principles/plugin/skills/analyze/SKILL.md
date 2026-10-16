---
name: analyze
description: Runs one complete first-principles analysis of a question as a conducted workflow. Composes the delegating prompt (recording the install checks and the router's preflight, which never stop the run), hands it to the first-principles agent once, then reads the finished analysis against the published summary contract and shows the same rendered report a plain-prompt run ends with (answer, confidence, gate result, contract status and file paths). Never edits, re-scores or re-runs the analysis. Invoked only as a slash command.
argument-hint: <question to analyze from first principles>
disable-model-invocation: true
---

# Conduct a first-principles analysis

The question is: $ARGUMENTS

You sequence the run. The first-principles agent owns the analysis; you never edit, rewrite,
re-score or "fix" it, and you run the agent at most once per invocation. Nothing here blocks or
stops the run: install problems and an out-of-scope question are recorded at compose time and
shown in the report, exactly as for a run started from a plain prompt.

Helper: `"${CLAUDE_PLUGIN_ROOT}/bin/conduct"` prints one JSON object. Pass the question
through a quoted heredoc so it stays verbatim:
`"${CLAUDE_PLUGIN_ROOT}/bin/conduct" compose "$(cat <<'Q'` ... `Q` `)"`.

1. **Compose.** Run `"${CLAUDE_PLUGIN_ROOT}/bin/conduct" compose` with the question (add
   `--mode focused-<technique>` only if the user asked for one technique). Use Bash, not an MCP
   tool: it also runs the install checks and the router's preflight and writes the hand-off
   record the trace and the report use. Read `agent_type`, `prompt` and `sha256` from its output.
   Say nothing about its `checks`; the report carries them.
2. **Delegate.** Call the Agent tool with `subagent_type` set to the composed `agent_type` and
   `prompt` set to the composed `prompt`, character for character. Add no instructions. If the
   agent runs in the background, wait for its completion notification before step 3; report
   nothing about the analysis before then.
3. **Report.** Run
   `"${CLAUDE_PLUGIN_ROOT}/bin/conduct" report --markdown --handoff <sha256> <analysis path>`
   with Bash, taking the path from the agent's final message (leave it out and the newest
   analysis in the working directory is used). If Bash is unavailable, call
   `mcp__plugin_agent-router-fp_agent_router__verify_summary` with the path and `handoff` set to
   the `sha256`, and use its `report_markdown`. Your reply about the analysis is this report exactly as given, with
   nothing before or after it: do not summarise, reword, re-derive or add to it, and do not edit
   or re-run the analysis.

   The report is the same one a run started from a plain prompt ends with: the Answer (marked
   when it is cut), the conclusion and its confidence, whether the Self-Audit Gate cleared, the
   ground truths not read at source, the `contract_status` (with what it means when it is not
   `valid`), any install check or router preflight that was not clean, and the paths of the
   analysis, its reader report and the trace. If it says no analysis file was found, show the
   agent's final message unchanged after it. If the contract is not valid, report it as it is.
   Do not repair the analysis or run the agent again.
