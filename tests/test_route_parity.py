"""Route parity: a run started with ``/agent-router-fp:analyze`` (the conductor skill) and one
started from a plain prompt the router routed end in the same delegating prompt and the same
report.

The plain-prompt route gets the conductor's shape from the hand-off hook pair
(``plugin/bin/handoff-hook`` -> ``conduct.py hook``): PreToolUse rewrites the main session's
``Agent`` prompt to the composed one, PostToolUse hands the main session the rendered report (or,
for a background run, the ``report`` command the skill itself runs). Both renderings come from
``integration_tools.render_report``. Offline: no ``claude`` session, no decider.
"""

import hashlib
import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from agent_router import integration_tools as it
from agent_router.adapters.claude_code import turn_id

ROOT = Path(__file__).resolve().parents[1]
INTEG = ROOT / "integrations" / "first-principles"
PLUGIN = INTEG / "plugin"
BIN = PLUGIN / "bin"
REPORTS = ROOT / "tests" / "fixtures" / "fp" / "reports"
FALLBACK = json.loads((INTEG / "manifest.fallback.json").read_text())
NAME, AGENT = FALLBACK["plugin_name"], FALLBACK["agent_type"]
QUESTION = "Is a four-day school week a good idea, or do we just assume five days?"
STAMP = "20261001T012816Z"
FENCE = re.compile(r"```json\n(.*?)\n```", re.S)


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, INTEG / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


conduct = _load("fp_conduct_parity", "conduct.py")
trace = _load("fp_trace_parity", "trace.py")


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


def _analysis(tmp_path, source="live-estimate-fermi.md", answer=None):
    """A fixture report as ``<tmp>/.first-principles/analysis-<stamp>.md`` (valid block)."""
    src = next(REPORTS.rglob(source))
    dest = tmp_path / ".first-principles" / f"analysis-{STAMP}.md"
    dest.parent.mkdir(exist_ok=True)
    text = src.read_text(encoding="utf-8")
    m = list(FENCE.finditer(text))[-1]
    data = json.loads(m.group(1))
    data["conclusion"].setdefault("rests_on", [c["id"] for c in data["chains"][-2:]])
    text = text[: m.start(1)] + json.dumps(data, indent=2) + text[m.end(1) :]
    if answer is not None:
        text = re.sub(r"(?ms)^## Answer\n.*?(?=^## )", f"## Answer\n\n{answer}\n\n", text, count=1)
    dest.write_text(text, encoding="utf-8")
    (dest.parent / f"report-{STAMP}.md").write_text("# reader report\n")
    return dest


def _routed_state(tmp_path, prompt, prompt_id="p-1", routed=True):
    """The session file the router's UserPromptSubmit hook leaves after routing ``prompt``."""
    state = {"prompts": [prompt], "suggested": []}
    if routed:
        turn = turn_id({"prompt_id": prompt_id}, 1)
        state["suggested"] = [[turn, conduct._integration().delegate_entry]]
    path = tmp_path / "state" / "sessions" / "s.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


def _pre(prompt, prompt_id="p-1", **extra):
    return {
        "session_id": "s",
        "prompt_id": prompt_id,
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "tool_input": {"description": "analysis", "subagent_type": AGENT, "prompt": prompt},
        **extra,
    }


def _post(prompt, response, cwd, duration_ms=None):
    payload = {**_pre(prompt), "hook_event_name": "PostToolUse", "tool_response": response}
    payload["cwd"] = str(cwd)
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    return payload


def _context(out):
    return out["hookSpecificOutput"]["additionalContext"]


# --- the shared renderer -------------------------------------------------------------------------


