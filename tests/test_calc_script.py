"""The calculator's script form: the evaluator, its fit check, the MCP tools, the catalog entry
and the trace record. Offline; the integration tools run against the integration directory."""

import asyncio
import importlib.util
import json
import re
import time
from pathlib import Path

import pytest

from agent_router.core.config import RouterConfig
from agent_router.core.fit import FITS, calc_expression, calc_script
from agent_router.core.router import Router
from agent_router.core.types import ChoiceResult, HookPoint, RouterEvent
from agent_router.tools import calc

INTEG = Path(__file__).resolve().parents[1] / "integrations" / "first-principles"
FP = "first-principles:first-principles"


# --- approximate functions and constants in a single expression ----------------------------------


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("log(2)", "≈ 0.6931471806"),
        ("ln(e)", "≈ 1"),
        ("math.log(8, 2)", "≈ 3"),
        ("log10(1000)", "≈ 3"),
        ("log2(1024)", "≈ 10"),
        ("exp(1)", "≈ 2.7182818285"),
        ("2 * pi", "≈ 6.2831853072"),
        ("math.pi", "≈ 3.1415926536"),
        ("math.sqrt(16)", "4"),  # exact stays exact
        ("log(1)", "0"),
        ("exp(0)", "1"),
    ],
)
def test_approximate_functions_and_constants(expr, expected):
    assert calc.evaluate(expr) == expected


@pytest.mark.parametrize(
    ("expr", "message"),
    [
        ("log(0)", "domain"),
        ("log(-3)", "domain"),
        ("ln(0)", "domain"),
        ("log10(-1)", "domain"),
        ("log(2, 1)", "base 1"),
        ("log(2, -2)", "domain"),
        ("exp(10000)", "too large"),
        ("log()", "argument"),
        ("log(1, 2, 3)", "argument"),
        ("math.os", "not defined"),
        ("x", "not defined"),
    ],
)
def test_approximate_function_errors_say_why(expr, message):
    with pytest.raises(ValueError, match=message):
        calc.evaluate(expr)


# --- scripts -----------------------------------------------------------------------------------


def test_script_with_variables_and_math():
    script = (
        "import math\n"
        "Th = 838.15; Tc = 303.15\n"
        "eta = 1 - Tc / Th\n"
        "L = math.log(Th / Tc)\n"
        "L += 1\n"
        "print(eta, L)\n"
        "eta * 100\n"
    )
    first, second = calc.evaluate_script(script).splitlines()
    assert first.startswith("eta = ") and ", L = ≈ " in first
    assert second.startswith("eta * 100 = ")


def test_script_output_lines_and_labels():
    out = calc.evaluate_script("x = 2\nprint('total', x * 3)\nx + 1\nprint()")
    assert out.splitlines() == ["total, x * 3 = 6", "x + 1 = 3"]


def test_script_names_carry_the_inexact_flag():
    out = calc.evaluate_script(
        "import math\na = math.log(10)\nb = a * 0\nprint(b)\nc = 3\nprint(c)"
    )
    assert out.splitlines() == ["b = ≈ 0", "c = 3"]


def test_script_from_math_import_and_semicolons():
    assert calc.evaluate_script("from math import log, pi; print(log(1), pi)") == (
        "log(1) = 0, pi = ≈ 3.1415926536"
    )


def test_script_agrees_with_python_on_the_agents_kind_of_figures():
    script = (
        "import math\n"
        "Th=838.15;Tl=563.15;Tc=303.15\n"
        "L=math.log(Th/Tl);Tm=(Th-Tl)/L\n"
        "print('lorenz', 1-Tc/Tm)\n"
        "print(5*3.6e9/(1530*275))\n"
    )
    import math

    Th, Tl, Tc = 838.15, 563.15, 303.15
    Tm = (Th - Tl) / math.log(Th / Tl)
    first, second = calc.evaluate_script(script).splitlines()
    number = re.compile(r"[-+]?\d+(?:\.\d+)?")
    got1 = float(number.findall(first.split("=")[-1])[-1])
    got2 = float(number.findall(second.split("=")[-1])[-1])
    assert got1 == pytest.approx(1 - Tc / Tm, rel=1e-6)
    assert got2 == pytest.approx(5 * 3.6e9 / (1530 * 275), rel=1e-6)


