"""Characterisation (golden) tests for integrations/first-principles/trace.py.

They freeze what the trace derives from the committed fixtures in tests/fixtures/fp today,
including wrong answers on the synthetic negatives, so every later change in trace output is a
visible, intentional diff.  Regenerate the goldens with ``UPDATE_GOLDEN=1 pytest <this file>``
and review the diff before committing; a plain run never writes.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "fp"
EXPECTED = FIX / "expected"
UPDATE = bool(os.environ.get("UPDATE_GOLDEN"))


def _load_trace():
    spec = importlib.util.spec_from_file_location(
        "fp_trace_char", ROOT / "integrations" / "first-principles" / "trace.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


trace = _load_trace()


def _dump(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _check(name: str, actual) -> None:
    path = EXPECTED / f"{name}.json"
    text = _dump(actual)
    if UPDATE:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return
    assert path.is_file(), f"missing golden {path.name}; run with UPDATE_GOLDEN=1"
    assert text == path.read_text(encoding="utf-8"), f"{path.name} differs from current output"


def _reports():
    return sorted(p for sub in ("valid", "negative") for p in (FIX / "reports" / sub).glob("*.md"))


@pytest.mark.parametrize("path", _reports(), ids=lambda p: f"{p.parent.name}-{p.stem}")
def test_parse_analysis_golden(path):
    out = trace.parse_analysis(path.read_text(encoding="utf-8"))
    _check(f"{path.parent.name}-{path.stem}", out)


def _normalise(records: list[dict], state: Path) -> list[dict]:
    """Drop what varies between machines: the temp state dir; the report text, kept as a length
    (its sha256 stays in the record)."""
    text = json.dumps(records, sort_keys=True).replace(str(state), "<state>")
    out = json.loads(text)
    for rec in out:
        if rec.get("analysis_text") is not None:
            rec["analysis_text"] = f"<{len(rec['analysis_text'])} chars>"
    return out


def _trace_records(state: Path) -> list[dict]:
    recs = []
    for f in sorted((state / "trace").glob("*.jsonl")):
        recs += [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()]
    return recs


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ROUTER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("AGENT_ROUTER_AUDIT", raising=False)
    return tmp_path / "state"


def test_replay_estimate_fermi_golden(state):
    for payload, ts in trace.replay_payloads(FIX / "captures" / "estimate-fermi.jsonl"):
        trace.handle(payload, state, now=ts)
    recs = _trace_records(state)
    ends = [r for r in recs if r["kind"] == "run_end"]
    assert len(ends) == 1 and ends[0]["decisions"] is not None  # a finished run with decisions
    _check("capture-estimate-fermi", _normalise(recs, state))


def test_replay_guard_blocked_payloads_golden(state):
    """Hand-built hook payloads: a guard that blocks the stop twice, so the agent stops three
    times.  Today each SubagentStop writes its own run_end (HOOK-05 will change that)."""
    events = json.loads((FIX / "captures" / "guard-blocked-payloads.json").read_text())
    for ev in events:
        trace.handle(ev["payload"], state, now=ev["ts"])
    recs = _trace_records(state)
    assert [r["kind"] for r in recs].count("run_end") >= 1
    _check("capture-guard-blocked-payloads", _normalise(recs, state))


def test_fixture_report_dirs_not_empty():
    assert len(list((FIX / "reports" / "valid").glob("*.md"))) == 5
    assert {p.stem for p in (FIX / "reports" / "negative").glob("*.md")} == {
        "absent",
        "multiple",
        "misplaced",
        "invalid_json",
        "unsupported_version",
        "dangling_rests_on",
    }