def test_the_report_carries_every_field_from_the_verification(tmp_path):
    path = _analysis(tmp_path)
    res = it.verify_summary(str(path.relative_to(tmp_path)), root=tmp_path)
    md = res["report_markdown"]
    d = res["decisions"]
    assert md.startswith(f"## {NAME} analysis: result\n")
    assert res["answer_excerpt"] in md
    assert f"**Conclusion:** {d['conclusion']['recommended']}" in md
    assert f"**Confidence:** {d['conclusion']['confidence']}" in md
    gate = "cleared" if d["gate_cleared"] else "not cleared"
    assert f"**Self-Audit Gate:** {gate}" in md
    assert f"**Ground truths not read at source:** {len(d['unverified_ground_truths'])}" in md
    assert "**Summary contract:** `valid`" in md and it.NOT_VALID_NOTE not in md
    assert f"Analysis: `{path}`" in md
    assert f"Reader report: `{path.parent / f'report-{STAMP}.md'}`" in md
    assert f"Trace: `{tmp_path / 'state' / 'trace'}`" in md


def test_the_mcp_result_carries_the_paths_and_the_report(tmp_path):
    """The gap this closes: the MCP verify_summary returned no paths, only the CLI did."""
    path = _analysis(tmp_path)
    res = it.verify_summary(str(path.relative_to(tmp_path)), root=tmp_path)
    assert res["paths"] == {
        "analysis": str(path),
        "reader_report": {"md": str(path.parent / f"report-{STAMP}.md"), "pdf": None},
        "trace_dir": str(tmp_path / "state" / "trace"),
    }
    cli = conduct.report(str(path), root=str(tmp_path))
    assert cli["report_markdown"] == res["report_markdown"]


def test_a_cut_answer_is_marked(tmp_path):
    path = _analysis(tmp_path, answer="word " * 600)
    res = it.verify_summary(str(path.relative_to(tmp_path)), root=tmp_path)
    assert res["answer_truncated"] is True and len(res["answer_excerpt"]) == it.ANSWER_CHARS
    assert "cut at 1,500 characters" in res["report_markdown"]
    short = _analysis(tmp_path, answer="A short answer.")
    res = it.verify_summary(str(short.relative_to(tmp_path)), root=tmp_path)
    assert res["answer_truncated"] is False and "cut at" not in res["report_markdown"]


def test_a_contract_that_is_not_valid_says_what_it_means(tmp_path):
    path = tmp_path / ".first-principles" / "analysis-20261001T000000Z.md"
    path.parent.mkdir()
    path.write_text("# a report\n\n## Answer\n\nYes.\n\n## 1. Problem Essence\n\nx\n")
    md = it.verify_summary(str(path.relative_to(tmp_path)), root=tmp_path)["report_markdown"]
    assert f"**Summary contract:** `absent`: {it.NOT_VALID_NOTE}" in md
    assert "not available, because the summary block could not be read" in md
    assert "Reader report: not found" in md


def test_a_plugin_from_the_cache_is_flagged():
    base = {"contract_status": "valid", "decisions": None, "paths": {}}
    assert "stale copy" in it.render_report({**base, "plugin": {"name": NAME, "source": "cache"}})
    assert "stale copy" not in it.render_report({**base, "plugin": {"name": NAME, "source": "env"}})


# --- PreToolUse: the same delegating prompt ------------------------------------------------------


def test_a_routed_prompt_is_delegated_exactly_as_the_conductor_would(tmp_path):
    _routed_state(tmp_path, QUESTION)
    out = conduct.hook(_pre("Analyse the school week question from first principles."))
    new = out["hookSpecificOutput"]["updatedInput"]
    assert set(out["hookSpecificOutput"]) == {"hookEventName", "updatedInput"}  # never a deny
    assert new["prompt"] == conduct.compose(QUESTION)["prompt"]  # route 1's prompt, verbatim
    assert new["subagent_type"] == AGENT and new["description"] == "analysis"  # rest unchanged


def test_an_unrouted_delegation_composes_the_main_sessions_prompt(tmp_path):
    _routed_state(tmp_path, "something else entirely", routed=False)
    mine = "Should we rewrite the billing service? Reason from fundamentals."
    out = conduct.hook(_pre(mine))
    assert out["hookSpecificOutput"]["updatedInput"]["prompt"] == conduct.compose(mine)["prompt"]