@pytest.mark.parametrize(
    ("script", "message"),
    [
        ("for i in range(3):\n    print(i)", r"line 1: for loop"),
        ("while True:\n    pass", "while loop"),
        ("def f():\n    return 1", "function definition"),
        ("print(1)\nopen('x')", "line 2: unknown function 'open'"),
        ("open('x').read()", "only plain calls"),
        ("__import__('os').system('id')", "only plain calls"),
        ("().__class__", "attribute access"),
        ("x = 1\nx.real", "attribute access"),
        ("import os", "only 'import math'"),
        ("from os import path", "only 'from math import"),
        ("from math import *", "not supported"),
        ("print(2 ** 100000)", "exponent too large"),
        ("x = 10 ** 5000\nprint(x * x * x * x * x * x * x * x)", "too large|digits"),
        ("print(f'{1}')", "f-strings are not supported"),
        ("print([1, 2])", "list is not supported"),
        ("x = [1][0]", "list is not supported|subscript"),
        ("print([i for i in y])", "comprehension"),
        ("a, b = 1, 2", "assignments are supported"),
        ("a = b = 1", "assignments are supported"),
        ("e = 2", "cannot assign to 'e'"),
        ("log = 2", "cannot assign to 'log'"),
        ("math = 2", "cannot assign to 'math'"),
        ("x += 1", "not defined"),
        ("print(y)", "not defined"),
        ("print(1, sep='')", "keyword arguments"),
        ("x = 1", "prints nothing"),
        ("", "empty script"),
        ("print(1 +", "invalid script"),
        ("print(1)\n" * 201, "too many statements"),
        ("x = 1\n" + "\n".join(f"v{i} = 1" for i in range(101)) + "\nprint(x)", "too many names"),
        ("# " + "x" * 10_001 + "\nprint(1)", "too long"),
        ("print(1/0)", "division by zero"),
        ("print(1 if 2 else 3)", "conditional expression"),
        ("print(1 < 2)", "comparison"),
        ("global x", "Global|global"),
        ("with open('f') as f:\n    pass", "with statement"),
        ("try:\n    pass\nexcept Exception:\n    pass", "try statement"),
        ("assert 1", "assert"),
        ("lambda: 1", "lambda"),
        ("print(**{})", "only plain calls|keyword"),
    ],
)
def test_script_rejects(script, message):
    with pytest.raises(ValueError, match=message):
        calc.evaluate_script(script)


def test_script_never_executes_anything(tmp_path):
    marker = tmp_path / "ran"
    for script in (
        f"open({str(marker)!r}, 'w').write('x')",
        f"__import__('pathlib').Path({str(marker)!r}).touch()",
        f"import os\nos.system('touch {marker}')",
    ):
        with pytest.raises(ValueError):
            calc.evaluate_script(script)
    assert not marker.exists()


def test_script_worst_case_is_fast():
    script = "x = 9 ** 9999\n" + "x = x * x\nprint(x)\n" * 3
    t0 = time.monotonic()
    with pytest.raises(ValueError):
        calc.evaluate_script(script)
    stmts = "\n".join(f"v{i % 90} = {i} ** 0.5 + exp(1)" for i in range(150)) + "\nprint(v1)"
    calc.evaluate_script(stmts)
    assert time.monotonic() - t0 < 5


# --- the fit check ------------------------------------------------------------------------------

HEREDOC = "python3 - <<'EOF'\nimport math\nx = 3\ny = x * 4\nprint(math.log(y))\nEOF"


@pytest.mark.parametrize(
    "command",
    [
        HEREDOC,
        HEREDOC + "\n",
        "python3 <<EOF\nx = 2\nprint(x * 3)\nEOF",
        "python <<'EOF'\nx = 2\nprint(x * 3)\nEOF",
        "cat <<'EOF' | python3\nx = 2\nprint(x * 3)\nEOF",
        "cat <<EOF | python3 -\nx = 2\nprint(x * 3)\nEOF",
        'python3 -c "\nimport math\nx = 3\nprint(math.log(x))\n"',
        "python3 -c 'x = 3; y = x * 2; print(y)'",
        "python3 -c \"import math\nx=3\nprint('ln', math.log(x))\"",
    ],
)
def test_a_script_the_calculator_runs_fits(command):
    assert calc_script({"command": command})
    assert not calc_expression({"command": command})  # the two never both take a call


