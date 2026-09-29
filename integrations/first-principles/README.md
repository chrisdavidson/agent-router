# agent-router × first-principles

A self-contained Claude Code plugin (`agent-router-fp`) that runs next to the
[first-principles](https://github.com/chrisdavidson/first-principles-skill) plugin and leaves
it untouched. It adds two checkpoints that plugin does not have:

1. **Delegation nudge.** When your prompt (or an `Agent` call the main session is about to
   make) looks like a first-principles question, the main session gets a short note: delegate
   it to `first-principles:first-principles`. A prompt that does not fit gets no note.
2. **Exact recompute.** Inside the first-principles agent, when it reaches for `python3 -c`,
   `bc` or similar to compute a figure (Phase 4 estimates, Phase 5 "recompute every computed
   figure"), it gets a note pointing at an exact calculator this plugin serves
   (`mcp__plugin_agent-router-fp_agent_router__calc`, exact fractions and big integers).

Both are advisory: the model may ignore a note, and nothing is ever blocked.

**Who does what.** agent-router decides *whether* to hand a question to the agent and offers
exact arithmetic. Everything inside the analysis stays with first-principles: Step 0 technique
selection, the slash-only skills, the Self-Audit Gate, the `.first-principles/` output file.
agent-router never points at an individual technique, and never routes the agent's own report
writes (any call naming `.first-principles/` is skipped before the classifier).

## Use it

```bash
make install                              # in this repo, once
claude --plugin-dir ~/Projects/first-principles-skill/first-principles \
       --plugin-dir ~/Projects/agent-router/integrations/first-principles/plugin
```

The hook finds `agent-router` in this repo's `.venv` (override with `AGENT_ROUTER_BIN`). If it
cannot run, it prints `{}` and the session carries on unchanged (fail open).

| Setting | Default | Meaning |
|---|---|---|
| `AGENT_ROUTER_BACKEND` | `local` | offline classifier; `cascade` asks Jev when unsure (needs a key) |
| `AGENT_ROUTER_THRESHOLD` | calibrated (`calibration.json`) | higher = fewer notes |
| `AGENT_ROUTER_DISABLED` | unset | `1` turns every checkpoint off |
| `AGENT_ROUTER_STATE_DIR` | `$XDG_STATE_HOME/agent-router` | per-session state and audit log |
| `AGENT_ROUTER_SKIP_INPUT` | `\.first-principles/` | tool calls matching this are never routed |

Hook cost: about 0.45 s per routed call (prompt, `Agent`, and `Bash` inside the agent). A
`Bash` call on the main thread is answered by the shell script in milliseconds, without Python.
Notes are once per turn per entry, so an analysis gets at most one calculator note.

Every checkpoint is logged to `<state dir>/audit/<session>.jsonl` (same format as the rest of
agent-router, plus `agent_type`).

## Files

| File | What |
|---|---|
| `catalog.yaml` | the two entries agent-router may point at (each scoped to one agent context, with its own threshold), plus the `none` exemplars |
| `eval_set.yaml` | `cal` cases written for this integration; `test` holdout = first-principles' own routing catalog (13 P, 20 N) plus Bash calls inside the agent |
| `calibration.json`, `calibrate.py` | classifier parameters, then one threshold per entry, all fit on the `cal` split only |
| `plugin/` | the Claude Code plugin: hooks, `.mcp.json`, `bin/hook`, `bin/mcp` |
| `battery.py` | live A/B: first-principles' routing catalog with and without this plugin |

## Measuring it

- **Offline:** `agent-router eval --catalog catalog.yaml --cases eval_set.yaml --skip-input
  '\.first-principles\b'` scores the catalog on the `test` holdout with the local
  classifier and `calibration.json`. `calibrate.py` re-fits the calibration on the `cal` split.
- **Live A/B:** `.venv/bin/python integrations/first-principles/battery.py` runs
  first-principles' routing catalog with and without this plugin, one fresh `claude -p`
  session per prompt, scored with first-principles' own `detect_routing`. It costs tokens; a
  delegated session is stopped at the delegation.

## Known gaps

- A quantitative decision phrased as "From first principles: is it cheaper to…" scored
  `none` for the delegation nudge (the examples are qualitative), and first-principles' own
  description did not route it either. Launch such questions with
  `/first-principles:first-principles-analysis`.
