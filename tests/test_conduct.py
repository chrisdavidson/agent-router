"""The conductor: ``conduct.py`` sub-commands and the ``analyze`` skill (CONDUCT-01..06).

Offline: the router's decider is stubbed or the local hashing embedder is used, no ``claude``
session runs. The skill is Markdown, so it may carry the plugin's tool names as literals; a test
holds them equal to the names derived from the descriptor and ``plugin.json``.
"""

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from agent_router.contracts import integration as integ_mod

ROOT = Path(__file__).resolve().parents[1]
INTEG = ROOT / "integrations" / "first-principles"
PLUGIN = INTEG / "plugin"
SKILL = PLUGIN / "skills" / "analyze" / "SKILL.md"
REPORTS = ROOT / "tests" / "fixtures" / "fp" / "reports"
FALLBACK = json.loads((INTEG / "manifest.fallback.json").read_text())
NAME, AGENT = FALLBACK["plugin_name"], FALLBACK["agent_type"]
QUESTION = "Is a four-day school week a good idea, or do we just assume five days?"


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, INTEG / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


conduct = _load("fp_conduct", "conduct.py")


CLEAN_CHECKS = {
    "health": {"ran": True, "ok": True, "flagged": []},
    "preflight": {"ran": True, "delegate": True, "score": 0.98, "threshold": 0.6},
}


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setattr(conduct, "run_checks", lambda question: CLEAN_CHECKS)
    monkeypatch.setenv("AGENT_ROUTER_INTEGRATION", str(INTEG))
    monkeypatch.setenv("AGENT_ROUTER_EMBEDDER", "hashing")
    monkeypatch.setenv("AGENT_ROUTER_PLUGIN_CACHE", "")  # the pinned fallback manifest
    monkeypatch.setenv("AGENT_ROUTER_STATE_DIR", str(tmp_path / "state"))
    for var in ("FP_PLUGIN_ROOT", "AGENT_ROUTER_AUDIT", "AGENT_ROUTER_CATALOG"):
        monkeypatch.delenv(var, raising=False)


def _integ():
    return integ_mod.load_integration(INTEG)


def _state(tmp_path):
    return tmp_path / "state"


def _run(capsys, *argv):
    code = conduct.main(list(argv))
    out = capsys.readouterr().out
    return code, json.loads(out)


# --- preflight (stubbed decider) -----------------------------------------------------------------


def _stub_route(monkeypatch, **fields):
    base = {
        "action": "native",
        "entry_id": None,
        "probabilities": {},
        "reason": "decider chose none",
        "threshold": 0.5,
        "applied_threshold": None,
    }
    seen = []

    def route(text, point="prompt", **_):
        seen.append((text, point))
        return {**base, **fields}

    monkeypatch.setattr(conduct.integration_tools, "route", route)
    return seen


def test_preflight_delegate(monkeypatch, capsys):
    delegate = _integ().delegate_entry
    seen = _stub_route(
        monkeypatch,
        action="suggest",
        entry_id=delegate,
        probabilities={delegate: 0.93, "none": 0.07},
        reason="p=0.930 at or above threshold 0.600",
        applied_threshold=0.6,
    )
    code, out = _run(capsys, "preflight", QUESTION)
    assert code == 0 and seen == [(QUESTION, "prompt")]
    assert out == {
        "delegate": True,
        "entry": delegate,
        "score": 0.93,
        "threshold": 0.6,
        "reason": "p=0.930 at or above threshold 0.600",
    }


def test_preflight_not_a_delegate(monkeypatch, capsys):
    delegate = _integ().delegate_entry
    _stub_route(monkeypatch, probabilities={delegate: 0.02, "none": 0.98})
    code, out = _run(capsys, "preflight", "What is 17% of 2,340?")
    assert code == 0
    assert out["delegate"] is False and out["entry"] is None
    assert out["score"] == 0.02 and out["threshold"] == 0.5


def test_preflight_an_error_is_json_and_exit_1(monkeypatch, capsys):
    def boom(*_a, **_k):
        raise ValueError("routing failed: nope")

    monkeypatch.setattr(conduct.integration_tools, "route", boom)
    code, out = _run(capsys, "preflight", QUESTION)
    assert code == 1 and out == {"error": "routing failed: nope"}