@pytest.mark.parametrize(
    "command",
    [
        "python3 - <<'EOF'\nfor i in range(3):\n    print(i)\nEOF",  # loop
        "python3 - <<'EOF'\nimport numpy as np\nprint(np.pi)\nEOF",  # not math
        "python3 - <<'EOF'\nprint(open('f').read())\nEOF",  # I/O
        "python3 - <<'EOF'\nx = 1\nEOF",  # prints nothing
        "python3 <<EOF\nx = $HOME\nprint(x)\nEOF",  # shell-expanded before python sees it
        'python3 -c "x = 3\nprint($HOME)"',
        "python3 - <<'EOF'\nprint(1)\nEOF\nrm -rf /tmp/x",  # something after the heredoc
        "cat > f.py <<'EOF'\nx = 1\nprint(x)\nEOF",  # writes a file, runs nothing
        "cd /tmp && python3 - <<'EOF'\nprint(1)\nEOF",
        'python3 -c "print(1)" extra',
        'python3 -c "import math; print(math.log(2))"',  # one expression: exact-calc's
        "ls -la",
        "",
    ],
)
def test_anything_else_does_not_fit_the_script_form(command):
    assert not calc_script({"command": command})


def test_the_fit_is_registered_by_name():
    assert FITS["calc_script"] is calc_script and FITS["calc_expression"] is calc_expression


def test_single_expression_with_log_now_fits_the_expression_form():
    assert calc_expression({"command": 'python3 -c "print(math.log(2))"'})


# --- the catalog entry, routing and the trace --------------------------------------------------


def _catalog():
    from agent_router.contracts.integration import variables_for_catalog
    from agent_router.core.catalog import load_catalog

    path = INTEG / "catalog.yaml"
    return load_catalog(path, variables=variables_for_catalog(path))


def test_the_script_entry_is_scoped_like_the_calculator():
    from agent_router.contracts.integration import load_integration
    from agent_router.core.types import HookPoint

    integ = load_integration(INTEG)
    cat = _catalog()
    entry = cat.get(integ.calc_script_entry)
    assert entry.kind == "tool" and entry.target == integ.calc_script_tool
    assert entry.fits == "calc_script" and entry.replaces == ("Bash",)
    assert entry.agents == (FP,)
    assert [e.id for e in cat.eligible(HookPoint.TOOL, "Bash", FP)] == [
        "exact-calc",
        "exact-calc-script",
    ]
    assert cat.eligible(HookPoint.TOOL, "Bash", "main") == []
    # every example is a script the calculator really runs
    for ex in entry.examples:
        assert calc_script({"command": ex}), ex


class _Spy:
    """A decider that records the options it was offered."""

    name = "spy"

    def __init__(self):
        self.options = []

    def decide(self, state, options):
        self.options = list(options)
        return ChoiceResult(
            choice="none", probabilities={k: 1 / len(options) for k in options}, confidence=0.5
        )


@pytest.mark.parametrize(
    ("command", "offered"),
    [
        (HEREDOC, ["exact-calc-script"]),
        ('python3 -c "print(0.17 * 2340)"', ["exact-calc"]),
        ("python3 - <<'EOF'\nfor i in range(2):\n    print(i)\nEOF", []),
        ("git log --oneline", []),
    ],
)
def test_the_fit_checks_decide_which_calculator_entry_is_offered(command, offered):
    spy = _Spy()
    router = Router(_catalog(), spy, RouterConfig())
    router.route(
        RouterEvent(
            point=HookPoint.TOOL,
            session_id="s",
            turn_id=1,
            text="",
            tool_name="Bash",
            tool_input={"command": command},
            agent_type=FP,
        )
    )
    assert [o for o in spy.options if o != "none"] == offered


