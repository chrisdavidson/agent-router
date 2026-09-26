import json
import os
from pathlib import Path

import pytest

from agent_router.adapters.claude_tools import (
    SERVER_NAME,
    TOOL_NAMES,
    build_mcp_server,
    build_tools,
)
from agent_router.tools import calc, html_to_markdown, json_query, repo_stats

DEMO = Path(__file__).resolve().parents[1] / "demo_workspace"


# ---------------------------------------------------------------- calc


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("3/7+5/11", "68/77 (≈ 0.8831168831)"),
        ("2**200", str(2**200)),
        ("123456789 * 987654321", str(123456789 * 987654321)),
        ("17% of 2,340", "1989/5 (≈ 397.8)"),
        ("17% of 2340", "1989/5 (≈ 397.8)"),
        ("percent_of(17, 2340)", "1989/5 (≈ 397.8)"),
        ("50%", "1/2 (≈ 0.5)"),
        ("10 % 3", "1"),
        ("10 % -3", "-2"),
        ("50% + 10", "21/2 (≈ 10.5)"),
        ("7 // 2", "3"),
        ("-(3 - 5)", "2"),
        ("0.1 + 0.2", "3/10 (≈ 0.3)"),
        ("gcd(462, 1071)", "21"),
        ("gcd(4,100)", "4"),
        ("lcm(4, 6)", "12"),
        ("factorial(12)", "479001600"),
        ("comb(5, 2)", "10"),
        ("perm(5, 2)", "20"),
        ("abs(-3/4)", "3/4 (≈ 0.75)"),
        ("round(22/7, 2)", "157/50 (≈ 3.14)"),
        ("round(7/2)", "4"),
        ("sqrt(16)", "4"),
        ("sqrt(9/4)", "3/2 (≈ 1.5)"),
        ("2**-2", "1/4 (≈ 0.25)"),
    ],
)
def test_calc_exact(expr, expected):
    assert calc.evaluate(expr) == expected


def test_calc_irrational_sqrt_is_approximate():
    assert calc.evaluate("sqrt(2)") == "≈ 1.4142135624"


def test_calc_compound_interest():
    out = calc.evaluate("10000 * (1 + 5/100)**7")
    assert out.endswith("(≈ 14071.0042265625)")


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os')",
        "().__class__",
        "open('x')",
        "[1][0]",
        "x",
        "1j",
        "'a'",
        "lambda: 1",
        "round(1, ndigits=2)",
        "2**100000",
        "(10**10000)**10000",
        "factorial(100000)",
        "comb(10**9, 5)",
        "1/0",
        "1 +",
        "",
        "sqrt(-1)",
        "(-8)**(1/3)",
        "gcd(1/2, 3)",
    ],
)
def test_calc_rejects(expr):
    with pytest.raises(ValueError):
        calc.evaluate(expr)


# ---------------------------------------------------------------- json_query


def _orders(tmp_path: Path) -> Path:
    data = {
        "orders": [
            {"id": 1, "status": "paid", "total": 10},
            {"id": 2, "status": "failed", "total": 5},
            {"id": 3, "status": "failed", "total": 7},
        ]
    }
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "orders.json").write_text(json.dumps(data))
    return tmp_path


def test_json_query_file(tmp_path):
    root = _orders(tmp_path)
    out = json_query.query("orders[?status=='failed'].id", path="data/orders.json", root=root)
    assert json.loads(out) == [2, 3]
    assert out == json.dumps([2, 3], indent=2)


def test_json_query_absolute_path_inside_root(tmp_path):
    root = _orders(tmp_path)
    out = json_query.query("length(orders)", path=str(root / "data/orders.json"), root=root)
    assert out == "3"


def test_json_query_text():
    out = json_query.query("version", text='{"version": "1.2.3"}', root=Path("."))
    assert out == '"1.2.3"'


@pytest.mark.parametrize("bad", ["../../etc/passwd", "/etc/passwd", "data/../../x.json"])
def test_json_query_rejects_escape(tmp_path, bad):
    root = _orders(tmp_path)
    with pytest.raises(ValueError, match="outside"):
        json_query.query("a", path=bad, root=root)


