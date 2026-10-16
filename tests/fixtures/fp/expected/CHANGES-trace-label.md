# Golden changes: the delegation record keeps the hand-off's description

`trace.py` now copies the main session's `Agent` call `description` (its few-word name for
the task, at most 120 characters) into the `delegation` record, so the demo's Trace tab can
label a session by what was asked. The field is absent when the call carries none.

| Golden | What changed | Why |
|---|---|---|
| `capture-estimate-fermi.json` | the `delegation` record gains `"description": "First-principles TES cost estimate"` | the replayed capture's `Agent` call carries that description |

No other field of any golden changed, and all other goldens are unchanged.
