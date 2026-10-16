"""The conductor's structured tools: route, verify_summary, doctor. Read-only, errors as
ValueError (a tool error over MCP), never a crash. Fixtures are the contract fixtures."""

import asyncio
import json
import re
import shutil
from pathlib import Path

import pytest

from agent_router import integration_tools as it
from agent_router.adapters import mcp_stdio

ROOT = Path(__file__).resolve().parents[1]
INTEG = ROOT / "integrations" / "first-principles"
REPORTS = ROOT / "tests" / "fixtures" / "fp" / "reports"
FP = "first-principles:first-principles"


@pytest.fixture(autouse=True)
def _integration(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_ROUTER_INTEGRATION", str(INTEG))
    monkeypatch.setenv("AGENT_ROUTER_EMBEDDER", "hashing")  # offline: no model weights
    monkeypatch.setenv("AGENT_ROUTER_PLUGIN_CACHE", "")  # the pinned fallback manifest
    monkeypatch.setenv("AGENT_ROUTER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("FP_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("AGENT_ROUTER_AUDIT", raising=False)
    monkeypatch.delenv("AGENT_ROUTER_SKIP_INPUT", raising=False)
    monkeypatch.delenv("AGENT_ROUTER_SKIP_PROMPT", raising=False)
    monkeypatch.delenv("AGENT_ROUTER_CATALOG", raising=False)


FENCE = re.compile(r"```json\n(.*?)\n```", re.S)


def _copy(tmp_path, name):
    """A fixture report in the working directory. The live fixtures predate
    ``conclusion.rests_on``; it is added so they are valid under the current schema."""
    src = next(REPORTS.rglob(name))
    dest = tmp_path / ".first-principles" / name
    dest.parent.mkdir(exist_ok=True)
    shutil.copy(src, dest)
    if name.startswith("live-"):
        text = dest.read_text(encoding="utf-8")
        m = list(FENCE.finditer(text))[-1]
        data = json.loads(m.group(1))
        data["conclusion"].setdefault("rests_on", [c["id"] for c in data["chains"][-2:]])
        dest.write_text(
            text[: m.start(1)] + json.dumps(data, indent=2) + text[m.end(1) :], encoding="utf-8"
        )
    return dest


# --- verify_summary ----------------------------------------------------------------------------


def test_verify_summary_on_a_valid_report(tmp_path):
    _copy(tmp_path, "live-estimate-fermi.md")
    out = it.verify_summary(".first-principles/live-estimate-fermi.md", root=tmp_path)
    assert out["contract_status"] == "valid" and out["violations"] == []
    assert out["decisions_verified"] is True
    assert out["schema"]["source"] in {"pinned", "plugin_root", "env"}
    assert out["schema"]["block_version"] == 1 and out["schema"]["accepted_versions"] == [1]
    d = out["decisions"]
    assert set(d) == {
        "run_mode",
        "conclusion",
        "gate_cleared",
        "fix_repeat",
        "unverified_ground_truths",
        "assumptions",
    }
    assert d["assumptions"]["count"] == sum(d["assumptions"]["by_verdict"].values()) > 0
    assert d["conclusion"]["recommended"] and d["conclusion"]["confidence"] in {
        "HIGH",
        "MEDIUM",
        "LOW",
    }
    assert isinstance(d["gate_cleared"], bool)
    json.dumps(out)  # JSON-serialisable as is


def test_verify_summary_reads_the_decisions_from_the_block_not_the_prose(tmp_path):
    path = _copy(tmp_path, "live-estimate-fermi.md")
    text = path.read_text(encoding="utf-8")
    block = json.loads(text[text.rindex("```json") + 7 : text.rindex("```")])
    out = it.verify_summary(str(path.relative_to(tmp_path)), root=tmp_path)
    d = out["decisions"]
    assert d["conclusion"]["confidence"] == block["conclusion"]["confidence"]
    assert d["gate_cleared"] == block["gate"]["cleared"]
    assert d["unverified_ground_truths"] == [
        f"{g['id']}?" for g in block["ground_truths"] if g["read_at_source"] is False
    ]
    assert d["assumptions"]["count"] == len(block["assumptions"])


def test_verify_summary_extracts_the_answer_section(tmp_path):
    _copy(tmp_path, "live-estimate-fermi.md")
    out = it.verify_summary(".first-principles/live-estimate-fermi.md", root=tmp_path)
    excerpt = out["answer_excerpt"]
    assert excerpt.startswith("**Recommendation:**") and len(excerpt) <= it.ANSWER_CHARS
    assert "## " not in excerpt


def test_answer_excerpt_is_capped():
    assert len(it.answer_excerpt("## Answer\n" + "word " * 1000 + "\n## 1. X")) == it.ANSWER_CHARS


def test_answer_excerpt_ends_at_the_next_section_and_is_none_without_one():
    assert it.answer_excerpt("## Answer\nyes\n\n## 1. X\nno") == "yes"
    assert it.answer_excerpt("## Answered later\nx") is None
    assert it.answer_excerpt("# t\n## 1. X\nno") is None
    assert it.answer_excerpt("## Answer\n\n## 1. X") is None


@pytest.mark.parametrize(
    ("name", "status"),
    [
        ("multiple.md", "multiple"),
        ("misplaced.md", "misplaced"),
        ("invalid_json.md", "invalid_json"),
        ("unsupported_version.md", "unsupported_version"),
        ("schema_violation.md", "schema_violation"),
    ],
)
def test_verify_summary_reports_each_contract_status(tmp_path, name, status):
    _copy(tmp_path, name)
    out = it.verify_summary(f".first-principles/{name}", root=tmp_path)
    assert out["contract_status"] == status
    assert out["violations"]  # a bad block says why
    assert out["decisions_verified"] is (status == "valid")
    if status in {"multiple", "misplaced", "invalid_json"}:
        assert out["decisions"] is None  # nothing is guessed


def test_verify_summary_surfaces_an_unsupported_version_as_unverified(tmp_path):
    _copy(tmp_path, "unsupported_version.md")
    out = it.verify_summary(".first-principles/unsupported_version.md", root=tmp_path)
    assert out["decisions"] is not None and out["decisions_verified"] is False


def test_verify_summary_plain_text_has_no_block(tmp_path):
    (tmp_path / "r.md").write_text("# a report\n\nno block here\n")
    out = it.verify_summary("r.md", root=tmp_path)
    assert out["contract_status"] == "absent" and out["decisions"] is None


@pytest.mark.parametrize("path", ["../outside.md", "/etc/passwd", "missing.md", "."])
def test_verify_summary_confines_and_reports_bad_paths(tmp_path, path):
    with pytest.raises(ValueError):
        it.verify_summary(path, root=tmp_path)


def test_verify_summary_rejects_a_symlink_out_of_the_root(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "r.md").write_text("x")
    root = tmp_path / "root"
    root.mkdir()
    (root / "link.md").symlink_to(outside / "r.md")
    with pytest.raises(ValueError, match="outside"):
        it.verify_summary("link.md", root=root)


def test_verify_summary_without_an_integration_is_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_ROUTER_INTEGRATION")
    (tmp_path / "r.md").write_text("x")
    with pytest.raises(ValueError, match="no integration"):
        it.verify_summary("r.md", root=tmp_path)


# --- route -------------------------------------------------------------------------------------

DECISION_FIELDS = {
    "action",
    "choice",
    "entry_id",
    "probabilities",
    "confidence",
    "reason",
    "hint",
    "options",
    "backend",
    "latency_ms",
    "stages",
    "threshold",
    "applied_threshold",
}
SCRIPT = {"command": "python3 - <<'EOF'\nimport math\nx = 3\nprint(math.log(x))\nEOF"}


def test_route_returns_the_cli_decision_fields_and_writes_no_audit(tmp_path):
    out = it.route("Work out from fundamentals whether we need a sales team")
    assert set(out) == DECISION_FIELDS
    assert out["backend"] == "local" and "first-principles-agent" in out["options"]
    json.dumps(out)
    assert not (tmp_path / "state" / "audit").exists()


def test_route_tool_step_offers_only_the_entry_whose_fit_check_passes():
    for tool_input, offered in (
        (SCRIPT, ["exact-calc-script", "none"]),
        ({"command": 'python3 -c "print(0.17 * 2340)"'}, ["exact-calc", "none"]),
        ({"command": "python3 - <<'EOF'\nfor i in range(3): print(i)\nEOF"}, []),
    ):
        for given in (tool_input, json.dumps(tool_input)):  # parsed or JSON text
            out = it.route("", "tool", "Bash", given, FP)
            assert out["options"] == offered


def test_route_tool_step_on_the_main_thread_has_no_calculator():
    assert it.route("", "tool", "Bash", SCRIPT)["options"] == []


def test_route_never_denies(monkeypatch):
    monkeypatch.setenv("AGENT_ROUTER_MODE", "enforce")
    out = it.route("", "tool", "Bash", SCRIPT, FP)
    assert out["action"] != "deny"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"text": "x", "point": "nope"}, "unknown point"),
        ({"text": "x", "point": "tool", "tool_input_json": "{not json"}, "not valid JSON"),
        ({"text": "x", "point": "tool", "tool_input_json": "[1]"}, "JSON object"),
        ({"text": 5}, "text must be a string"),
    ],
)
def test_route_bad_requests_are_value_errors(kwargs, message):
    with pytest.raises(ValueError, match=message):
        it.route(**kwargs)


