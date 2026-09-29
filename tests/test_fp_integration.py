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
    assert set(hooks) == {"UserPromptSubmit", "PreToolUse"}
    assert os.access(plugin / "bin" / "hook", os.X_OK)


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