def test_preflight_with_the_real_local_decider(capsys):
    code, out = _run(capsys, "preflight", QUESTION)
    assert code == 0 and set(out) == {"delegate", "entry", "score", "threshold", "reason"}
    assert isinstance(out["delegate"], bool)


# --- compose -------------------------------------------------------------------------------------

CALC = "mcp__plugin_agent-router-fp_agent_router__calc"
DOCUMENT = (
    "To read a PDF (a link or a workspace file) as its own text, page by page or only the "
    "passages naming given terms, use mcp__plugin_agent-router-fp_agent_router__document_text "
    "(load it with ToolSearch); WebFetch summarises a PDF instead of returning it."
)
CAPABILITY = (
    f"Exact arithmetic is available: {CALC} for a single expression and {CALC}_script for a "
    f"script (loops, lists, small functions); load them with ToolSearch. {DOCUMENT}"
)


def test_compose_golden_with_the_calculator(capsys, tmp_path):
    code, out = _run(capsys, "compose", QUESTION)
    prompt = f"Problem statement: {QUESTION}\n{CAPABILITY}"
    assert code == 0
    assert out == {
        "prompt": prompt,
        "sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "agent_type": AGENT,
        "launcher": FALLBACK["launcher"],
        "checks": CLEAN_CHECKS,
    }


def test_compose_golden_without_the_calculator(capsys, tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "references").mkdir(parents=True)
    (root / ".claude-plugin").mkdir()
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": NAME}))
    (root / "references" / "summary-schema.json").write_text("{}")
    (root / "references" / "integration.json").write_text(
        json.dumps({**FALLBACK, "capabilities_used": []})
    )
    monkeypatch.setenv("FP_PLUGIN_ROOT", str(root))
    code, out = _run(capsys, "compose", QUESTION)
    # no exact arithmetic in the manifest: only the document tool is named
    assert code == 0 and out["prompt"] == f"Problem statement: {QUESTION}\n{DOCUMENT}"


def test_compose_without_the_served_tools_names_none(tmp_path, monkeypatch):
    fake = tmp_path / "plugin"
    (fake / "bin").mkdir(parents=True)
    (fake / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"agent_router": {"command": "${CLAUDE_PLUGIN_ROOT}/bin/mcp"}}})
    )
    monkeypatch.setattr(conduct, "_plugin_dir", lambda _i: fake)
    integ = _integ()
    resolved = conduct._resolved(integ)
    assert conduct.calc_tools(integ, resolved) == []  # no launcher file yet
    (fake / "bin" / "mcp").write_text("exec agent-router mcp --tools route,doctor\n")
    assert conduct.calc_tools(integ, resolved) == []
    (fake / "bin" / "mcp").write_text("exec agent-router mcp --tools calc,route\n")
    assert conduct.calc_tools(integ, resolved) == [integ.calc_tool]
    (fake / "bin" / "mcp").unlink()
    assert conduct.calc_tools(integ, resolved) == []


def test_the_real_plugin_serves_both_calculator_tools_and_document_text():
    integ = _integ()
    assert conduct.calc_tools(integ, conduct._resolved(integ)) == [
        integ.calc_tool,
        integ.calc_script_tool,
        integ.document_tool,
    ]


def test_compose_mirrors_the_optional_input_contract_fields(capsys):
    code, out = _run(
        capsys,
        "compose",
        QUESTION,
        "--domain",
        "education policy",
        "--constraint",
        "no extra budget",
        "--constraint",
        "state law",
        "--ground-truth",
        "180 instructional days (state handbook)",
        "--mode",
        "focused-pre-mortem",
    )
    assert code == 0
    assert out["prompt"] == (
        f"Problem statement: {QUESTION}\n"
        "Domain: education policy\n"
        "Key constraints:\n- no extra budget\n- state law\n"
        "Known ground truths:\n- 180 instructional days (state handbook)\n"
        "MODE: focused-pre-mortem\n" + CAPABILITY
    )


def test_compose_keeps_the_question_verbatim(capsys):
    odd = "  Is 2 < 3 && 'x' \"y\" $HOME `ls`?\nSecond line.  "
    _code, out = _run(capsys, "compose", odd)
    assert out["prompt"].startswith(f"Problem statement: {odd}\n")


@pytest.mark.parametrize("argv", [("   ",), ("q", "--mode", "turbo"), ("q", "--mode", "focused-")])
def test_compose_rejects_bad_input(capsys, argv):
    code, out = _run(capsys, "compose", *argv)
    assert code == 1 and "error" in out