def test_route_without_an_integration_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("AGENT_ROUTER_INTEGRATION")
    with pytest.raises(ValueError, match="no integration"):
        it.route("x")


# --- doctor ------------------------------------------------------------------------------------


def test_doctor_report_wraps_the_checks(monkeypatch):
    from agent_router import doctor

    fake = [doctor.Check("a", doctor.PASS, "fine"), doctor.Check("b", doctor.FAIL, "broken")]
    monkeypatch.setattr(doctor, "run_checks", lambda directory, **kw: fake)
    out = it.doctor_report()
    assert out == {
        "ok": False,
        "checks": [
            {"name": "a", "status": "PASS", "detail": "fine"},
            {"name": "b", "status": "FAIL", "detail": "broken"},
        ],
    }
    monkeypatch.setattr(doctor, "run_checks", lambda directory, **kw: fake[:1])
    assert it.doctor_report()["ok"] is True


# --- over MCP ----------------------------------------------------------------------------------


def _call(server, name, args):
    res = asyncio.run(server.call_tool(name, args))
    content = res.content if hasattr(res, "content") else res[0]
    return content[0].text


def test_the_tools_answer_json_over_mcp_and_errors_become_tool_errors(tmp_path):
    _copy(tmp_path, "live-estimate-fermi.md")
    server = mcp_stdio.build_server(tmp_path, ["route", "verify_summary", "doctor"])
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert set(tools) == {"route", "verify_summary", "doctor"}
    assert set(tools["route"].input_schema["properties"]) == {
        "text",
        "point",
        "tool",
        "tool_input_json",
        "agent_type",
        "question",
    }
    # either `text` or `question` names the step, so neither is schema-required; the tool
    # itself rejects a call with neither (test_mcp_route_accepts_question_as_another_name_for_text)
    assert "required" not in tools["route"].input_schema
    assert tools["verify_summary"].input_schema["required"] == ["path"]

    res = _call(server, "verify_summary", {"path": ".first-principles/live-estimate-fermi.md"})
    assert json.loads(res)["contract_status"] == "valid"
    # the host may hand tool_input_json over parsed; the tool takes either form
    res = _call(
        server,
        "route",
        {"text": "", "point": "tool", "tool": "Bash", "agent_type": FP, "tool_input_json": SCRIPT},
    )
    assert json.loads(res)["options"] == ["exact-calc-script", "none"]

    for name, args, message in (
        ("verify_summary", {"path": "../etc/passwd"}, "outside the workspace"),
        ("verify_summary", {"path": "nope.md"}, "file not found"),
        ("route", {"text": "x", "point": "bogus"}, "unknown point"),
    ):
        with pytest.raises(Exception) as err:
            _call(server, name, args)
        assert message in str(err.value) and type(err.value).__name__ == "ToolError"


def test_an_unexpected_failure_inside_a_tool_is_still_a_tool_error(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(it, "doctor_report", boom)
    server = mcp_stdio.build_server(tmp_path, ["doctor"])
    with pytest.raises(Exception) as err:
        _call(server, "doctor", {})
    assert "kaboom" in str(err.value) and type(err.value).__name__ == "ToolError"