def test_a_routed_prompt_of_an_earlier_turn_is_not_used(tmp_path):
    _routed_state(tmp_path, QUESTION, prompt_id="p-0")
    mine = "Now question the on-call rotation from scratch."
    out = conduct.hook(_pre(mine, prompt_id="p-1"))
    assert out["hookSpecificOutput"]["updatedInput"]["prompt"] == conduct.compose(mine)["prompt"]


def test_a_conductor_prompt_is_left_alone(tmp_path):
    composed = conduct.compose(QUESTION)["prompt"]
    assert conduct.hook(_pre(composed)) == {}


@pytest.mark.parametrize(
    "payload",
    [
        {**_pre("x"), "tool_input": {"subagent_type": "general-purpose", "prompt": "x"}},
        {**_pre("x"), "agent_type": AGENT},  # an Agent call inside a subagent
        {**_pre("x"), "tool_name": "Bash"},
        {**_pre(""), "tool_input": {"subagent_type": AGENT, "prompt": ""}},
        {"hook_event_name": "SubagentStop", "agent_type": AGENT},
        None,
        [],
    ],
)
def test_the_hook_ignores_everything_else(payload):
    assert conduct.hook(payload) == {}


def test_the_trace_learns_the_rewritten_prompt_at_the_runs_end(tmp_path):
    """Hooks on one event run in parallel, so the trace records the original prompt; the
    hand-off record it reads at SubagentStop says the agent got the composed one."""
    state = tmp_path / "state"
    original = "Analyse the school week question from first principles."
    _routed_state(tmp_path, QUESTION)
    rec = trace.handle(_pre(original), state)
    assert rec["launched_by"] is None and rec["prompt_names_calc"] is False
    conduct.hook(_pre(original))
    resolved = trace._rewritten(rec, state)
    assert resolved["launched_by"] == "router-hook" and resolved["rewritten"] is True
    assert resolved["prompt_names_calc"] is True  # the composed prompt's capability line
    assert resolved["composed_sha256"] == conduct.compose(QUESTION)["sha256"]
    # a delegation nothing rewrote stays as recorded
    other = trace.handle(_pre("an unrelated prompt"), state)
    assert trace._rewritten(other, state) == other


# --- PostToolUse: the same report ----------------------------------------------------------------


def test_a_foreground_run_is_handed_route_1s_report_verbatim(tmp_path):
    path = _analysis(tmp_path)
    composed = conduct.compose(QUESTION, launcher="router-hook")["prompt"]
    final = f"Report: {path.parent / f'report-{STAMP}.md'}\nWorking file: {path}\nDone."
    out = conduct.hook(_post(composed, {"status": "completed", "content": final}, tmp_path))
    route1 = conduct.report(str(path), root=str(tmp_path))["report_markdown"]
    ctx = _context(out)
    assert ctx.endswith(route1) and conduct.SHOW_VERBATIM in ctx


def test_the_report_takes_the_named_analysis_over_a_newer_one(tmp_path):
    path = _analysis(tmp_path)
    newer = path.parent / "analysis-20991231T000000Z.md"
    newer.write_text("# other\n")
    blocks = [{"type": "text", "text": f"The working file is `{path}`."}]
    out = conduct.hook(_post("p", {"status": "completed", "content": blocks}, tmp_path))
    assert f"Analysis: `{path}`" in _context(out)


def test_a_background_run_is_told_to_run_the_skills_report_command(tmp_path):
    path = _analysis(tmp_path)
    out = conduct.post_agent(
        _post("p", {"status": "async_launched", "isAsync": True}, tmp_path), now=1_800_000_000
    )
    ctx = _context(out)
    assert conduct.SHOW_VERBATIM in ctx
    sha = hashlib.sha256(b"p").hexdigest()
    cmd = conduct.report_command(1_800_000_000 - conduct.SINCE_SKEW_S, sha)
    assert (
        cmd in ctx and f"report --markdown --handoff {sha}" in cmd and str(BIN / "conduct") in cmd
    )
    # what that command prints, once the analysis exists, is route 1's report
    os.utime(path, (1_800_000_100, 1_800_000_100))
    later = conduct.report(None, since=1_800_000_000 - 5, root=str(tmp_path))
    assert (
        later["report_markdown"] == conduct.report(str(path), root=str(tmp_path))["report_markdown"]
    )