def _trace():
    spec = importlib.util.spec_from_file_location("fp_trace_script", INTEG / "trace.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_trace_records_a_script_call_as_a_calc_record(tmp_path):
    tr = _trace()
    base = {"session_id": "s", "agent_type": FP, "agent_id": "a1", "cwd": str(tmp_path)}
    ok = tr.handle(
        {
            **base,
            "hook_event_name": "PostToolUse",
            "tool_name": tr.CALC_SCRIPT_TOOL,
            "tool_input": {"script": "x = 2\nprint(x * 3)"},
            "tool_response": [{"type": "text", "text": "x * 3 = 6"}],
        },
        tmp_path,
        now="2026-10-15T10:00:00Z",
    )
    assert ok["kind"] == "calc" and ok["script"] is True
    assert ok["expression"] == "x = 2\nprint(x * 3)" and "x * 3 = 6" in ok["result"]
    failed = tr.handle(
        {
            **base,
            "hook_event_name": "PostToolUseFailure",
            "tool_name": tr.CALC_SCRIPT_TOOL,
            "tool_input": {"script": "for i in x: pass"},
            "error": "line 1: for loop is not supported",
        },
        tmp_path,
        now="2026-10-15T10:00:01Z",
    )
    assert failed["kind"] == "tool_failed" and failed["was"] == "calc" and failed["script"] is True


def test_the_trace_counts_a_script_note_and_call():
    tr = _trace()
    ts = "2026-10-15T10:00:30+00:00"
    audit = [
        {
            "ts": ts,
            "point": "tool",
            "agent_type": FP,
            "action": "suggest",
            "entry_id": tr.CALC_SCRIPT_ENTRY,
            "tool_use_id": "t1",
            "options": [tr.CALC_SCRIPT_ENTRY, "none"],
        }
    ]
    run = [
        {"kind": "shell", "interpreter": True, "tool_use_id": "t1", "ts": "2026-10-15T10:00:29Z"},
        {"kind": "calc", "script": True, "ts": "2026-10-15T10:01:00Z"},
    ]
    start = tr._when("2026-10-15T10:00:00Z")
    end = tr._when("2026-10-15T10:05:00Z")
    routing = tr._routing(audit, run, None, start, end)
    assert routing["calc_notes"] == 1 and routing["calc_calls"] == 1
    assert routing["interpreter_calls_calc_could_run"] == 1


# --- MCP surface ---------------------------------------------------------------------------------


def test_mcp_serves_calc_script_and_the_default_has_no_integration_tools(tmp_path, monkeypatch):
    from agent_router.adapters import mcp_stdio

    monkeypatch.delenv("AGENT_ROUTER_INTEGRATION", raising=False)
    assert mcp_stdio.default_tools() == mcp_stdio.TOOLS
    server = mcp_stdio.build_server(tmp_path)
    names = [t.name for t in asyncio.run(server.list_tools())]
    assert names == list(mcp_stdio.TOOLS) and "calc_script" in names
    res = asyncio.run(
        server.call_tool("calc_script", {"script": "import math\nprint(math.log(1))"})
    )
    assert "math.log(1) = 0" in json.dumps(res, default=str)
    with pytest.raises(Exception) as err:
        asyncio.run(server.call_tool("calc_script", {"script": "for i in x: pass"}))
    assert "for loop" in str(err.value) and type(err.value).__name__ == "ToolError"


def test_integration_tools_need_an_integration(tmp_path, monkeypatch):
    from agent_router.adapters import mcp_stdio

    monkeypatch.delenv("AGENT_ROUTER_INTEGRATION", raising=False)
    with pytest.raises(ValueError, match="need an integration"):
        mcp_stdio.build_server(tmp_path, ["route"])
    monkeypatch.setenv("AGENT_ROUTER_INTEGRATION", str(INTEG))
    assert mcp_stdio.default_tools() == (*mcp_stdio.TOOLS, *mcp_stdio.INTEGRATION_TOOLS)
    server = mcp_stdio.build_server(tmp_path, ["calc", "route", "verify_summary", "doctor"])
    assert [t.name for t in asyncio.run(server.list_tools())] == [
        "calc",
        "route",
        "verify_summary",
        "doctor",
    ]


def test_sdk_parity_serves_calc_script(tmp_path):
    from agent_router.adapters.claude_tools import EXTRA_TOOL_NAMES, build_tools

    tools = {t.name: t for t in build_tools(tmp_path)}
    assert EXTRA_TOOL_NAMES == ["mcp__agent_router__calc_script"]
    assert tools["calc_script"].input_schema["required"] == ["script"]
    res = asyncio.run(tools["calc_script"].handler({"script": "x = 2\nprint(x ** 10)"}))
    assert res["content"][0]["text"] == "x ** 10 = 1024"
    res = asyncio.run(tools["calc_script"].handler({"script": "while 1: pass"}))
    assert res["is_error"] is True and "while loop" in res["content"][0]["text"]
