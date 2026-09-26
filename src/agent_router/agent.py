"""The inner agent: a Claude Agent SDK session with the router's hooks and MIT tools.

``run_agent`` streams timeline events (schema in ``agent_router.adapters.claude_sdk``) to
``on_event`` and returns the final result text. Use ``prepare_workspace`` to run the demo in
a disposable copy of ``demo_workspace/``: the agent may run Bash there.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

from agent_router.adapters.claude_sdk import (
    MAX_EVENT_TEXT,
    ClaudeRouterHooks,
    Listener,
    emit,
)
from agent_router.adapters.claude_tools import SERVER_NAME, TOOL_NAMES, build_mcp_server
from agent_router.core.audit import AuditLog
from agent_router.core.catalog import load_catalog
from agent_router.core.config import RouterConfig
from agent_router.core.router import Router

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_MAX_TURNS = 8
NATIVE_TOOLS = ["Skill", "Read", "Glob", "Grep", "Bash", "WebFetch"]
DEMO_WORKSPACE = Path(__file__).resolve().parents[2] / "demo_workspace"


def prepare_workspace(src: Path = DEMO_WORKSPACE) -> Path:
    """Copy ``src`` into a fresh temp directory and return the copy (caller cleans up
    ``result.parent``)."""
    tmp = Path(tempfile.mkdtemp(prefix="agent-router-"))
    dest = tmp / "workspace"
    shutil.copytree(src, dest)
    return dest


def make_router(
    backend: str = "local",
    config: RouterConfig | None = None,
    audit: AuditLog | None = None,
) -> Router:
    """Router over the bundled catalog with the named decider backend."""
    from agent_router.deciders.registry import make_decider

    catalog = load_catalog()
    config = config if config is not None else RouterConfig.from_env()
    return Router(catalog, make_decider(backend, catalog), config, audit)


def build_options(
    router: Router,
    workspace: Path,
    model: str = DEFAULT_MODEL,
    max_turns: int = DEFAULT_MAX_TURNS,
    *,
    hooks: ClaudeRouterHooks | None = None,
) -> ClaudeAgentOptions:
    """SDK options: project skills, in-process MIT tools, router hooks.

    ``permission_mode`` is ``"default"`` (never ``bypassPermissions``): listed tools run
    without prompts, anything else is refused in this non-interactive session.
    """
    hooks = hooks if hooks is not None else ClaudeRouterHooks(router)
    return ClaudeAgentOptions(
        model=model,
        max_turns=max_turns,
        cwd=workspace,
        setting_sources=["project"],
        mcp_servers={SERVER_NAME: build_mcp_server(workspace)},
        allowed_tools=[*TOOL_NAMES, *NATIVE_TOOLS],
        permission_mode="default",
        hooks=hooks.hooks(),
    )


def _flatten(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text", "")))
        else:
            parts.append(str(item))
    return "\n".join(parts)


async def run_agent(
    prompt: str,
    router: Router,
    workspace: Path,
    on_event: Listener | None = None,
    *,
    model: str = DEFAULT_MODEL,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> str:
    """Run one prompt through the inner agent; returns the final result text."""
    listeners: list[Listener] = [on_event] if on_event is not None else []
    hooks = ClaudeRouterHooks(router)
    for cb in listeners:
        hooks.on_decision(cb)
    options = build_options(router, workspace, model, max_turns, hooks=hooks)
    emit(listeners, "prompt", prompt=prompt)
    final = ""
    try:
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        emit(listeners, "assistant", text=block.text)
                    elif isinstance(block, ToolUseBlock):
                        emit(listeners, "tool_use", id=block.id, name=block.name, input=block.input)
            elif isinstance(msg, UserMessage) and not isinstance(msg.content, str):
                for block in msg.content:
                    if isinstance(block, ToolResultBlock):
                        emit(
                            listeners,
                            "tool_result",
                            tool_use_id=block.tool_use_id,
                            content=_flatten(block.content)[:MAX_EVENT_TEXT],
                            is_error=bool(block.is_error),
                        )
            elif isinstance(msg, ResultMessage):
                final = msg.result or ""
                emit(
                    listeners,
                    "result",
                    result=msg.result,
                    is_error=msg.is_error,
                    num_turns=msg.num_turns,
                    total_cost_usd=msg.total_cost_usd,
                    duration_ms=msg.duration_ms,
                )
    except Exception as exc:
        emit(listeners, "error", message=f"{type(exc).__name__}: {exc}")
        raise
    return final
