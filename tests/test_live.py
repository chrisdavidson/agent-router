"""Live end-to-end test: a real Claude Agent SDK session (uses your Claude login).

Run with: ``AGENT_ROUTER_EMBEDDER=model2vec .venv/bin/pytest -m live tests/test_live.py -s``
"""

import json
import shutil

import pytest

from agent_router.agent import DEMO_WORKSPACE, make_router, prepare_workspace, run_agent
from agent_router.core.audit import AuditLog
from agent_router.core.config import RouterConfig

pytestmark = pytest.mark.live

MODEL = "claude-haiku-4-5-20251001"


async def test_inner_agent_takes_calc_suggestion(monkeypatch):
    monkeypatch.setenv("AGENT_ROUTER_EMBEDDER", "model2vec")
    audit = AuditLog(None)
    router = make_router("local", RouterConfig(), audit)
    workspace = prepare_workspace(DEMO_WORKSPACE)
    events = []
    try:
        result = await run_agent(
            "What is 2**200 exactly?", router, workspace, events.append, model=MODEL
        )
    finally:
        shutil.rmtree(workspace.parent, ignore_errors=True)

    for e in events:
        print(json.dumps(e, default=str)[:300])
    print("RESULT:", result)

    routed = [
        r
        for r in audit.records
        if r["action"] in ("suggest", "enforce") and r["entry_id"] == "exact-calc"
    ]
    assert routed, f"no exact-calc suggestion in audit: {audit.records}"
    tool_uses = [e["name"] for e in events if e["type"] == "tool_use"]
    assert "mcp__agent_router__calc" in tool_uses, tool_uses
    assert "1606938044258990275541962092341162602522202993782792835301376" in result.replace(
        ",", ""
    )
