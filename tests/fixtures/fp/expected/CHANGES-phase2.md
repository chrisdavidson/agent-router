# Golden changes in Phase 2 (contract reader)

Regenerated with `UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_fp_characterisation.py` after the
code was finished. The diff against the Phase 1 goldens (6d5777a) removes no line: every change
is an added key. Nothing under `decisions` changed in any existing golden.

## Changed

### `capture-estimate-fermi.json` (one `run_end` record)

Added keys, all on the `run_end` record:

| key | value | why (requirement) |
|---|---|---|
| `contract` | `contract_status: misplaced`, violation "a section follows the block", `schema_source: pinned`, `schema_path` shown as `<repo>/...` | CONTRACT-01. The run appended `## Answer` after the block, so the block is not the last section. Real data, see "Findings" |
| `decisions_source` | `prose` | the status is not `valid`/`unsupported_version`, so the prose fallback is used (D-06, CONTRACT-04) |
| `decisions_verified` | `null` | only a block-built decision set is verified or not |
| `stop_attempt` | `1` | HOOK-05 |
| `stop_hook_active` | `false` | HOOK-05 (the replayed payload carries none) |

`analysis_source` is unchanged (`appends`): it still says where the text came from.
The `decisions` object is byte-identical to the Phase 1 golden.

### `capture-guard-blocked-payloads.json` (three `run_end` records)

Same five keys on each of the three records. Values:

| record | `stop_attempt` | `stop_hook_active` | `contract_status` | `decisions_source` |
|---|---|---|---|---|
| 1st stop | 1 | false | `absent` | `prose` |
| 2nd stop | 2 | true | `absent` | `prose` |
| 3rd stop | 3 | true | `absent` | `prose` |

(HOOK-05, CONTRACT-01.) The hand-built report has no block. Three records remain on disk, one per
stop; consumers (`--report`, the demo) read the last per `agent_id`.

## Unchanged (11)

`parse_analysis` is untouched, so its goldens are byte-identical: `negative-absent`,
`negative-dangling_rests_on`, `negative-invalid_json`, `negative-misplaced`, `negative-multiple`,
`negative-unsupported_version`, `valid-example-product-business`,
`valid-example-theoretical-limit-carnot`, `valid-live-estimate-fermi`, `valid-live-personal-general`,
`valid-live-software-systems`.

## Added (11): `derive-<group>-<name>.json`

New test `test_derive_decisions_golden` freezes `derive_decisions(text)`: contract status,
`decisions_source`, `decisions_verified` and `decisions`.

| golden | `contract_status` | `decisions_source` | why |
|---|---|---|---|
| `derive-negative-absent` | `absent` | `prose` | CONTRACT-01 |
| `derive-negative-multiple` | `multiple` | `prose` | CONTRACT-01 |
| `derive-negative-misplaced` | `misplaced` | `prose` | CONTRACT-01 |
| `derive-negative-invalid_json` | `invalid_json` | `prose` | CONTRACT-01 |
| `derive-negative-unsupported_version` | `unsupported_version` | `block` (`decisions_verified: false`) | CONTRACT-03 |
| `derive-negative-dangling_rests_on` | `schema_violation` | `prose` | the source report predates `conclusion.rests_on`; the dangling id is also listed (CONTRACT-05), see "Findings" |
| `derive-valid-example-product-business` | `valid` | `block` (`decisions_verified: true`) | CONTRACT-04 |
| `derive-valid-example-theoretical-limit-carnot` | `valid` | `block` | CONTRACT-04 |
| `derive-valid-live-estimate-fermi` | `schema_violation` | `prose` | missing `conclusion.rests_on` |
| `derive-valid-live-personal-general` | `schema_violation` | `prose` | missing `conclusion.rests_on` |
| `derive-valid-live-software-systems` | `schema_violation` | `prose` | missing `conclusion.rests_on` |

No block-vs-prose contradiction appears in any golden: on the two block-read examples the block
and the prose agree on every compared field. The disagreement path is covered by
`tests/test_fp_contract_trace.py`, which builds variants.

## Findings (real data that disagrees with the current schema)

* The three live reports (and so `dangling_rests_on`, derived from one) lack the required
  `conclusion.rests_on`. first-principles' own `check-summary-block.py` rejects them the same
  way. The field was added as required without a `schema_version` bump, so they cannot read
  as `valid`. Updated with the field they read as `valid` (tested).
* The estimate-fermi capture ends with `## Answer` after the block: a run of an older
  first-principles whose document order put the answer last. Under the current contract it is
  `misplaced`.
