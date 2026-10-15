# Golden changes in Phase 3 (integration manifest, router side)

Regenerated with `UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_fp_characterisation.py`. The diff
against the Phase 2 goldens adds 32 lines and removes none: every change is one added key.
`decisions`, `contract`, `routing` and every other existing key are byte-identical.

## Changed

### `capture-estimate-fermi.json` (one `run_end` record) and `capture-guard-blocked-payloads.json` (three)

| key | value | why |
|---|---|---|
| `integration` | `{"manifest_version": 1, "plugin_root": null, "source": "fallback", "warnings": ["no plugin root found: using the pinned fallback"]}` | MANIFEST-02: how the manifest was resolved is recorded on each `run_end` |

The value is the same on every record because the characterisation run is hermetic:
`tests/conftest.py` points `AGENT_ROUTER_PLUGIN_CACHE` at a directory that does not exist, and
`FP_PLUGIN_ROOT` is unset, so resolution ends at the pinned fallback. On a developer machine
without that override the field would carry the cached plugin root, which is why the tests set it.

## Not changed

- The six `parse_analysis` goldens and the eleven `derive_decisions` goldens: they do not go
  through the identity code.
- No other record kind (`run_start`, `calc`, `shell`, `delegation`, ...) gained or lost a key.
