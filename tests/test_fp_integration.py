"""integrations/first-principles: catalog, eval set, plugin files and battery helpers."""

import importlib.util
import json
import os
from pathlib import Path

import pytest

from agent_router.core.catalog import load_catalog
from agent_router.core.types import HookPoint
from agent_router.evaluate import load_cases

INTEG = Path(__file__).resolve().parents[1] / "integrations" / "first-principles"
FP = "first-principles:first-principles"


def _battery():
    spec = importlib.util.spec_from_file_location("fp_battery", INTEG / "battery.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_catalog_scopes_each_entry():
    cat = load_catalog(INTEG / "catalog.yaml")
    delegate = cat.get("first-principles-agent")
    assert delegate.kind == "agent" and delegate.target == FP and delegate.agents == ("main",)
    # no entry routes to an individual first-principles technique (that is Step 0's job)
    assert not any(
        e.target.startswith("first-principles:") and e.kind == "skill" for e in cat.entries
    )
    assert cat.eligible(HookPoint.PROMPT, agent_type=FP) == []


def test_eval_set_ids_unique_and_labels_known():
    cat = load_catalog(INTEG / "catalog.yaml")
    cases = load_cases(INTEG / "eval_set.yaml")
    assert len({c.id for c in cases}) == len(cases)
    known = {e.id for e in cat.entries} | {"none"}
    assert {c.expected for c in cases} <= known
    holdout = [c for c in cases if c.id.startswith("fp-")]
    assert len(holdout) == 33 and all(c.split == "test" for c in holdout)


def test_calibration_is_tagged_with_the_integration_catalog():
    cal = json.loads((INTEG / "calibration.json").read_text())
    version = load_catalog(INTEG / "catalog.yaml").version
    assert cal["model2vec"]["catalog_version"] == version


def test_plugin_files():
    plugin = INTEG / "plugin"
    manifest = json.loads((plugin / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "agent-router-fp"
    hooks = json.loads((plugin / "hooks" / "hooks.json").read_text())["hooks"]
    assert set(hooks) == {
        "UserPromptSubmit",
        "PreToolUse",
        "SubagentStart",
        "SubagentStop",
        "PostToolUse",
        "PostToolUseFailure",
    }
    for event in ("SubagentStart", "SubagentStop"):
        assert hooks[event][0]["matcher"] == FP
    assert os.access(plugin / "bin" / "hook", os.X_OK)
    assert os.access(plugin / "bin" / "trace", os.X_OK)


def test_delegated_call_detection():
    battery = _battery()
    call = {
        "type": "assistant",
        "message": {
            "content": [{"type": "tool_use", "name": "Agent", "input": {"subagent_type": FP}}]
        },
    }
    assert battery.delegated_call(call)
    other = json.loads(json.dumps(call).replace(FP, "general-purpose"))
    assert not battery.delegated_call(other)
    assert not battery.delegated_call({"type": "result"})


@pytest.mark.model
def test_holdout_meets_first_principles_thresholds(monkeypatch):
    """The nudge alone clears the bar first-principles sets for its own routing."""
    from agent_router.deciders import local
    from agent_router.evaluate import make_router, run_eval

    monkeypatch.setattr(local, "CALIBRATION_PATH", INTEG / "calibration.json")
    cat = load_catalog(INTEG / "catalog.yaml")
    router = make_router("local", cat)
    cases = [c for c in load_cases(INTEG / "eval_set.yaml") if c.id.startswith("fp-")]
    report = run_eval(lambda: router, cases)
    got = {r.id: r.predicted for r in report.results}
    p_ok = sum(got[c.id] == c.expected for c in cases if c.expected != "none")
    n_ok = sum(got[c.id] == "none" for c in cases if c.expected == "none")
    assert p_ok >= 11 and n_ok >= 18


def _hook(payload, tmp_path):
    import subprocess

    env = {
        **os.environ,
        "AGENT_ROUTER_STATE_DIR": str(tmp_path),
        "AGENT_ROUTER_EMBEDDER": "hashing",  # offline: no model download
    }
    out = subprocess.run(
        [str(INTEG / "plugin" / "bin" / "hook")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=True,
    )
    return json.loads(out.stdout)


def test_plugin_serves_only_the_calculator():
    mcp = json.loads((INTEG / "plugin" / ".mcp.json").read_text())["mcpServers"]
    assert list(mcp) == ["agent_router"]
    script = (INTEG / "plugin" / "bin" / "mcp").read_text()
    assert "mcp --tools calc" in script
    target = load_catalog(INTEG / "catalog.yaml").get("exact-calc").target
    assert target == "mcp__plugin_agent-router-fp_agent_router__calc"


def test_hook_fast_path_for_main_thread_bash(tmp_path):
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "s",
        "tool_name": "Bash",
        "tool_input": {"command": "python3 -c 'print(2**64)'"},
    }
    assert _hook(payload, tmp_path) == {}
    assert not (tmp_path / "audit").exists()  # answered by the shell, not the router


def test_hook_skips_the_agents_report_writes(tmp_path):
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "s",
        "prompt_id": "p",
        "agent_type": FP,
        "tool_name": "Bash",
        "tool_input": {"command": "cat >> \".first-principles/a.md\" <<'X'\n12 x 1500 = 18000\nX"},
    }
    assert _hook(payload, tmp_path) == {}
    (line,) = (tmp_path / "audit" / "s.jsonl").read_text().splitlines()
    assert json.loads(line)["reason"] == "skip pattern"


# --- decision trace (trace.py, plugin/bin/trace) -----------------------------------------------


def _trace():
    spec = importlib.util.spec_from_file_location("fp_trace", INTEG / "trace.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ANALYSIS = """# First-Principles Analysis — test

Run mode: `full-composer`

**Re-entry disclosure.** One edge fired: the Self-Audit Gate's Fix/Repeat. It re-scored C2.

## Techniques not applied (process output)

- fishbone (Phase 2) — not applicable — one cause
- trade-off (Phase 4) — not applicable — one option

## Self-Audit Gate (process output)

**Criterion 1: Identify Essence**
Band: **Rigorous**

**Criterion 2: Challenge Assumptions**
Band: **Hand-wavy**

**Criterion 2: Challenge Assumptions**
Band: **Sound**

Gate result: no criterion Absent; Fix/Repeat fired once.

## 1. Problem Essence

**Core problem:** x

## 2. Assumptions Table

| Assumption | Type | Treatment | Verdict | Verification |
|---|---|---|---|---|
| (A1) Demand grows | untested belief | Verify | Challenge — no data | unverified — flagged |
| (A2) Energy is conserved | physical law | Accept | Accept — law | textbook |
| (A3) Copy peers | convention — analogy-as-evidence | Challenge | **Discard** — analogy | n/a |

## 3. Ground Truths

- **GT-1** Energy is conserved — source: physics
- **GT-2?** Demand is 10/day — unverified: no telemetry

## 4. Derivation Chains

### Conclusion C1: The load fits

GT-1 + GT-2? -> fits

**Confidence:** MEDIUM — GT-2? unverified

### Conclusion C2: [Illustrative] Cost is low

**Confidence:** LOW

### Conclusion C3 [Speculative]: Queues shrink

**Confidence:** LOW

## 5. Abandoned Reasoning

### Dead End: copy the competitor
### Dead End 2: "scale first"

## 6. Conclusion

**Recommended approach:** Measure demand first (chain C1).

**Confidence:** MEDIUM — C1 rests on GT-2?
"""


def test_parse_analysis_reads_every_decision():
    d = _trace().parse_analysis(ANALYSIS)
    assert d["run_mode"] == "full-composer"
    assert d["re_entry"] == {
        "fired": True,
        "disclosure": "Re-entry disclosure. One edge fired: the Self-Audit Gate's Fix/Repeat",
    }
    assert d["sections"][-6:] == [
        "1. Problem Essence",
        "2. Assumptions Table",
        "3. Ground Truths",
        "4. Derivation Chains",
        "5. Abandoned Reasoning",
        "6. Conclusion",
    ]
    a = d["assumptions"]
    assert a["count"] == 3
    assert a["by_type"] == {"untested belief": 1, "physical law": 1, "convention": 1}
    assert a["by_verdict"] == {"Challenge": 1, "Accept": 1, "Discard": 1}
    assert d["ground_truths"] == {"count": 2, "unverified": ["GT-2?"]}
    chains = [(c["id"], c["tag"], c["confidence"]) for c in d["chains"]]
    assert chains == [("C1", None, "MEDIUM"), ("C2", None, "LOW"), ("C3", "[Speculative]", "LOW")]
    assert d["dead_ends"] == ["copy the competitor", '"scale first"']
    assert [t["technique"] for t in d["techniques_not_applied"]] == ["fishbone", "trade-off"]
    gate = d["gate"]
    assert gate["passes"] == 2 and gate["fix_repeat"] is True
    assert gate["bands"] == {"2": "Sound"}  # the last pass
    assert gate["criteria"] == {"1": "Identify Essence", "2": "Challenge Assumptions"}
    assert gate["result"].startswith("no criterion Absent")
    assert d["conclusion"]["confidence"] == "MEDIUM"
    assert d["conclusion"]["recommended"].startswith("Measure demand first")


def test_parse_analysis_tolerates_a_partial_file():
    d = _trace().parse_analysis("## 1. Problem Essence\n\nhalf written")
    assert d["chains"] == [] and d["gate"]["passes"] == 0
    assert d["conclusion"] == {"recommended": None, "confidence": None}


def _audit(path, *recs):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in recs))


def test_trace_records_a_run_and_links_the_routers_decisions(tmp_path):
    tr = _trace()
    work = tmp_path / "work"
    (work / ".first-principles").mkdir(parents=True)
    report = work / ".first-principles" / "analysis-20260929T000000Z.md"
    report.write_text(ANALYSIS)
    state = tmp_path / "state"
    _audit(
        state / "audit" / "s.jsonl",
        {
            "ts": "2026-09-29T10:00:00+00:00",
            "point": "prompt",
            "action": "suggest",
            "entry_id": "first-principles-agent",
            "applied_threshold": 0.55,
            "probabilities": {"first-principles-agent": 0.8},
        },
        {
            "ts": "2026-09-29T10:02:00+00:00",
            "point": "tool",
            "agent_type": FP,
            "action": "suggest",
            "entry_id": "exact-calc",
        },
    )
    base = {"session_id": "s", "agent_type": FP, "agent_id": "a1", "cwd": str(work)}
    steps = [
        ("2026-09-29T10:01:00Z", {"hook_event_name": "SubagentStart"}),
        (
            "2026-09-29T10:01:10Z",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Read",
                "tool_input": {"file_path": "/x/agents/references/pre-mortem.md"},
            },
        ),
        (
            "2026-09-29T10:01:20Z",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "python3 -c 'print(1/3)'"},
                "tool_response": {"stdout": "0.333"},
            },
        ),
        (
            "2026-09-29T10:02:30Z",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": tr.CALC_TOOL,
                "tool_input": {"expression": "1/3"},
                "tool_response": [{"type": "text", "text": "1/3"}],
            },
        ),
        (
            "2026-09-29T10:02:40Z",
            {
                "hook_event_name": "PostToolUseFailure",
                "tool_name": tr.CALC_TOOL,
                "tool_input": {"expression": "1/0"},
                "error": "division by zero",
            },
        ),
        (
            "2026-09-29T10:03:00Z",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {
                    "command": 'cat >> ".first-principles/analysis-'
                    "20260929T000000Z.md\" <<'FP_EOF'\n## 6. Conclusion"
                    "\n### Conclusion C1: x\nbody\nFP_EOF"
                },
                "tool_response": {"stdout": ""},
            },
        ),
        (
            "2026-09-29T10:03:30Z",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {
                    "command": "cd .first-principles && python3 - <<'PY'\n"
                    "s=open(p).read()\nopen(p,'w').write(s.replace(a,b))\nPY"
                },
                "tool_response": {"stdout": ""},
            },
        ),
        (
            "2026-09-29T10:04:00Z",
            {"hook_event_name": "SubagentStop", "last_assistant_message": "Analysis written."},
        ),
    ]
    for ts, extra in steps:
        tr.handle({**base, **extra}, state, now=ts)
    recs = [json.loads(x) for x in (state / "trace" / "s.jsonl").read_text().splitlines()]
    assert [r["kind"] for r in recs] == [
        "run_start",
        "reference_read",
        "shell",
        "calc",
        "tool_failed",
        "section_written",
        "report_op",
        "run_end",
    ]
    assert recs[1]["meaning"] == "adversarial pass on a plan (Phase 5)"
    assert recs[2]["math"] is True
    assert recs[3] == {**recs[3], "expression": "1/3", "result": "1/3"}
    assert recs[4]["was"] == "calc" and recs[4]["expression"] == "1/0"
    assert recs[5]["headings"] == ["6. Conclusion", "Conclusion C1: x"]
    end = recs[-1]
    assert end["duration_s"] == 180.0
    assert end["analysis"] == str(report)
    assert end["references_read"] == ["pre-mortem.md"]
    assert recs[6]["op"] == "revise"
    assert end["sections_written"] == 1 and end["tool_failures"] == 1
    assert end["report_revisions"] == 1
    assert end["decisions"]["gate"]["fix_repeat"] is True
    assert end["routing"] == {
        "delegation": {
            "action": "suggest",
            "entry_id": "first-principles-agent",
            "p": 0.8,
            "applied_threshold": 0.55,
        },
        "calc_notes": 1,
        "calc_calls": 2,
        "calc_failures": 1,
        "shell_math_calls": 1,
        "calc_calls_after_note": 2,
        "shell_math_after_note": 0,
        "calc_note_followed": True,
    }


def test_trace_ignores_everything_outside_the_agent(tmp_path):
    tr = _trace()
    main = {
        "session_id": "s",
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
    }
    other = {**main, "agent_type": "general-purpose", "agent_id": "x"}
    unrelated = {
        **main,
        "agent_type": FP,
        "agent_id": "a",
        "tool_name": "Grep",
        "tool_input": {"pattern": "x"},
    }
    plain_read = {**unrelated, "tool_name": "Read", "tool_input": {"file_path": "/src/a.py"}}
    for payload in (main, other, unrelated, plain_read):
        assert tr.handle(payload, tmp_path) is None
    assert not (tmp_path / "trace").exists()


def _run_trace(payload, tmp_path):
    import subprocess

    env = {**os.environ, "AGENT_ROUTER_STATE_DIR": str(tmp_path)}
    env.pop("AGENT_ROUTER_DISABLED", None)
    out = subprocess.run(
        [str(INTEG / "plugin" / "bin" / "trace")],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=True,
    )
    return json.loads(out.stdout)


def test_trace_hook_is_record_only_and_fails_open(tmp_path):
    start = {
        "hook_event_name": "SubagentStart",
        "session_id": "s",
        "agent_type": FP,
        "agent_id": "a",
    }
    assert _run_trace(start, tmp_path) == {}
    assert json.loads((tmp_path / "trace" / "s.jsonl").read_text())["kind"] == "run_start"
    main = {
        "hook_event_name": "PostToolUse",
        "session_id": "m",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
    }
    assert _run_trace(main, tmp_path) == {}
    assert not (tmp_path / "trace" / "m.jsonl").exists()  # answered by the shell
    garbage = '{"agent_type": "first-principles:first-principles", not json'
    assert _run_trace(garbage, tmp_path) == {}


def test_trace_replays_a_capture(tmp_path):
    tr = _trace()
    work = tmp_path / "w"
    (work / ".first-principles").mkdir(parents=True)
    (work / ".first-principles" / "analysis-1.md").write_text(ANALYSIS)
    call = {"type": "tool_use", "id": "ag", "name": "Agent", "input": {"subagent_type": FP}}
    read = {
        "type": "tool_use",
        "id": "r1",
        "name": "Read",
        "input": {"file_path": "/p/references/trade-off.md"},
    }
    capture = [
        {"type": "system", "subtype": "init", "session_id": "s", "cwd": str(work)},
        {"type": "assistant", "timestamp": "2026-09-29T10:00:00Z", "message": {"content": [call]}},
        {
            "type": "assistant",
            "timestamp": "2026-09-29T10:00:05Z",
            "parent_tool_use_id": "ag",
            "message": {"content": [read]},
        },
        {
            "type": "user",
            "timestamp": "2026-09-29T10:00:06Z",
            "parent_tool_use_id": "ag",
            "message": {"content": [{"type": "tool_result", "tool_use_id": "r1", "content": "x"}]},
        },
        {
            "type": "user",
            "timestamp": "2026-09-29T10:05:00Z",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": "ag", "content": "done"}]
            },
        },
    ]
    path = tmp_path / "run.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in capture))
    for payload, ts in tr.replay_payloads(path):
        tr.handle(payload, tmp_path / "state", now=ts)
    recs = [
        json.loads(x) for x in (tmp_path / "state" / "trace" / "s.jsonl").read_text().splitlines()
    ]
    assert [r["kind"] for r in recs] == ["run_start", "reference_read", "run_end"]
    assert recs[-1]["duration_s"] == 300.0
    assert recs[-1]["analysis"].endswith("analysis-1.md")  # found in cwd: no append recorded


def test_trace_report_has_one_row_per_finished_run(tmp_path):
    tr = _trace()
    work = tmp_path / "w"
    (work / ".first-principles").mkdir(parents=True)
    (work / ".first-principles" / "analysis-1.md").write_text(ANALYSIS)
    base = {"session_id": "s", "agent_type": FP, "cwd": str(work)}
    for agent in ("a1", "a2"):
        tr.handle({**base, "agent_id": agent, "hook_event_name": "SubagentStart"}, tmp_path)
    tr.handle({**base, "agent_id": "a1", "hook_event_name": "SubagentStop"}, tmp_path)
    rows = tr.report(tmp_path / "trace").splitlines()[2:]
    assert len(rows) == 1  # a2 never finished
    assert "MEDIUM" in rows[0] and "| yes |" in rows[0]  # confidence, Fix/Repeat


def test_hook_skips_in_place_report_revisions(tmp_path):
    """Revisions cd into .first-principles without naming it with a slash (seen live)."""
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "s",
        "prompt_id": "p",
        "agent_type": FP,
        "tool_name": "Bash",
        "tool_input": {
            "command": "cd /w/.first-principles && python3 - <<'PY'\n"
            "s=open('analysis-1.md').read()\nprint(12 * 1500)\nPY"
        },
    }
    assert _hook(payload, tmp_path) == {}
    (line,) = (tmp_path / "audit" / "s.jsonl").read_text().splitlines()
    assert json.loads(line)["reason"] == "skip pattern"


def test_trace_flags_revisions_and_restarts_of_the_report():
    tr = _trace()

    def bash(cmd):
        return tr._tool_record({"tool_name": "Bash", "tool_input": {"command": cmd}})

    restart = bash('P=/w/.first-principles/analysis-1.md\n: > "$P"\ncat >> "$P" <<E\n# A\nE')
    assert restart["kind"] == "section_written" and restart["restarts"] and not restart["revises"]
    plain = bash('cat >> "/w/.first-principles/analysis-1.md" <<E\nx : > y\nE')
    assert not plain["restarts"]
    fix = bash(
        'F=/w/.first-principles/a.md; sed -i \'s/six/seven/\' "$F"; cat >> "$F" <<E\n## 1. X\nE'
    )
    assert fix["kind"] == "section_written" and fix["revises"]
    assert bash("cd /w/.first-principles && grep -c '^#' analysis-1.md")["op"] == "check"
    assert tr.parse_analysis("- **Re-entry edges fired:** none.")["re_entry"]["fired"] is False
    assert tr.parse_analysis("no disclosure")["re_entry"] is None
