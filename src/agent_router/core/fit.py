"""Named fit checks: can a catalog entry actually do the pending call?

The decider scores how much a pending call *looks like* an entry's examples; a fit check asks
whether the entry could *run* it. An entry names its check in the catalog (``fits:``); only
names registered here are accepted, so a catalog never carries code.

``calc_expression``: the exact calculator fits a shell call only when the call is one
arithmetic expression the calculator evaluates (``python3 -c "print(...)"``, ``echo ... | bc``,
``awk 'BEGIN { print ... }'``, ``node -e "console.log(...)"``, ``expr``, ``$((...))``).
``calc_script``: the same calculator, run as a script, fits a shell call that is a python
heredoc (``python3 - <<'EOF'``, ``python3 <<EOF``, ``cat <<EOF | python3``) or a multi-statement
``python3 -c`` whose body ``calc.evaluate_script`` runs without error (assignments, ``print``,
``math.log``; no loops, I/O or imports other than math). A call ``calc_expression`` fits is not
also a ``calc_script`` fit, so the two entries never compete for one call.

Measured in the first-principles runs: all 16 calculator notes inside the agent fired on 3-36
line scripts (variables, loops, ``math.log``, ``scipy``) or on text commands, none of which
the calculator can run, and each spent the run's one note.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Callable, Mapping
from typing import Any

from agent_router.tools import calc

_IMPORTS = r"(?:\s*(?:import\s+[\w.]+(?:\s*,\s*[\w.]+)*|from\s+[\w.]+\s+import\s+[\w, ]+)\s*;)*"
_PY = re.compile(
    rf"""^\s*python[0-9.]*\s+-c\s+(['"])({_IMPORTS})\s*print\((?P<expr>.*)\)\s*;?\s*\1\s*$""",
    re.S,
)
_NODE = re.compile(r"""^\s*node\s+-e\s+(['"])\s*console\.log\((?P<expr>.*)\)\s*;?\s*\1\s*$""", re.S)
_AWK = re.compile(
    r"""^\s*awk\s+(['"])\s*BEGIN\s*\{\s*print\s+(?P<expr>[^;{}]*?)\s*;?\s*\}\s*\1\s*$""", re.S
)
_BC = re.compile(
    r"""^\s*echo\s+(['"])(?:\s*scale\s*=\s*\d+\s*;)?(?P<expr>[^;]*?)\1\s*\|\s*bc(?:\s+-l)?\s*$"""
)
_ARITH = re.compile(r"""^\s*echo\s+["']?\$\(\((?P<expr>.*)\)\)["']?\s*$""")
_EXPR = re.compile(r"^\s*expr\s+(?P<args>.+)$")
_MODULE = re.compile(r"\bmath\.")


def _candidate(command: str) -> str | None:
    """The single arithmetic expression a shell command computes, or None."""
    if "\n" in command.strip() or "<<" in command:
        return None
    for pattern in (_PY, _NODE, _AWK, _BC, _ARITH):
        m = pattern.match(command)
        if m:
            return _MODULE.sub("", m.group("expr"))
    m = _EXPR.match(command)
    if m:
        try:
            return " ".join(shlex.split(m.group("args")))
        except ValueError:
            return None
    return None


_PYTHON = r"python[0-9.]*"
_HEREDOC_PY = re.compile(
    rf"""^\s*{_PYTHON}(?:\s+-)?\s*<<-?[ \t]*(?P<q>['"]?)(?P<tag>\w+)(?P=q)[ \t]*\n"""
    r"""(?P<body>.*?)\n[ \t]*(?P=tag)[ \t]*\n?\s*$""",
    re.S,
)
_HEREDOC_CAT = re.compile(
    rf"""^\s*cat\s+<<-?[ \t]*(?P<q>['"]?)(?P<tag>\w+)(?P=q)[ \t]*\|"""
    rf"""[ \t]*{_PYTHON}(?:[ \t]+-)?[ \t]*\n"""
    r"""(?P<body>.*?)\n[ \t]*(?P=tag)[ \t]*\n?\s*$""",
    re.S,
)
_PY_C = re.compile(rf"""^\s*{_PYTHON}\s+-c\s+(?P<q>['"])""")


def _script_candidate(command: str) -> str | None:
    """The python script a shell command runs (heredoc or ``-c``), or None."""
    for pattern in (_HEREDOC_PY, _HEREDOC_CAT):
        m = pattern.match(command)
        if m:
            if m.group("q") == "" and re.search(r"[$`\\]", m.group("body")):
                return None  # an unquoted heredoc is shell-expanded before python sees it
            return m.group("body")
    m = _PY_C.match(command)
    if m:
        try:
            words = shlex.split(command)
        except ValueError:
            return None
        if len(words) != 3 or words[1] != "-c":
            return None
        if m.group("q") == '"' and re.search(r"[$`]", words[2]):
            return None
        return words[2]
    return None


def calc_script(tool_input: Mapping[str, Any]) -> bool:
    """True when the pending Bash call is a python script the exact calculator runs."""
    command = str(tool_input.get("command") or "")
    if calc_expression(tool_input):
        return False
    script = _script_candidate(command)
    if not script:
        return False
    try:
        calc.evaluate_script(script)
    except ValueError:
        return False
    return True


def calc_expression(tool_input: Mapping[str, Any]) -> bool:
    """True when the pending Bash call is one expression the exact calculator evaluates."""
    expr = _candidate(str(tool_input.get("command") or ""))
    if not expr:
        return False
    try:
        calc.evaluate(expr)
    except ValueError:
        return False
    return True


FITS: dict[str, Callable[[Mapping[str, Any]], bool]] = {
    "calc_expression": calc_expression,
    "calc_script": calc_script,
}