def test_compose_writes_the_handoff_record(capsys, tmp_path):
    _code, out = _run(capsys, "compose", QUESTION)
    rec = json.loads((_state(tmp_path) / "conductor" / f"{out['sha256']}.json").read_text())
    assert set(rec) == {"sha256", "composed_at", "question_sha256", "launcher", "checks"}
    assert rec["checks"] == CLEAN_CHECKS
    assert rec["launcher"] == "conductor"
    assert rec["sha256"] == out["sha256"]
    assert rec["question_sha256"] == hashlib.sha256(QUESTION.encode()).hexdigest()
    assert datetime.fromisoformat(rec["composed_at"]).tzinfo is not None


# --- the trace recognises the hand-off (CONDUCT-05) ----------------------------------------------


def _delegation(trace, tmp_path, prompt, now=None):
    return trace.handle(
        {
            "session_id": "s",
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_input": {"subagent_type": AGENT, "prompt": prompt},
        },
        _state(tmp_path),
        now,
    )


def test_trace_recognises_a_conductor_handoff(capsys, tmp_path):
    trace = _load("fp_trace_conduct", "trace.py")
    _code, out = _run(capsys, "compose", QUESTION)
    rec = _delegation(trace, tmp_path, out["prompt"])
    assert rec["kind"] == "delegation"
    assert rec["launched_by"] == "conductor" and rec["composed_sha256"] == out["sha256"]
    assert rec["prompt_names_calc"] is True  # the capability line names the calculator


def test_trace_does_not_recognise_another_prompt(capsys, tmp_path):
    trace = _load("fp_trace_conduct", "trace.py")
    _code, out = _run(capsys, "compose", QUESTION)
    rec = _delegation(trace, tmp_path, out["prompt"] + " ")  # edited after composing
    assert rec["launched_by"] is None and "composed_sha256" not in rec
    assert _delegation(trace, tmp_path, "Analyse this.")["launched_by"] is None


def test_trace_does_not_recognise_an_expired_handoff(capsys, tmp_path):
    trace = _load("fp_trace_conduct", "trace.py")
    _code, out = _run(capsys, "compose", QUESTION)
    now = datetime.now(UTC)
    fresh = (now + timedelta(minutes=59)).isoformat()
    stale = (now + timedelta(minutes=61)).isoformat()
    assert _delegation(trace, tmp_path, out["prompt"], fresh)["launched_by"] == "conductor"
    assert _delegation(trace, tmp_path, out["prompt"], stale)["launched_by"] is None


def test_trace_ignores_an_unreadable_handoff_record(tmp_path):
    trace = _load("fp_trace_conduct", "trace.py")
    sha = hashlib.sha256(b"p").hexdigest()
    path = _state(tmp_path) / "conductor" / f"{sha}.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    assert _delegation(trace, tmp_path, "p")["launched_by"] is None
    path.write_text(json.dumps({"sha256": "0" * 64, "composed_at": datetime.now(UTC).isoformat()}))
    assert _delegation(trace, tmp_path, "p")["launched_by"] is None  # record for another hash


# --- verify --------------------------------------------------------------------------------------


FENCE = re.compile(r"```json\n(.*?)\n```", re.S)


def _analysis(tmp_path, source, stamp="20261001T012816Z"):
    """A fixture report as ``.first-principles/analysis-<stamp>.md``. The live fixtures predate
    ``conclusion.rests_on``; it is added so they are valid under the current schema."""
    src = next(REPORTS.rglob(source))
    dest = tmp_path / ".first-principles" / f"analysis-{stamp}.md"
    dest.parent.mkdir(exist_ok=True)
    text = src.read_text(encoding="utf-8")
    if source.startswith("live-"):
        m = list(FENCE.finditer(text))[-1]
        data = json.loads(m.group(1))
        data["conclusion"].setdefault("rests_on", [c["id"] for c in data["chains"][-2:]])
        text = text[: m.start(1)] + json.dumps(data, indent=2) + text[m.end(1) :]
    dest.write_text(text, encoding="utf-8")
    return dest


