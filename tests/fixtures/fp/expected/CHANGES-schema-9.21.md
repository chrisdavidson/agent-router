# Golden changes: the router follows first-principles 9.21's schema fix

The trace's pinned schema moved from the 9.20.0 copy to the 9.21 copy, in which
`conclusion.rests_on` is `"optional": true`. The validator learned the keyword
(`optional` needs `nullable: true` and is refused on top-level fields, mirroring the
publisher's checker).

| Golden | What changed | Why |
|---|---|---|
| `derive-valid-live-estimate-fermi.json` | `contract_status` `schema_violation` -> `valid`; `decisions_source` `prose` -> `block`; `decisions_verified` null -> true; `decisions` now built from the block | the only violation was the missing `conclusion.rests_on` key, now optional |
| `derive-valid-live-personal-general.json` | same | same |
| `derive-valid-live-software-systems.json` | same | same |
| `derive-negative-dangling_rests_on.json` | same; its one internal violation (`chains[0].rests_on[3]`, `internal-dangling-rests-on`) is still listed | it was derived from `live-estimate-fermi.md`, and internal violations never change a readable block's status (Phase 2 rule) |
| `negative-schema_violation.json`, `derive-negative-schema_violation.json` | new | the new fixture for a block that violates the schema |

No block-vs-prose contradictions appear in any of the four changed goldens. All other goldens
are unchanged.
