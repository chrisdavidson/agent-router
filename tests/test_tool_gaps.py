"""The offline tool-gap report (integrations/first-principles/tool_gaps.py)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _gaps():
    spec = importlib.util.spec_from_file_location(
        "tool_gaps", ROOT / "integrations" / "first-principles" / "tool_gaps.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records) + '{"half written\n')


def _shell(session: str, tid: str, command: str, interpreter: bool = False) -> dict:
    return {
        "session": session,
        "agent_id": "a1",
        "kind": "shell",
        "command": command,
        "interpreter": interpreter,
        "tool_use_id": tid,
    }


def _tool_row(session: str, tid: str, reason: str, action: str = "skipped") -> dict:
    return {
        "session": session,
        "ts": f"t-{tid}",
        "point": "tool",
        "tool_name": "Bash",
        "tool_use_id": tid,
        "action": action,
        "reason": reason,
    }


SECRET = "python3 -c 'print(secret_rate * 12)'"


@pytest.fixture
def state(tmp_path: Path) -> Path:
    root = tmp_path / "state"
    for s in ("s1", "s2"):
        _write(
            root / "trace" / f"{s}.jsonl",
            [
                {"session": s, "agent_id": "a1", "kind": "run_start"},
                _shell(s, f"{s}-py", SECRET, interpreter=True),
                _shell(s, f"{s}-pdf", "curl -sL -o f.pdf https://www.osti.gov/x.pdf"),
                _shell(s, f"{s}-curl", "curl -s https://developer.nrel.gov/api/v8.json"),
                _shell(s, f"{s}-ls", "cd /private-workdir && ls -la"),
                {
                    "session": s,
                    "agent_id": "a1",
                    "kind": "source",
                    "tool": "WebFetch",
                    "host": "law.justia.com",
                    "target": "https://law.justia.com/x",
                    "outcome": "http_error",
                    "tool_use_id": f"{s}-fetch",
                },
                {
                    "session": s,
                    "agent_id": "a1",
                    "kind": "source",
                    "host": "www.irs.gov",
                    "outcome": "ok",
                    "tool_use_id": f"{s}-ok",
                },
                {"session": s, "agent_id": "a1", "kind": "calc", "tool_use_id": f"{s}-calc"},
            ],
        )
        _write(
            root / "audit" / f"{s}.jsonl",
            [
                {"session": s, "ts": "p", "point": "prompt", "action": "native", "reason": "x"},
                _tool_row(s, f"{s}-py", "does not fit: exact-calc, exact-calc-script"),
                _tool_row(s, f"{s}-pdf", "does not fit: exact-calc, exact-calc-script"),
                _tool_row(s, f"{s}-ls", "skip pattern"),
            ],
        )
    return root


def test_each_call_lands_in_one_pattern_joined_to_what_the_router_made_of_it(state: Path):
    result = _gaps().scan([state, state])  # the same state twice: each call counts once
    by = {p["id"]: p for p in result["patterns"]}
    assert (by["compute_script"]["calls"], by["compute_script"]["router"]) == (
        2,
        {"did not fit": 2},
    )
    assert by["document_to_text"]["hosts"] == 1  # www.osti.gov, counted not named
    assert by["web_via_shell"]["router"] == {"not checked": 2}
    assert by["source_without_content"]["hosts"] == 1
    assert by["inspect_files"]["router"] == {"skip pattern": 2}
    # an answered source and the catalog's calculator are not gaps
    assert sum(p["calls"] for p in result["patterns"]) == 10
    assert result["calculator_calls"] == 2
    assert (result["runs"], result["sessions"]) == (2, 2)  # a1 in s1 and a1 in s2
    assert result["checkpoints"]["tool / did not fit"] == 4


def test_a_candidate_recurs_across_sessions_and_is_not_housekeeping(state: Path):
    gaps = _gaps()
    by = {p["id"]: p for p in gaps.scan([state], min_calls=2, min_sessions=2)["patterns"]}
    assert by["compute_script"]["candidate"] and by["document_to_text"]["candidate"]
    assert not by["inspect_files"]["candidate"]  # recurs, but housekeeping
    by = {p["id"]: p for p in gaps.scan([state], min_calls=2, min_sessions=3)["patterns"]}
    assert not any(p["candidate"] for p in by.values())


def test_the_report_keeps_no_command_text(state: Path, tmp_path: Path, capsys):
    gaps = _gaps()
    out = tmp_path / "gaps.json"
    assert gaps.main(["--state", str(state), "--min-calls", "2", "--json", str(out)]) == 0
    text = capsys.readouterr().out
    saved = out.read_text()
    for kept in (text, saved):
        assert "secret_rate" not in kept and "private-workdir" not in kept and "f.pdf" not in kept
        assert "osti.gov" not in kept and "justia.com" not in kept and "nrel.gov" not in kept
    assert "### Multi-step compute scripts" in text
    assert json.loads(saved)["patterns"][0]["candidate"] is True


def test_a_host_cut_off_by_the_traces_truncation_is_dropped():
    gaps = _gaps()
    long = "curl -s " + "x" * 175 + " https://dos.pa.gov/forms"  # cut at 200: "...dos.pa.g"
    cut = long[: gaps.TRACE_COMMAND_CHARS]
    assert gaps._host_in(long) == "dos.pa.gov"
    assert cut.endswith("dos.pa.g") and gaps._host_in(cut) is None


def test_no_traces_is_an_error(tmp_path: Path, capsys):
    assert _gaps().main(["--state", str(tmp_path)]) == 1
    assert "no trace files" in capsys.readouterr().err