def test_verify_a_valid_analysis_with_its_reports(capsys, tmp_path):
    path = _analysis(tmp_path, "live-estimate-fermi.md")
    (tmp_path / ".first-principles" / "report-20261001T012816Z.md").write_text("# r\n")
    code, out = _run(capsys, "verify", str(path.relative_to(tmp_path)), "--root", str(tmp_path))
    assert code == 0
    assert out["contract_status"] == "valid" and out["decisions_verified"] is True
    assert out["decisions"]["conclusion"]["confidence"] in {"HIGH", "MEDIUM", "LOW"}
    assert out["answer_excerpt"].startswith("**Recommendation:**")
    paths = out["paths"]
    assert paths["analysis"] == str(path)
    assert paths["reader_report"] == {
        "md": str(tmp_path / ".first-principles" / "report-20261001T012816Z.md"),
        "pdf": None,  # absent is reported, never an error
    }
    assert paths["trace_dir"] == str(_state(tmp_path) / "trace")


def test_verify_a_schema_violation_is_reported_not_repaired(capsys, tmp_path):
    path = _analysis(tmp_path, "schema_violation.md")
    before = path.read_bytes()
    code, out = _run(capsys, "verify", str(path), "--root", str(tmp_path))
    assert code == 0 and out["contract_status"] == "schema_violation" and out["violations"]
    assert out["decisions_verified"] is False
    assert path.read_bytes() == before  # the analysis is only read (D-09)


def test_verify_an_analysis_without_a_block(capsys, tmp_path):
    path = tmp_path / ".first-principles" / "analysis-20261001T000000Z.md"
    path.parent.mkdir()
    path.write_text("# a report\n\nno block here\n")
    code, out = _run(capsys, "verify", str(path), "--root", str(tmp_path))
    assert code == 0 and out["contract_status"] == "absent" and out["decisions"] is None
    assert out["paths"]["reader_report"] == {"md": None, "pdf": None}


def test_verify_a_name_that_is_not_an_analysis_has_no_reader_report(capsys, tmp_path):
    (tmp_path / "r.md").write_text("# a report\n")
    _code, out = _run(capsys, "verify", "r.md", "--root", str(tmp_path))
    assert out["paths"]["reader_report"] == {"md": None, "pdf": None}


@pytest.mark.parametrize("path", ["missing.md", "../outside.md"])
def test_verify_a_bad_path_is_json_and_exit_1(capsys, tmp_path, path):
    code, out = _run(capsys, "verify", path, "--root", str(tmp_path))
    assert code == 1 and "error" in out


# --- record-root and latest-analysis ----------------------------------------------------------


