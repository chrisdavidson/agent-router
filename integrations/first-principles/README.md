# agent-router × first-principles

A self-contained Claude Code plugin (`agent-router-fp`) that runs next to the
[first-principles](https://github.com/chrisdavidson/first-principles-skill) plugin and leaves
it untouched. It adds one checkpoint that plugin does not have:

1. **Delegation nudge.** When your prompt (or an `Agent` call the main session is about to
   make) looks like a first-principles question, the main session gets a short note: delegate
   it to `first-principles:first-principles`. Nothing else changes: the note is advisory, and
   a prompt that does not fit gets no note.

**Who does what.** agent-router only decides *whether* to hand a question to the agent.
Everything inside the analysis stays with first-principles: Step 0 technique selection, the
slash-only skills, the Self-Audit Gate, the `.first-principles/` output file. agent-router
never points at an individual technique.

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

Every checkpoint is logged to `<state dir>/audit/<session>.jsonl` (same format as the rest of
agent-router, plus `agent_type`).

## Files

| File | What |
|---|---|
| `catalog.yaml` | the one entry agent-router may point at, plus the `none` exemplars |
| `eval_set.yaml` | `cal` cases written for this integration; `test` holdout = first-principles' own routing catalog (13 P, 20 N) |
| `calibration.json` | local-classifier parameters fit on the `cal` split only |
| `plugin/` | the Claude Code plugin: hooks, `bin/hook` |
| `battery.py` | live A/B: first-principles' routing catalog with and without this plugin |

## Measuring it

- **Offline:** `agent-router eval --catalog catalog.yaml --cases eval_set.yaml` scores the catalog on the `test` holdout with the local
  classifier and `calibration.json`.
- **Live A/B:** `.venv/bin/python integrations/first-principles/battery.py` runs
  first-principles' routing catalog with and without this plugin, one fresh `claude -p`
  session per prompt, scored with first-principles' own `detect_routing`. It costs tokens; a
  delegated session is stopped at the delegation.
