"""Unit tests for the Claude Agent SDK adapter and inner agent runner (no SDK session)."""

from pathlib import Path

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from agent_router import agent as agent_mod
from agent_router.adapters.claude_sdk import EVENT_TYPES, ClaudeRouterHooks
from agent_router.adapters.claude_tools import TOOL_NAMES
from agent_router.agent import build_options, prepare_workspace, run_agent
from agent_router.core.audit import AuditLog
from agent_router.core.catalog import load_catalog
from agent_router.core.config import RouterConfig
from agent_router.core.router import Router
from agent_router.core.types import NONE_ID, ChoiceResult

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "demo_workspace"
SECRET = "SECRET-EXCEPTION-TEXT"


class RuleDecider:
    """Deterministic stand-in: picks an option by keyword in the decider state."""

    name = "rule"

    def __init__(self, rules=None, error=None):
        self.rules = rules if rules is not None else {}
        self.error = error
        self.states = []

    def decide(self, state, options):
        self.states.append(state)
        if self.error:
            raise self.error
        choice = NONE_ID
        for needle, entry_id in self.rules.items():
            if needle in state and entry_id in options:
                choice = entry_id
                break
        probs = {k: (0.9 if k == choice else 0.1 / (len(options) - 1)) for k in options}
        return ChoiceResult(choice, probs, confidence=0.8, backend="rule", latency_ms=1.5)


CALC_RULES = {"2**200": "exact-calc"}


def make_hooks(rules=CALC_RULES, error=None, **cfg):
    decider = RuleDecider(rules, error)
    audit = AuditLog(None)
    router = Router(load_catalog(), decider, RouterConfig(**cfg), audit)
    return ClaudeRouterHooks(router), decider, audit


def prompt_input(prompt, session="s1"):
    return {
        "session_id": session,
        "transcript_path": "/tmp/t.jsonl",
        "cwd": "/tmp",
        "hook_event_name": "UserPromptSubmit",
        "prompt": prompt,
    }


def tool_input(tool_name, tool_in, session="s1"):
    return {
        "session_id": session,
        "transcript_path": "/tmp/t.jsonl",
        "cwd": "/tmp",
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_in,
        "tool_use_id": "toolu_1",
    }


# -- hooks -------------------------------------------------------------------


async def test_prompt_gets_additional_context():
    hooks, _, audit = make_hooks()
    out = await hooks.on_user_prompt(prompt_input("What is 2**200 exactly?"), None, None)
    spec = out["hookSpecificOutput"]
    assert spec["hookEventName"] == "UserPromptSubmit"
    assert "mcp__agent_router__calc" in spec["additionalContext"]
    assert audit.records[-1]["action"] == "suggest"
    assert audit.records[-1]["entry_id"] == "exact-calc"


async def test_bash_python_calc_gets_hint():
    hooks, decider, audit = make_hooks()
    # the prompt itself does not match; the pending Bash command does
    await hooks.on_user_prompt(prompt_input("how big is this number?"), None, None)
    out = await hooks.on_pre_tool_use(
        tool_input("Bash", {"command": 'python3 -c "print(2**200)"'}), "toolu_1", None
    )
    spec = out["hookSpecificOutput"]
    assert spec["hookEventName"] == "PreToolUse"
    assert "mcp__agent_router__calc" in spec["additionalContext"]
    assert "permissionDecision" not in spec
    rec = audit.records[-1]
    assert (rec["point"], rec["tool_name"], rec["entry_id"]) == ("tool", "Bash", "exact-calc")
    # state carries the last prompt and the pending call
    assert "how big is this number?" in decider.states[-1]
    assert "pending Bash" in decider.states[-1]


async def test_skill_maps_to_skill_point_and_hints_commit_writer():
    hooks, _, audit = make_hooks({"release-notes": "commit-writer"})
    await hooks.on_user_prompt(prompt_input("write a commit message for my fix"), None, None)
    # the prompt got no hint (rule only fires on the pending skill)
    assert audit.records[-1]["action"] == "native"
    out = await hooks.on_pre_tool_use(
        tool_input("Skill", {"skill": "release-notes", "args": "fix login"}), "toolu_2", None
    )
    assert 'skill="commit-writer"' in out["hookSpecificOutput"]["additionalContext"]
    rec = audit.records[-1]
    assert (rec["point"], rec["tool_name"], rec["action"]) == ("skill", "Skill", "suggest")