def _plugin_root(base, name):
    (base / ".claude-plugin").mkdir(parents=True)
    (base / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": name}))
    return base


def test_record_root_is_resolved_as_recorded(capsys, tmp_path):
    root = _plugin_root(tmp_path / "fp", NAME)
    code, out = _run(capsys, "record-root", str(root))
    target = _state(tmp_path) / "integration" / f"{NAME}.root"
    assert code == 0 and Path(out["file"]) == target
    assert target.read_text().strip() == str(root.resolve())
    assert out["resolved"]["source"] == "fallback+root"  # no manifest in this fake root...
    assert out["resolved"]["plugin_root"] == str(root.resolve())
    resolved = integ_mod.resolve(_integ(), state_root=_state(tmp_path), env={})
    assert resolved.plugin_root == root.resolve()  # ...but the hook and trace now find the root


def test_record_root_reports_source_recorded_with_a_manifest(capsys, tmp_path):
    root = _plugin_root(tmp_path / "fp", NAME)
    (root / "references").mkdir()
    (root / "references" / "integration.json").write_text(json.dumps(FALLBACK))
    (root / "references" / "summary-schema.json").write_text("{}")
    _code, out = _run(capsys, "record-root", str(root))
    assert out["resolved"]["source"] == "recorded"


def test_record_root_rejects_the_wrong_plugin(capsys, tmp_path):
    code, out = _run(capsys, "record-root", str(_plugin_root(tmp_path / "other", "not-it")))
    assert code == 1 and "not-it" in out["error"]
    assert not (_state(tmp_path) / "integration").exists()


def test_record_root_rejects_a_directory_that_is_no_plugin(capsys, tmp_path):
    (tmp_path / "plain").mkdir()
    for target in (tmp_path / "plain", tmp_path / "nowhere"):
        code, out = _run(capsys, "record-root", str(target))
        assert code == 1 and "error" in out


def test_latest_analysis_picks_the_newest(capsys, tmp_path):
    d = tmp_path / ".first-principles"
    d.mkdir()
    old, new = d / "analysis-1.md", d / "analysis-2.md"
    old.write_text("old")
    new.write_text("new")
    (d / "analysis-3.md.process").write_text("not an analysis")
    (d / "report-1.md").write_text("not an analysis")
    os.utime(old, (2_000_000_000, 2_000_000_000))
    os.utime(new, (1_000_000_000, 1_000_000_000))
    code, out = _run(capsys, "latest-analysis", "--cwd", str(tmp_path))
    assert code == 0 and out == {"path": str(old)}  # newest by mtime, not by name


def test_latest_analysis_is_null_when_there_is_none(capsys, tmp_path):
    code, out = _run(capsys, "latest-analysis", "--cwd", str(tmp_path))
    assert code == 0 and out == {"path": None}


# --- the wrapper script and the CLI as a process -------------------------------------------------


def test_bin_conduct_runs_the_helper(tmp_path):
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "AGENT_ROUTER_STATE_DIR": str(_state(tmp_path)),
        "AGENT_ROUTER_PLUGIN_CACHE": "",
        "AGENT_ROUTER_EMBEDDER": "hashing",
    }
    done = subprocess.run(
        [str(PLUGIN / "bin" / "conduct"), "latest-analysis", "--cwd", str(tmp_path)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == {"path": None}


# --- the skill (CONDUCT-01, CONDUCT-03) -----------------------------------------------------------


def _skill():
    text = SKILL.read_text(encoding="utf-8")
    front, body = re.fullmatch(r"---\n(.*?)\n---\n(.*)", text, re.S).groups()
    return yaml.safe_load(front), body


def test_skill_frontmatter():
    meta, _body = _skill()
    assert meta["name"] == "analyze" == SKILL.parent.name
    assert meta["disable-model-invocation"] is True
    assert isinstance(meta["argument-hint"], str) and meta["argument-hint"]
    desc = meta["description"]
    assert isinstance(desc, str) and 0 < len(desc) <= 1024 and not re.search(r"<[a-z/]", desc)
    assert set(meta) == {"name", "description", "argument-hint", "disable-model-invocation"}


def test_skill_tool_names_equal_the_derived_names():
    _meta, body = _skill()
    integ = _integ()
    plugin_name = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["name"]
    assert plugin_name == integ.own_plugin_name
    served = set(
        re.search(r"--tools\s+(\S+)", (PLUGIN / "bin" / "mcp").read_text()).group(1).split(",")
    )
    derived = {
        tool: f"mcp__plugin_{plugin_name}_{integ_mod.MCP_SERVER}__{tool}"
        for tool in ("route", "verify_summary", "doctor")
    }
    assert set(derived) <= served  # the MCP server really serves what the skill calls
    used = set(re.findall(r"mcp__plugin_[A-Za-z0-9_-]+", body))
    assert used == {derived["verify_summary"]}  # health and preflight now run inside compose
    # the calculator names the compose step relies on follow the same rule
    assert integ.calc_tool == f"mcp__plugin_{plugin_name}_{integ_mod.MCP_SERVER}__calc"


def test_skill_sequences_the_helper_and_forbids_editing():
    _meta, body = _skill()
    for sub in ("compose", "report --markdown --handoff", "verify_summary"):
        assert sub in body
    # the skill and the hand-off hook give the main session the same instruction for the report
    assert conduct.SHOW_VERBATIM in " ".join(body.split())
    for phrase in ("never edit", "at most once", "character for character", "Add no instructions"):
        assert phrase.lower() in body.lower()
    assert "${CLAUDE_PLUGIN_ROOT}/bin/conduct" in body and (PLUGIN / "bin" / "conduct").is_file()


@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")
def test_claude_plugin_validate_passes():
    done = subprocess.run(
        ["claude", "plugin", "validate", str(PLUGIN)], capture_output=True, text=True, timeout=120
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_doctor_subcommand_returns_the_integration_checks(monkeypatch):
    seen = {"ok": True, "checks": [{"name": "stub", "status": "PASS", "detail": ""}]}
    monkeypatch.setattr(conduct.integration_tools, "doctor_report", lambda: seen)
    assert conduct.run(["doctor"]) is seen
