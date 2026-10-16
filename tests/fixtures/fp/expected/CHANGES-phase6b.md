# Golden changes in Phase 6b (conductor skill)

Regenerated with `UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_fp_characterisation.py`. The diff
adds two lines and removes none: one added key on one record kind.

## Changed

### `capture-estimate-fermi.json` and `capture-guard-blocked-payloads.json` (one `delegation` record each)

| key | value | why |
|---|---|---|
| `launched_by` | `null` | CONDUCT-05: a `delegation` record says whether the conductor composed the prompt (`"conductor"`, with `composed_sha256`) or not. These captures predate the conductor, so no hand-off record exists for their prompts |

## Not changed

- Every other key and record kind, including `run_end`, `decisions`, `contract` and `routing`.
- The `parse_analysis` and `derive_decisions` goldens: they do not touch delegation records.
