"""Stdio MCP server ``agent_router`` for hosts that load MCP servers as processes.

``agent-router mcp`` serves the catalog tools to Claude Code (a plugin's ``.mcp.json``), where
they surface as ``mcp__plugin_<plugin>_agent_router__<tool>``. File tools are confined to the
working directory the host starts the server in. ``--tools`` limits what is served.

Three more tools, ``route``, ``verify_summary`` and ``doctor``, are *integration* tools: they
exist only when the server runs with an integration (``AGENT_ROUTER_INTEGRATION``, see
:mod:`agent_router.integration_tools`). They are read-only and report errors as tool errors.

Works with the ``mcp`` package 1.x (``FastMCP``) and 2.x (``MCPServer``).
"""

from __future__ import annotations

import functools
import json
import os
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from agent_router.tools import calc, html_to_markdown, json_query, repo_stats

SERVER_NAME = "agent_router"
TOOLS = ("calc", "calc_script", "json_query", "html_to_markdown", "repo_stats")
INTEGRATION_TOOLS = ("route", "verify_summary", "doctor")


def default_tools(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """What ``agent-router mcp`` serves without ``--tools``: the catalog tools, plus the
    integration tools when an integration is in force."""
    env = os.environ if env is None else env
    if env.get("AGENT_ROUTER_INTEGRATION", "").strip():
        return (*TOOLS, *INTEGRATION_TOOLS)
    return TOOLS


def _server_class() -> Callable[..., Any]:
    try:
        from mcp.server.mcpserver import MCPServer  # mcp >= 2

        return MCPServer
    except ImportError:
        from mcp.server.fastmcp import FastMCP  # mcp 1.x

        return FastMCP


def _tool_error_class() -> type[Exception]:
    try:
        from mcp.server.mcpserver.exceptions import ToolError  # mcp >= 2
    except ImportError:
        from mcp.server.fastmcp.exceptions import ToolError  # type: ignore  # mcp 1.x
    return ToolError


def _expected(fn: Callable[..., str]) -> Callable[..., str]:
    """Report a tool's ``ValueError`` as the SDK's ``ToolError``, so its message reaches the model.

    The SDK treats any other exception as a crash and sends only ``Error executing tool <name>``:
    measured in the first-principles runs, the agent retried 7 failed calculator calls without
    learning why (e.g. ``log()`` is not supported).
    """
    tool_error = _tool_error_class()

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return fn(*args, **kwargs)
        except (ValueError, OSError) as e:
            raise tool_error(str(e)) from e

    return wrapper


def _as_json(fn: Callable[..., Any]) -> Callable[..., str]:
    """An integration tool's result as JSON text; any failure becomes a ``ValueError`` (and so
    a tool error), because these tools are called by a conductor that must never crash."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return json.dumps(fn(*args, **kwargs), indent=2, ensure_ascii=False, default=str)
        except (ValueError, OSError):
            raise
        except Exception as e:
            raise ValueError(f"{fn.__name__} failed: {type(e).__name__}: {e}") from e

    return wrapper


def build_server(root: Path, tools: Iterable[str] = TOOLS) -> Any:
    """The ``agent_router`` MCP server with the chosen tools, files confined to ``root``."""
    root = Path(root).resolve()
    wanted = set(tools)
    unknown = wanted - {*TOOLS, *INTEGRATION_TOOLS}
    if unknown:
        raise ValueError(f"unknown tools: {', '.join(sorted(unknown))}")
    needs_integration = wanted & set(INTEGRATION_TOOLS)
    if needs_integration and not os.environ.get("AGENT_ROUTER_INTEGRATION", "").strip():
        raise ValueError(
            f"{', '.join(sorted(needs_integration))} need an integration: "
            "set AGENT_ROUTER_INTEGRATION to its directory"
        )
    server = _server_class()(SERVER_NAME)

    if "calc" in wanted:

        @server.tool(name="calc")
        @_expected
        def calc_tool(expression: str) -> str:
            """Exact calculator (agent-router, MIT). Evaluates arithmetic with exact fractions
            and big integers: + - * / // % **, '17% of 2340', sqrt, factorial, gcd, lcm, abs,
            round, comb, perm. Returns an integer, 'a/b (≈ decimal)', or '≈ decimal' if
            irrational. A list evaluates each item: '[2*3, 7/2]'. Example expressions:
            '3/7 + 5/11', '2**200', '10000*(1+5/100)**7'."""
            return calc.evaluate(expression)

    if "calc_script" in wanted:

        @server.tool(name="calc_script")
        @_expected
        def calc_script_tool(script: str) -> str:
            """Exact calculator for a short python-style script (agent-router, MIT). Statements
            separated by newlines or ';': `import math`, `name = expression`, `name += expression`,
            `print(...)` and bare expressions; each print or bare expression returns one line
            '<expression> = <value>'. Exact fractions and big integers, plus math.log, ln, log10,
            log2, exp, sqrt, pi and e (shown as '≈ decimal'). No loops, functions, f-strings,
            lists, subscripts, files or other imports: those return an error naming the line."""
            return calc.evaluate_script(script)

    if "json_query" in wanted:

        @server.tool(name="json_query")
        @_expected
        def json_query_tool(
            expression: str, path: str | None = None, text: str | None = None
        ) -> str:
            """Query JSON with a JMESPath expression (jmespath.py, MIT). Give exactly one of
            `path` (a JSON file in the workspace) or `text` (inline JSON). Returns pretty JSON."""
            return json_query.query(expression, path=path, text=text, root=root)

    if "html_to_markdown" in wanted:

        @server.tool(name="html_to_markdown")
        @_expected
        def html_to_markdown_tool(path: str | None = None, html: str | None = None) -> str:
            """Convert HTML to clean Markdown (python-markdownify, MIT), keeping headings,
            links, lists and tables. Give exactly one of `path` or `html`."""
            return html_to_markdown.convert(path=path, html=html, root=root)

    if "repo_stats" in wanted:

        @server.tool(name="repo_stats")
        @_expected
        def repo_stats_tool(path: str = ".") -> str:
            """Count files and lines of code per language under a workspace directory
            (agent-router, MIT), skipping .git, virtualenvs and node_modules."""
            return repo_stats.stats(path or ".", root=root)

    if wanted & set(INTEGRATION_TOOLS):
        from agent_router import integration_tools as it

    if "route" in wanted:

        @server.tool(name="route")
        @_expected
        @_as_json
        def route_tool(
            text: str,
            point: str = "prompt",
            tool: str | None = None,
            tool_input_json: str | dict[str, Any] | None = None,
            agent_type: str | None = None,
        ) -> str:
            """Routing decision for one step, as JSON (what `agent-router route --json` prints):
            action, entry_id, choice, probabilities, confidence, reason, hint, threshold.
            `point` is prompt, tool or skill; for a tool step give `tool` (e.g. Bash) and its
            input as a JSON object (or its JSON text) in `tool_input_json`; `agent_type` is the
            subagent making the call (entries are scoped to one), omitted on the main thread.
            Read-only and advisory."""
            return it.route(text, point, tool, tool_input_json, agent_type)

    if "verify_summary" in wanted:

        @server.tool(name="verify_summary")
        @_expected
        @_as_json
        def verify_summary_tool(path: str) -> str:
            """Check an analysis file against the plugin's published summary contract. Returns
            JSON: contract_status, violations, the schema (path, source, version), the
            decisions read from the block (run_mode, conclusion, gate, unverified ground
            truths, assumption counts) and the report's Answer section excerpt. Read-only; `path`
            must be inside the working directory."""
            return it.verify_summary(path, root=root)

    if "doctor" in wanted:

        @server.tool(name="doctor")
        @_expected
        @_as_json
        def doctor_tool() -> str:
            """Install health checks for this integration as JSON: {ok, checks: [{name, status,
            detail}]} with status PASS, WARN or FAIL. Read-only."""
            return it.doctor_report()

    return server