def test_json_query_rejects_symlink_escape(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    root = tmp_path / "root"
    root.mkdir()
    os.symlink(outside, root / "link.json")
    with pytest.raises(ValueError, match="outside"):
        json_query.query("a", path="link.json", root=root)


def test_json_query_errors(tmp_path):
    root = _orders(tmp_path)
    with pytest.raises(ValueError):
        json_query.query("a", root=root)
    with pytest.raises(ValueError):
        json_query.query("a", path="data/orders.json", text="{}", root=root)
    with pytest.raises(ValueError):
        json_query.query("orders[?", path="data/orders.json", root=root)
    with pytest.raises(ValueError):
        json_query.query("a", text="{not json", root=root)
    with pytest.raises(ValueError):
        json_query.query("a", path="missing.json", root=root)


def test_json_query_demo_fixture():
    out = json_query.query("length(orders[?status=='failed'])", path="data/orders.json", root=DEMO)
    assert int(out) >= 1


# ---------------------------------------------------------------- html_to_markdown

HTML = """<html><head><title>T</title><style>body { color: red; }</style>
<script>alert('x');</script></head><body>
<h1>Release 1.0</h1><h2>Changes</h2>
<ul><li>Added export</li><li>Fixed login</li></ul>
<p>See <a href="https://example.com/docs">the docs</a>.</p>
<table><tr><th>Area</th><th>Status</th></tr><tr><td>API</td><td>done</td></tr></table>
</body></html>"""


def test_html_to_markdown_text():
    md = html_to_markdown.convert(html=HTML, root=Path("."))
    assert "# Release 1.0" in md
    assert "## Changes" in md
    assert "Added export" in md
    assert "[the docs](https://example.com/docs)" in md
    assert "| Area | Status |" in md
    assert "alert(" not in md
    assert "color: red" not in md
    assert "\n\n\n" not in md


def test_html_to_markdown_file_and_escape(tmp_path):
    (tmp_path / "page.html").write_text(HTML)
    md = html_to_markdown.convert(path="page.html", root=tmp_path)
    assert "# Release 1.0" in md
    with pytest.raises(ValueError, match="outside"):
        html_to_markdown.convert(path="../../etc/passwd", root=tmp_path)
    with pytest.raises(ValueError):
        html_to_markdown.convert(root=tmp_path)


def test_html_to_markdown_demo_fixture():
    md = html_to_markdown.convert(path="docs/release.html", root=DEMO)
    assert md.startswith("# ")
    assert "<script" not in md and "function" not in md
    assert "|" in md and "](" in md


# ---------------------------------------------------------------- repo_stats


def test_repo_stats(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("a = 1\nb = 2\nc = 3\n")
    (tmp_path / "src" / "b.py").write_text("x = 1")
    (tmp_path / "src" / "u.js").write_text("let a;\nlet b;\n")
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02\n")
    for skipped in (".git", "node_modules", ".venv", "__pycache__"):
        (tmp_path / skipped).mkdir()
        (tmp_path / skipped / "junk.py").write_text("1\n" * 100)
    out = repo_stats.stats(root=tmp_path)
    assert "| Python | 2 | 4 |" in out
    assert "| JavaScript | 1 | 2 |" in out
    assert "| **Total** | **3** | **6** |" in out
    assert "junk.py" not in out
    assert "blob.bin" not in out
    assert "| src/a.py | 3 |" in out


def test_repo_stats_subdir_and_escape(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("a\n")
    assert "| Python | 1 | 1 |" in repo_stats.stats("src", root=tmp_path)
    with pytest.raises(ValueError, match="outside"):
        repo_stats.stats("..", root=tmp_path)
    with pytest.raises(ValueError):
        repo_stats.stats("src/a.py", root=tmp_path)


# ---------------------------------------------------------------- MCP adapter


def test_build_mcp_server():
    cfg = build_mcp_server(DEMO)
    assert cfg["type"] == "sdk"
    assert cfg["name"] == SERVER_NAME == "agent_router"
    assert TOOL_NAMES == [
        "mcp__agent_router__calc",
        "mcp__agent_router__json_query",
        "mcp__agent_router__html_to_markdown",
        "mcp__agent_router__repo_stats",
    ]


def test_tool_names_match_catalog_targets():
    from agent_router.core.catalog import load_catalog

    targets = {e.target for e in load_catalog().entries if e.kind == "tool"}
    assert targets == set(TOOL_NAMES)


def test_tool_schemas_mark_optional_args():
    tools = {t.name: t for t in build_tools(DEMO)}
    assert tools["calc"].input_schema["required"] == ["expression"]
    assert tools["json_query"].input_schema["required"] == ["expression"]
    assert tools["html_to_markdown"].input_schema["required"] == []
    assert tools["repo_stats"].input_schema["required"] == []


async def test_tool_handlers():
    tools = {t.name: t for t in build_tools(DEMO)}

    res = await tools["calc"].handler({"expression": "3/7+5/11"})
    assert res["content"] == [{"type": "text", "text": "68/77 (≈ 0.8831168831)"}]
    assert not res.get("is_error")

    res = await tools["json_query"].handler(
        {"expression": "length(orders)", "path": "data/orders.json"}
    )
    assert int(res["content"][0]["text"]) >= 10
    assert not res.get("is_error")

    res = await tools["html_to_markdown"].handler({"path": "docs/release.html"})
    assert res["content"][0]["text"].startswith("# ")

    res = await tools["repo_stats"].handler({})
    assert "| Python |" in res["content"][0]["text"]


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("calc", {"expression": "__import__('os')"}),
        ("json_query", {"expression": "a", "path": "../../etc/passwd"}),
        ("html_to_markdown", {"path": "/etc/passwd"}),
        ("repo_stats", {"path": ".."}),
    ],
)
async def test_tool_handlers_error_path(name, args):
    tools = {t.name: t for t in build_tools(DEMO)}
    res = await tools[name].handler(args)
    assert res["is_error"] is True
    assert res["content"][0]["type"] == "text"
    assert res["content"][0]["text"].startswith("Error:")


# ---------------------------------------------------------------- skill


def test_commit_writer_skill():
    text = (DEMO / ".claude/skills/commit-writer/SKILL.md").read_text()
    assert text.startswith("---\n")
    front = text.split("---")[1]
    assert "name: commit-writer" in front
    assert "description:" in front and "Conventional Commits" in front
    assert "MIT" in text.split("---", 2)[2]