def test_an_analysis_from_before_the_run_is_not_reported(tmp_path):
    path = _analysis(tmp_path)
    os.utime(path, (1_000, 1_000))
    out = conduct.post_agent(
        _post("p", {"status": "completed", "content": "no path here"}, tmp_path, duration_ms=1000),
        now=1_800_000_000,
    )
    ctx = _context(out)
    assert "No analysis file was found." in ctx and "no path here" in ctx


def test_a_conductor_run_is_left_to_the_skill(tmp_path):
    _analysis(tmp_path)
    composed = conduct.compose(QUESTION)["prompt"]  # launcher: conductor
    assert conduct.hook(_post(composed, {"status": "completed", "content": "x"}, tmp_path)) == {}


# --- both routes, end to end, through the shipped scripts ---------------------------------------


def _script(name, *args, stdin="", cwd=None, env=None):
    proc = subprocess.run(
        [str(BIN / name), *args],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**os.environ, **(env or {})},
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_route_1_and_route_2_give_the_same_prompt_and_the_same_report(tmp_path):
    env = {"AGENT_ROUTER_STATE_DIR": str(tmp_path / "state")}
    # route 1: the skill's compose step, then its report step
    r1 = json.loads(_script("conduct", "compose", QUESTION, env=env))
    r1_prompt = r1["prompt"]
    path = _analysis(tmp_path)
    r1_report = _script(
        "conduct",
        "report",
        "--markdown",
        "--handoff",
        r1["sha256"],
        str(path),
        cwd=tmp_path,
        env=env,
    )
    # route 2: the router routed the plain prompt; the main session wrote its own Agent prompt
    _routed_state(tmp_path, QUESTION)
    pre = json.loads(_script("handoff-hook", stdin=json.dumps(_pre("my own words")), env=env))
    r2_prompt = pre["hookSpecificOutput"]["updatedInput"]["prompt"]
    post_in = _post(
        r2_prompt, {"status": "completed", "content": f"Working file: {path}"}, tmp_path
    )
    out = _script("handoff-hook", stdin=json.dumps(post_in), env=env)
    assert "\n" not in out.strip()  # one line: bin/_failopen.sh passes only that through
    r2_report = _context(json.loads(out))
    assert r2_prompt == r1_prompt
    assert r2_report.endswith(r1_report)
    # identical prompts share one hand-off record; the latest run's launcher labels it, so the
    # trace credits this plain-prompt run to the hook, and a later conductor run to the skill
    sha = hashlib.sha256(r1_prompt.encode()).hexdigest()
    rec = json.loads((tmp_path / "state" / "conductor" / f"{sha}.json").read_text())
    assert rec["launcher"] == "router-hook"


