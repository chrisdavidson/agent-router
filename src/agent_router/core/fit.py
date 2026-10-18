"""Named fit checks: can a catalog entry actually do the pending call?

The decider scores how much a pending call *looks like* an entry's examples; a fit check asks
whether the entry could *run* it. An entry names its check in the catalog (``fits:``); only
names registered here are accepted, so a catalog never carries code.

``calc_expression``: the exact calculator fits a shell call only when the call is one
arithmetic expression the calculator evaluates (``python3 -c "print(...)"``, ``echo ... | bc``,
``awk 'BEGIN { print ... }'``, ``node -e "console.log(...)"``, ``expr``, ``$((...))``).
``calc_script``: the same calculator, run as a script, fits a shell call that is a python
heredoc (``python3 - <<'EOF'``, ``python3 <<EOF``, ``cat <<EOF | python3``), a ``python3 -c``
script, a script written with ``cat > x.py <<'EOF'`` and then run with ``python3 x.py``, or an
``awk 'BEGIN{...}'`` program (translated by ``tools/awk_begin.py``), optionally after
``cd DIR &&`` and with ``2>&1``, whose body ``calc.evaluate_script`` runs
without error (loops, lists, small functions, f-strings, ``math``; no I/O or other imports). A
call ``calc_expression`` fits is not also a ``calc_script`` fit, so the two entries never compete
for one call.

``reads_pdf``: the document-text tool fits a call that reads a PDF: a ``WebFetch`` of a ``.pdf``
link, or a shell call running ``pdftotext`` / ``pdfinfo`` / ``mutool``, or downloading or
converting a ``.pdf`` with ``curl``, ``wget`` or ``pandoc``.

Measured in the first-principles runs: all 16 calculator notes inside the agent fired on 3-36
line scripts (variables, loops, ``math.log``, ``scipy``) or on text commands, none of which
the calculator can run, and each spent the run's one note.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Callable, Mapping
from typing import Any

from agent_router.tools import awk_begin, calc
from agent_router.tools import calc_script as calc_script_form

# The fit check runs the script inside the router's hook, before the call it judges: a script
# the calculator needs longer than this to run is not offered (the tool itself allows 10 s).
FIT_SECONDS = 0.25

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
# write a script to a file, then run that file: ``cat > /tmp/x.py <<'EOF' ... EOF`` and then
# ``python3 /tmp/x.py`` (on the next line or after ``&&`` / ``;``), optionally in a fresh
# ``mkdir -p`` directory. ``cat >>`` (appending to an earlier file) is not this shape.
_WRITE_RUN = re.compile(
    r"""^\s*(?:mkdir\s+-p\s+\S+\s*(?:&&|;)\s*)?"""
    r"""cat\s+(?:>\s*(?P<f1>[\w./-]+\.py)\s+<<-?[ \t]*(?P<q1>['"]?)(?P<t1>\w+)(?P=q1)"""
    r"""|<<-?[ \t]*(?P<q2>['"]?)(?P<t2>\w+)(?P=q2)\s*>\s*(?P<f2>[\w./-]+\.py))[ \t]*\n"""
    r"""(?P<body>.*?)\n[ \t]*(?P<tag>\w+)[ \t]*\n?\s*(?:&&|;)?\s*"""
    rf"""{_PYTHON}\s+(?P<run>[\w./-]+\.py)\s*$""",
    re.S,
)
# a leading ``cd DIR &&`` (or ``;``) and a trailing ``2>&1``: neither changes what the script
# computes, and the calculator reads no files
_CD = re.compile(r"""^\s*cd\s+(?:"[^"]*"|'[^']*'|[^\s;&|'"]+)\s*(?:&&|;)\s*""")
_STDERR = re.compile(r"[ \t]+2>&1(?=[ \t]*(?:\n|$))")
# an awk program with only a BEGIN block, single-quoted: translated (awk_begin) and run as a script
_AWK_BEGIN = re.compile(r"""^\s*awk\s+'(?P<prog>\s*BEGIN\s*\{[^']*\})\s*'\s*$""")


def _write_run(command: str) -> str | None:
    m = _WRITE_RUN.match(command)
    if m is None:
        return None
    path = m.group("f1") or m.group("f2")
    tag = m.group("t1") or m.group("t2")
    quoted = m.group("q1") if m.group("t1") else m.group("q2")
    if m.group("tag") != tag or m.group("run") != path:
        return None
    if not quoted and re.search(r"[$`\\]", m.group("body")):
        return None  # an unquoted heredoc is shell-expanded before python sees it
    return m.group("body")


def _script_candidate(command: str) -> str | None:
    """The python script a shell command runs (heredoc, ``-c`` or a file it has just written),
    or None. A leading ``cd DIR &&`` and a ``2>&1`` are ignored."""
    command = _STDERR.sub("", _CD.sub("", command, count=1))
    script = _write_run(command)
    if script is not None:
        return script
    m = _AWK_BEGIN.match(command)
    if m:
        return awk_begin.translate(m.group("prog"))
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
        calc_script_form.run(script, max_seconds=FIT_SECONDS)
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


# a PDF, by its name or the tools that read one; ".pdf" must end a path segment
_PDF_NAME = re.compile(r"""\.pdf(?=$|[\s'"?#&;|)>])""", re.I)
_PDF_TOOLS = re.compile(r"(?:^|[\s;&|(])(?:pdftotext|pdfinfo|pdftohtml|mutool)\b")


def reads_pdf(tool_input: Mapping[str, Any]) -> bool:
    """True when the pending call reads a PDF: a ``WebFetch`` of a ``.pdf`` link, or a shell call
    that runs ``pdftotext`` (or ``pdfinfo``, ``mutool``) or names a ``.pdf`` file it downloads
    or converts. ``document_text`` returns that PDF's own text."""
    url = tool_input.get("url")
    if isinstance(url, str) and url:
        path = re.sub(r"[?#].*$", "", url)
        return bool(re.match(r"https?://", url, re.I)) and path.lower().endswith(".pdf")
    command = str(tool_input.get("command") or "")
    if not command:
        return False
    if _PDF_TOOLS.search(command):
        return True
    if re.search(r"\b(?:curl|wget)\b", command) and _PDF_NAME.search(command):
        return True
    # pandoc reading a PDF, not writing one (``-o report.pdf`` is the report being rendered)
    inputs = re.sub(r"(?:-o|--output)(?:\s+|=)\S+", " ", command)
    return bool(re.search(r"\bpandoc\b", inputs)) and bool(_PDF_NAME.search(inputs))


FITS: dict[str, Callable[[Mapping[str, Any]], bool]] = {
    "calc_expression": calc_expression,
    "calc_script": calc_script,
    "reads_pdf": reads_pdf,
}
