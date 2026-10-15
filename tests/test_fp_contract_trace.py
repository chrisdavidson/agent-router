"""trace.py reads decisions from the summary block (CONTRACT-03..06, TRACE-04, HOOK-05)."""

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "fp"
INTEG = ROOT / "integrations" / "first-principles"
FP = "first-principles:first-principles"
VALID = FIX / "reports" / "valid"
NEG = FIX / "reports" / "negative"
FENCE = re.compile(r"```json\n(.*?)\n```", re.S)


def _load_trace():
    spec = importlib.util.spec_from_file_location("fp_trace_contract", INTEG / "trace.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


tr = _load_trace()


def _with_block(text: str, mutate) -> str:
    m = list(FENCE.finditer(text))[-1]
    data = json.loads(m.group(1))
    mutate(data)
    return text[: m.start(1)] + json.dumps(data, indent=2) + text[m.end(1) :]


def _current(data: dict) -> None:
    data["conclusion"].setdefault("rests_on", ["C1"])


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for var in ("AGENT_ROUTER_FP_SCHEMA", "FP_PLUGIN_ROOT", "AGENT_ROUTER_AUDIT"):
        monkeypatch.delenv(var, raising=False)


def _run(tmp_path: Path, report: str, *, stops: int = 1, agent: str = "a1") -> list[dict]:
    """Run an agent that wrote ``report`` to its cwd and stopped ``stops`` times."""
    work = tmp_path / "work"
    (work / ".first-principles").mkdir(parents=True, exist_ok=True)
    (work / ".first-principles" / "analysis-1.md").write_text(report, encoding="utf-8")
    state = tmp_path / "state"
    base = {"session_id": "s", "agent_type": FP, "cwd": str(work), "agent_id": agent}
    tr.handle({**base, "hook_event_name": "SubagentStart"}, state)
    for i in range(stops):
        tr.handle({**base, "hook_event_name": "SubagentStop", "stop_hook_active": i > 0}, state)
    lines = (state / "trace" / "s.jsonl").read_text(encoding="utf-8").splitlines()
    return [r for r in map(json.loads, lines) if r["kind"] == "run_end"]


def test_valid_block_supplies_the_decisions(tmp_path):
    text = (VALID / "example-product-business.md").read_text(encoding="utf-8")
    (end,) = _run(tmp_path, text)
    block = json.loads(FENCE.findall(text)[-1])
    d = end["decisions"]
    assert end["contract"]["contract_status"] == "valid"
    assert end["decisions_source"] == "block" and end["decisions_verified"] is True
    assert end["analysis_source"] == "file"  # where the TEXT came from: unchanged meaning
    assert "block" not in end["contract"] and end["contract"]["schema_source"] == "pinned"
    assert d["assumptions"]["count"] == len(block["assumptions"])
    assert [c["id"] for c in d["chains"]] == [c["id"] for c in block["chains"]]
    assert [c["confidence"] for c in d["chains"]] == [c["confidence"] for c in block["chains"]]
    assert d["chains"][0]["title"]  # prose still supplies titles
    assert d["conclusion"]["confidence"] == block["conclusion"]["confidence"]
    assert d["gate"] is not None and d["gate"]["passes_written"] == 0  # a null gate stays null
    assert d["gate"]["cleared"] is None and d["techniques_not_applied"] is None
    assert d["contradictions"] == []


def test_block_decisions_fill_every_field_report_and_demo_read(tmp_path):
    text = _with_block((VALID / "live-personal-general.md").read_text(encoding="utf-8"), _current)
    (end,) = _run(tmp_path, text)
    prose = tr.parse_analysis(text)
    d = end["decisions"]
    assert end["decisions_source"] == "block"
    assert set(prose) <= set(d)  # the shape the prose parse has, plus fields the block adds
    assert (
        d["gate"]["passes"] == 2
        and d["gate"]["fix_repeat"] is True
        and d["gate"]["cleared"] is True
    )
    assert d["gate"]["bands"] and len(d["gate"]["bands"]) == 6
    assert d["gate"]["criteria"] == prose["gate"]["criteria"]  # prose-only field
    assert d["ground_truths"]["unverified"] == prose["ground_truths"]["unverified"]
    assert d["re_entry"]["fired"] is True and d["re_entry"]["edges"]
    assert d["conclusion"]["rests_on"]
    assert d["contradictions"] == []  # block and prose agree on every compared field


@pytest.mark.parametrize("name", ["absent", "multiple", "misplaced", "invalid_json"])
def test_unusable_block_falls_back_to_prose(tmp_path, name):
    text = (NEG / f"{name}.md").read_text(encoding="utf-8")
    (end,) = _run(tmp_path, text)
    assert end["contract"]["contract_status"] == name
    assert end["decisions_source"] == "prose" and end["decisions_verified"] is None
    expected = tr.parse_analysis(text)
    expected["gate"]["passes_written"] = 0
    assert end["decisions"] == expected


def test_schema_violation_falls_back_to_prose(tmp_path):
    (end,) = _run(tmp_path, (VALID / "live-estimate-fermi.md").read_text(encoding="utf-8"))
    assert end["contract"]["contract_status"] == "schema_violation"
    assert end["decisions_source"] == "prose"
    assert any(v["path"] == "conclusion.rests_on" for v in end["contract"]["violations"])


def test_unsupported_version_still_surfaces_decisions_unverified(tmp_path):
    (end,) = _run(tmp_path, (NEG / "unsupported_version.md").read_text(encoding="utf-8"))
    assert end["contract"]["contract_status"] == "unsupported_version"
    assert end["contract"]["schema_version"] == 2
    assert end["decisions_source"] == "block" and end["decisions_verified"] is False
    assert end["decisions"]["chains"] and end["decisions"]["assumptions"]["count"] > 0


def test_a_block_with_a_strange_shape_does_not_crash_the_trace(tmp_path):
    text = _with_block(
        (NEG / "unsupported_version.md").read_text(encoding="utf-8"),
        lambda d: d.update(chains=7, assumptions={"x": 1}, gate=[], conclusion="no"),
    )
    (end,) = _run(tmp_path, text)
    assert end["decisions_source"] == "block" and end["decisions_verified"] is False
    assert end["decisions"]["chains"] == [] and end["decisions"]["assumptions"]["count"] == 0


# -- block vs prose ------------------------------------------------------------------------------


def test_block_wins_and_the_disagreement_is_recorded(tmp_path):
    def mutate(d):
        d["conclusion"]["confidence"] = "HIGH"  # the report's section 6 says MEDIUM
        d["chains"][1]["confidence"] = "LOW"
        d["gate"]["cleared"] = False
        d["assumptions"][0]["verdict"] = "Accept"  # it was Discard

    text = _with_block(
        (VALID / "live-personal-general.md").read_text(encoding="utf-8"),
        lambda d: (_current(d), mutate(d)),
    )
    (end,) = _run(tmp_path, text)
    d = end["decisions"]
    assert end["decisions_source"] == "block"
    assert d["conclusion"]["confidence"] == "HIGH"  # the block's value
    versus = [c for c in d["contradictions"] if c.startswith("block vs prose: ")]
    fields = {c.split(": ")[1] for c in versus}
    assert fields == {
        "conclusion.confidence",
        "chains.confidence",
        "gate.cleared",
        "assumptions.by_verdict",
    }
    one = next(c for c in versus if ": conclusion.confidence:" in c)
    assert one == "block vs prose: conclusion.confidence: block=HIGH prose=MEDIUM"


def test_a_missing_prose_field_is_not_a_disagreement():
    prose = tr.parse_analysis("## 1. Problem Essence\n\nhalf written")
    text = _with_block((VALID / "live-personal-general.md").read_text(encoding="utf-8"), _current)
    block = json.loads(FENCE.findall(text)[-1])
    assert tr.block_vs_prose(tr.decisions_from_block(block, prose), prose) == []


def test_unverified_ground_truth_and_reentry_disagreements():
    text = (VALID / "live-software-systems.md").read_text(encoding="utf-8")
    block = json.loads(FENCE.findall(text)[-1])
    block["ground_truths"][0]["read_at_source"] = not block["ground_truths"][0]["read_at_source"]
    block["re_entry"] = {"fired": False, "edges": []}
    prose = tr.parse_analysis(text)
    versus = tr.block_vs_prose(tr.decisions_from_block(block, prose), prose)
    assert {c.split(": ")[1] for c in versus} == {"ground_truths.unverified", "re_entry.fired"}


# -- schema location and an absent reader ---------------------------------------------------------


def test_schema_location_order(tmp_path, monkeypatch):
    assert tr.schema_location() == (tr.PINNED_SCHEMA, "pinned")
    assert tr.PINNED_SCHEMA.read_bytes() == (FIX / "schema" / "summary-schema.json").read_bytes()
    root = tmp_path / "plugin"
    (root / "references").mkdir(parents=True)
    monkeypatch.setenv("FP_PLUGIN_ROOT", str(root))
    assert tr.schema_location()[1] == "pinned"  # no file there: the pinned copy
    (root / "references" / "summary-schema.json").write_text("{}")
    assert tr.schema_location() == (root / "references" / "summary-schema.json", "plugin_root")
    monkeypatch.setenv("AGENT_ROUTER_FP_SCHEMA", str(tmp_path / "x.json"))
    assert tr.schema_location() == (tmp_path / "x.json", "env")


def test_a_missing_or_broken_schema_degrades_to_prose(tmp_path, monkeypatch):
    text = (VALID / "example-product-business.md").read_text(encoding="utf-8")
    monkeypatch.setenv("AGENT_ROUTER_FP_SCHEMA", str(tmp_path / "gone.json"))
    (end,) = _run(tmp_path, text)
    assert end["contract"]["contract_status"] == "schema_unavailable"
    assert end["contract"]["schema_source"] == "env" and end["decisions_source"] == "prose"
    bad = tmp_path / "bad.json"
    schema = json.loads(tr.PINNED_SCHEMA.read_text(encoding="utf-8"))
    schema["fields"]["run_mode"]["format"] = "x"
    bad.write_text(json.dumps(schema))
    monkeypatch.setenv("AGENT_ROUTER_FP_SCHEMA", str(bad))
    (end,) = _run(tmp_path / "two", text)
    assert (
        end["contract"]["contract_status"] == "schema_error" and end["decisions_source"] == "prose"
    )


def test_without_the_contract_package_the_trace_still_works(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "contracts", None)
    (end,) = _run(tmp_path, (VALID / "example-product-business.md").read_text(encoding="utf-8"))
    assert end["contract"] is None and end["decisions_source"] == "prose"
    assert end["decisions"]["assumptions"]["count"] > 0
    assert tr.contract_coverage([end]) == (
        "contract: valid 0/1 · prose fallback 1 · unsupported 0 · other 0"
    )


def test_no_report_text_records_nothing_to_derive(tmp_path):
    state = tmp_path / "state"
    base = {"session_id": "s", "agent_type": FP, "cwd": str(tmp_path), "agent_id": "a"}
    tr.handle({**base, "hook_event_name": "SubagentStart"}, state)
    end = tr.handle({**base, "hook_event_name": "SubagentStop"}, state)
    assert end["decisions"] is None and end["contract"] is None
    assert end["decisions_source"] is None and end["stop_attempt"] == 1


def test_the_standalone_script_imports_the_reader_from_a_checkout(tmp_path):
    """bin/trace runs the file by path with the venv python: the reader comes from ../../src."""
    import subprocess

    code = (
        "import sys, importlib.util;"
        "sys.path[:] = [p for p in sys.path if 'agent-router' not in p and 'src' not in p];"
        f"s = importlib.util.spec_from_file_location('t', {str(INTEG / 'trace.py')!r});"
        "m = importlib.util.module_from_spec(s); s.loader.exec_module(m);"
        "print(m.contracts is not None)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=tmp_path)
    assert out.stdout.strip() == "True", out.stderr


# -- several stops per run (HOOK-05) and the report -----------------------------------------------


def _guard_events(state: Path) -> None:
    events = json.loads((FIX / "captures" / "guard-blocked-payloads.json").read_text())
    for ev in events:
        tr.handle(ev["payload"], state, now=ev["ts"])


def test_every_stop_is_numbered_and_the_last_one_is_the_run(tmp_path):
    state = tmp_path / "state"
    _guard_events(state)
    recs = [
        json.loads(x) for f in (state / "trace").glob("*.jsonl") for x in f.read_text().splitlines()
    ]
    ends = [r for r in recs if r["kind"] == "run_end"]
    assert [(r["stop_attempt"], r["stop_hook_active"]) for r in ends] == [
        (1, False),
        (2, True),
        (3, True),
    ]
    assert tr.last_run_ends(recs) == [ends[-1]]
    other = {**ends[0], "agent_id": "b", "stop_attempt": 1}
    both = tr.last_run_ends([ends[0], other, ends[1], ends[2]])
    assert [(r["agent_id"], r["stop_attempt"]) for r in both] == [("b", 1), ("agent-guard-1", 3)]


def test_report_has_one_row_per_agent_with_its_stop_count(tmp_path):
    _guard_events(tmp_path)
    out = tr.report(tmp_path / "trace").splitlines()
    rows = [r for r in out[2:] if r.startswith("|")]
    assert len(rows) == 1
    head = [c.strip() for c in out[0].strip("|").split("|")]
    cells = [c.strip() for c in rows[0].strip("|").split("|")]
    assert len(cells) == len(head)
    assert cells[head.index("stops")] == "3"
    assert cells[head.index("contract")] == "absent"
    assert cells[head.index("decisions from")] == "prose"
    assert out[-1] == "contract: valid 0/1 · prose fallback 1 · unsupported 0 · other 0"


def _end(agent, status, source, **kw):
    contract = (
        None if status is None else {"contract_status": status, "violations": kw.get("v", [])}
    )
    return {
        "kind": "run_end",
        "agent_id": agent,
        "session": "s",
        "contract": contract,
        "decisions_source": source,
    }


def test_coverage_line_counts_each_run_once(tmp_path):
    ends = [
        _end("a", "valid", "block"),
        _end("b", "valid", "block", v=[{"code": "internal-dangling-rests-on"}]),
        _end("c", "unsupported_version", "block"),
        _end("d", "absent", "prose"),
        _end("e", "schema_violation", "prose"),
        _end("f", None, None),
    ]
    assert tr.contract_coverage(ends) == (
        "contract: valid 2/6 · prose fallback 2 · unsupported 1 · other 1 · inconsistent 1"
    )
    assert (
        tr.contract_coverage([])
        == "contract: valid 0/0 · prose fallback 0 · unsupported 0 · other 0"
    )
    # through the report: a repeated stop does not count twice
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    rows = [_end("a", "absent", "prose"), _end("a", "valid", "block"), _end("b", "absent", "prose")]
    (trace_dir / "s.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert tr.report(trace_dir).splitlines()[-1] == (
        "contract: valid 1/2 · prose fallback 1 · unsupported 0 · other 0"
    )


def test_report_marks_block_prose_disagreement_apart_from_disclosure_contradictions(tmp_path):
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    end = _end("a", "valid", "block")
    end["decisions"] = {
        "contradictions": ["block vs prose: conclusion.confidence: block=HIGH prose=MEDIUM"]
    }
    (trace_dir / "s.jsonl").write_text(json.dumps(end) + "\n")
    row = tr.report(trace_dir).splitlines()[2]
    assert "(block differs from prose)" in row and "contradicts disclosure" not in row
