"""In-process MCP server exposing the MIT catalog tools to a Claude Agent SDK agent.

The server is named ``agent_router`` so its tools surface as ``mcp__agent_router__<tool>``,
matching the targets in ``catalog.yaml``. This is the only module that imports the SDK;
the tool logic lives in the pure ``agent_router.tools`` modules.
"""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from claude_agent_sdk import McpSdkServerConfig, SdkMcpTool, create_sdk_mcp_server, tool

from agent_router.tools import calc, html_to_markdown, json_query, repo_stats

SERVER_NAME = "agent_router"
SERVER_VERSION = "0.1.0"
_TOOLS = ("calc", "json_query", "html_to_markdown", "repo_stats")
TOOL_NAMES = [f"mcp__{SERVER_NAME}__{n}" for n in _TOOLS]


def _schema(required: list[str], **props: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {k: {"type": "string", "description": v} for k, v in props.items()},
        "required": required,
    }


def _text(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _safe(fn: Callable[[dict[str, Any]], str]) -> Callable[[dict[str, Any]], Awaitable[dict]]:
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        try:
            return _text(fn(args))
        except Exception as e:  # reported to the model as a tool error, never raised
            return {**_text(f"Error: {e}"), "is_error": True}

    return handler


def build_tools(root: Path) -> list[SdkMcpTool[Any]]:
    """The four catalog tools, with file access confined to ``root``."""
    root = Path(root).resolve()

    calc_tool = tool(
        "calc",
        "Exact calculator (agent-router, MIT). Evaluates arithmetic with exact fractions and "
        "big integers: + - * / // % **, '17% of 2340', sqrt, factorial, gcd, lcm, abs, round, "
        "comb, perm. Returns an integer, 'a/b (≈ decimal)', or '≈ decimal' if irrational.",
        _schema(["expression"], expression="Math expression, e.g. '3/7 + 5/11' or '2**200'."),
    )(_safe(lambda a: calc.evaluate(a["expression"])))

    json_tool = tool(
        "json_query",
        "Query JSON with a JMESPath expression (jmespath.py, MIT). Give exactly one of `path` "
        "(a JSON file in the workspace) or `text` (inline JSON). Returns pretty JSON.",
        _schema(
            ["expression"],
            expression="JMESPath expression, e.g. \"orders[?status=='failed'].id\".",
            path="Workspace-relative path to a JSON file.",
            text="Inline JSON text.",
        ),
    )(
        _safe(
            lambda a: json_query.query(
                a["expression"], path=a.get("path"), text=a.get("text"), root=root
            )
        )
    )

    html_tool = tool(
        "html_to_markdown",
        "Convert HTML to clean Markdown (python-markdownify, MIT), keeping headings, links, "
        "lists and tables and dropping scripts/styles. Give exactly one of `path` or `html`.",
        _schema(
            [],
            path="Workspace-relative path to an HTML file.",
            html="Inline HTML text.",
        ),
    )(_safe(lambda a: html_to_markdown.convert(path=a.get("path"), html=a.get("html"), root=root)))

    stats_tool = tool(
        "repo_stats",
        "Count files and lines of code per language under a workspace directory "
        "(agent-router, MIT), skipping .git, virtualenvs and node_modules; lists the "
        "largest files. Returns Markdown tables.",
        _schema([], path="Workspace-relative directory (default '.')."),
    )(_safe(lambda a: repo_stats.stats(a.get("path") or ".", root=root)))

    return [calc_tool, json_tool, html_tool, stats_tool]


def build_mcp_server(root: Path) -> McpSdkServerConfig:
    """In-process SDK MCP server ``agent_router`` whose tools operate inside ``root``."""
    return create_sdk_mcp_server(name=SERVER_NAME, version=SERVER_VERSION, tools=build_tools(root))