async def test_own_tool_returns_empty():
    hooks, decider, audit = make_hooks({"": "exact-calc"})
    out = await hooks.on_pre_tool_use(
        tool_input("mcp__agent_router__calc", {"expression": "2**200"}), "t", None
    )
    assert out == {}
    assert audit.records[-1]["action"] == "skipped"
    assert decider.states == []


async def test_own_skill_returns_empty():
    hooks, decider, _ = make_hooks({"": "commit-writer"})
    out = await hooks.on_pre_tool_use(tool_input("Skill", {"skill": "commit-writer"}), "t", None)
    assert out == {}
    assert decider.states == []


async def test_enforce_mode_denies_native_tool():
    hooks, _, _ = make_hooks(mode="enforce")
    await hooks.on_user_prompt(prompt_input("hello"), None, None)
    out = await hooks.on_pre_tool_use(
        tool_input("Bash", {"command": "python3 -c 'print(2**200)'"}), "t", None
    )
    spec = out["hookSpecificOutput"]
    assert spec["hookEventName"] == "PreToolUse"
    assert spec["permissionDecision"] == "deny"
    assert "mcp__agent_router__calc" in spec["permissionDecisionReason"]
    assert spec["permissionDecisionReason"].startswith("[agent-router] Blocked Bash")


async def test_native_decision_returns_empty():
    hooks, _, _ = make_hooks({})
    assert (
        await hooks.on_user_prompt(prompt_input("what is the capital of France"), None, None) == {}
    )


async def test_decider_error_never_surfaces_reason():
    hooks, _, audit = make_hooks(error=RuntimeError(SECRET))
    out = await hooks.on_user_prompt(prompt_input("2**200"), None, None)
    assert out == {}
    assert SECRET in audit.records[-1]["reason"]  # audit keeps it for operators


async def test_hook_never_raises_into_sdk(monkeypatch):
    hooks, _, _ = make_hooks()

    def boom(event):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(hooks.router, "route", boom)
    assert await hooks.on_user_prompt(prompt_input("2**200"), None, None) == {}
    assert await hooks.on_pre_tool_use(tool_input("Bash", {"command": "x"}), "t", None) == {}
    # malformed input too
    assert await hooks.on_pre_tool_use({}, None, None) == {}
    assert await hooks.on_user_prompt({}, None, None) == {}


async def test_turn_ids_increment_per_session_and_dedupe_per_turn():
    hooks, _, audit = make_hooks()
    await hooks.on_user_prompt(prompt_input("2**200 please", "a"), None, None)
    await hooks.on_user_prompt(prompt_input("hello", "b"), None, None)
    # same turn: the calc hint was already given at the prompt, so the Bash call is skipped
    out = await hooks.on_pre_tool_use(
        tool_input("Bash", {"command": "python3 -c 'print(2**200)'"}, "a"), "t", None
    )
    assert out == {}
    assert audit.records[-1]["action"] == "skipped"
    await hooks.on_user_prompt(prompt_input("and 2**200 again", "a"), None, None)
    turns = [(r["session"], r["turn"]) for r in audit.records]
    assert turns == [("a", 1), ("b", 1), ("a", 1), ("a", 2)]
    assert audit.records[-1]["action"] == "suggest"


async def test_recent_prompts_feed_state():
    hooks, decider, _ = make_hooks({})
    await hooks.on_user_prompt(prompt_input("first question"), None, None)
    await hooks.on_user_prompt(prompt_input("second question"), None, None)
    assert "previous: first question" in decider.states[-1]


async def test_on_decision_emits_payload_without_reason():
    hooks, _, _ = make_hooks(error=None)
    events = []
    hooks.on_decision(events.append)
    await hooks.on_user_prompt(prompt_input("What is 2**200?"), None, None)
    decision = [e for e in events if e["type"] == "decision"][-1]
    assert decision["action"] == "suggest"
    assert decision["entry_id"] == "exact-calc"
    assert decision["point"] == "prompt"
    assert decision["tool_name"] is None
    assert decision["backend"] == "rule"
    assert decision["latency_ms"] == 1.5
    assert decision["confidence"] == 0.8
    assert decision["probabilities"]["exact-calc"] == pytest.approx(0.9)
    assert "mcp__agent_router__calc" in decision["hint"]
    assert "reason" not in decision
    hook = [e for e in events if e["type"] == "hook"][-1]
    assert hook["output"] == "additionalContext"
    assert all(e["type"] in EVENT_TYPES for e in events)