@pytest.mark.parametrize(
    "stdin",
    ["", "not json", "[]", json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash"})],
)
def test_the_handoff_script_fails_open(stdin, tmp_path):
    out = _script("handoff-hook", stdin=stdin, env={"AGENT_ROUTER_STATE_DIR": str(tmp_path)})
    assert out == "{}\n"


def test_the_handoff_script_fails_open_when_the_helper_crashes(tmp_path):
    stub = tmp_path / "python"
    stub.write_text("#!/bin/sh\necho 'Traceback: boom' >&2\nexit 3\n")
    stub.chmod(0o755)
    out = _script(
        "handoff-hook",
        stdin=json.dumps(_pre("x")),
        env={"AGENT_ROUTER_PYTHON": str(stub), "AGENT_ROUTER_STATE_DIR": str(tmp_path)},
    )
    assert out == "{}\n"


def test_a_multi_line_conclusion_stays_inside_its_bullet():
    rec = "Four steps:\n1. Measure.\n\n2. Trial."
    md = it.render_report(
        {
            "contract_status": "valid",
            "decisions": {"conclusion": {"recommended": rec, "confidence": "LOW"}},
            "paths": {},
        }
    )
    assert (
        "- **Conclusion:** Four steps:\n  1. Measure.\n\n  2. Trial.\n- **Confidence:** LOW" in md
    )


# --- run checks: proceed and warn, the same either way ---------------------------------------

BASE = {"contract_status": "valid", "decisions": None, "paths": {}}


def test_clean_checks_add_nothing_to_the_report():
    assert it.check_lines(CLEAN_CHECKS) == []
    assert it.render_report({**BASE, "checks": CLEAN_CHECKS}) == it.render_report(BASE)


def test_unclean_checks_are_shown():
    checks = {
        "health": {
            "ran": True,
            "ok": False,
            "flagged": [{"name": "hooks wiring", "status": "FAIL", "detail": "bin/x missing"}],
        },
        "preflight": {"ran": True, "delegate": False, "score": 0.12, "threshold": 0.6},
    }
    md = it.render_report({**BASE, "checks": checks})
    assert "- **Install health (FAIL):** FAIL hooks wiring: bin/x missing" in md
    assert "(score 0.12, threshold 0.60); it was analysed anyway" in md
    lines = it.check_lines({"health": {"ran": False, "error": "timed out after 6 s"}})
    assert lines == [
        "- **Install health:** not checked (timed out after 6 s)",
        "- **Router preflight:** not run (unknown)",
    ]
    assert "not recorded" in it.check_lines({"missing": True})[0]


def test_the_report_reads_the_checks_from_the_handoff_record(tmp_path, monkeypatch):
    path = _analysis(tmp_path)
    flagged = {**CLEAN_CHECKS, "preflight": {"ran": True, "delegate": False}}
    monkeypatch.setattr(conduct, "run_checks", lambda question: flagged)
    sha = conduct.compose(QUESTION)["sha256"]
    md = conduct.report(str(path), root=str(tmp_path), handoff=sha)["report_markdown"]
    assert "it was analysed anyway" in md
    missing = conduct.report(str(path), root=str(tmp_path), handoff="0" * 64)["report_markdown"]
    assert "**Run checks:** not recorded" in missing
    # route 2's hook composes with the same checks, so both reports carry the same line
    _routed_state(tmp_path, QUESTION)
    rewritten = conduct.hook(_pre("my words"))["hookSpecificOutput"]["updatedInput"]["prompt"]
    final = f"Working file: {path}"
    ctx = _context(conduct.hook(_post(rewritten, {"content": final}, tmp_path)))
    assert ctx.endswith(md)


def test_run_checks_never_raise_and_are_bounded(monkeypatch):
    real = _load("fp_conduct_checks", "conduct.py")

    def boom():
        raise RuntimeError("no doctor")

    monkeypatch.setattr(real.integration_tools, "doctor_report", boom)
    monkeypatch.setattr(real, "preflight", lambda q: __import__("time").sleep(5))
    monkeypatch.setattr(real, "PREFLIGHT_BUDGET_S", 0.2)
    out = real.run_checks("q")
    assert out["health"] == {"ran": False, "error": "RuntimeError: no doctor"}
    assert out["preflight"] == {"ran": False, "error": "timed out after 0.2 s"}


def test_the_mcp_fallback_gives_the_skill_the_same_report(tmp_path, monkeypatch):
    path = _analysis(tmp_path)
    flagged = {**CLEAN_CHECKS, "preflight": {"ran": True, "delegate": False}}
    monkeypatch.setattr(conduct, "run_checks", lambda question: flagged)
    sha = conduct.compose(QUESTION)["sha256"]
    cli = conduct.report(str(path), root=str(tmp_path), handoff=sha)["report_markdown"]
    rel = str(path.relative_to(tmp_path))
    mcp = it.verify_summary(rel, root=tmp_path, handoff=sha)["report_markdown"]
    assert mcp == cli and "analysed anyway" in mcp


def test_a_cut_ending_in_a_blank_line_leaves_no_run_of_blank_lines():
    md = it.render_report({**BASE, "answer_excerpt": "text\n\n", "answer_truncated": True})
    assert "\n\n\n" not in md and "text\n\n*(The Answer is cut" in md