async def test_listener_errors_are_swallowed():
    hooks, _, _ = make_hooks()

    def bad(_):
        raise RuntimeError("listener")

    hooks.on_decision(bad)
    out = await hooks.on_user_prompt(prompt_input("2**200"), None, None)
    assert "additionalContext" in out["hookSpecificOutput"]


def test_hooks_registration():
    hooks, _, _ = make_hooks()
    reg = hooks.hooks()
    assert set(reg) == {"UserPromptSubmit", "PreToolUse"}
    assert reg["UserPromptSubmit"][0].hooks == [hooks.on_user_prompt]
    assert reg["PreToolUse"][0].matcher is None
    assert reg["PreToolUse"][0].hooks == [hooks.on_pre_tool_use]


# -- agent runner --------------------------------------------------------------


def test_prepare_workspace_copies_to_temp(tmp_path):
    ws = prepare_workspace(DEMO)
    try:
        assert ws != DEMO and ws.resolve() != DEMO.resolve()
        assert (ws / ".claude/skills/commit-writer/SKILL.md").is_file()
        assert (ws / "data/orders.json").is_file()
        (ws / "data/orders.json").write_text("{}")
        assert (DEMO / "data/orders.json").read_text() != "{}"
    finally:
        import shutil

        shutil.rmtree(ws.parent, ignore_errors=True)


def test_build_options(tmp_path):
    hooks, _, _ = make_hooks()
    opts = build_options(hooks.router, tmp_path)
    assert opts.setting_sources == ["project"]
    assert opts.cwd == tmp_path
    assert opts.permission_mode == "default"
    assert opts.model == "claude-haiku-4-5-20251001"
    assert opts.max_turns == 8
    assert "agent_router" in opts.mcp_servers
    for t in [*TOOL_NAMES, "Skill", "Read", "Glob", "Grep", "Bash", "WebFetch"]:
        assert t in opts.allowed_tools
    assert set(opts.hooks) == {"UserPromptSubmit", "PreToolUse"}


async def test_run_agent_streams_events(monkeypatch, tmp_path):
    hooks_seen = {}

    async def fake_query(*, prompt, options):
        hooks_seen["options"] = options
        # drive the registered hooks like the CLI would
        up = options.hooks["UserPromptSubmit"][0].hooks[0]
        await up(prompt_input(prompt), None, None)
        yield AssistantMessage(
            content=[
                TextBlock("Let me compute."),
                ToolUseBlock("toolu_9", "mcp__agent_router__calc", {"expression": "2**200"}),
            ],
            model="m",
        )
        yield UserMessage(
            content=[
                ToolResultBlock(
                    "toolu_9", "1606938044258990275541962092341162602522202993782792835301376"
                )
            ]
        )
        yield ResultMessage(
            subtype="success",
            duration_ms=10,
            duration_api_ms=5,
            is_error=False,
            num_turns=2,
            session_id="s1",
            total_cost_usd=0.001,
            result="2**200 = 1606938044258990275541962092341162602522202993782792835301376",
        )

    monkeypatch.setattr(agent_mod, "query", fake_query)
    hooks, _, _ = make_hooks()
    events = []
    out = await run_agent("What is 2**200 exactly?", hooks.router, tmp_path, events.append)
    assert out.startswith("2**200 = 1606938")
    types = [e["type"] for e in events]
    assert types[0] == "prompt"
    for t in ("decision", "hook", "assistant", "tool_use", "tool_result", "result"):
        assert t in types
    assert all(t in EVENT_TYPES for t in types)
    tu = next(e for e in events if e["type"] == "tool_use")
    assert tu["name"] == "mcp__agent_router__calc"
    assert tu["input"] == {"expression": "2**200"}
    res = next(e for e in events if e["type"] == "result")
    assert res["total_cost_usd"] == 0.001
    assert hooks_seen["options"].permission_mode == "default"


async def test_run_agent_emits_error_and_reraises(monkeypatch, tmp_path):
    async def fake_query(*, prompt, options):
        raise RuntimeError("cli died")
        yield  # pragma: no cover

    monkeypatch.setattr(agent_mod, "query", fake_query)
    hooks, _, _ = make_hooks()
    events = []
    with pytest.raises(RuntimeError):
        await run_agent("hi", hooks.router, tmp_path, events.append)
    assert events[-1]["type"] == "error"
    assert "cli died" in events[-1]["message"]
