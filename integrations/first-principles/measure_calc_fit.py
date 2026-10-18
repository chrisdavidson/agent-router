#!/usr/bin/env python3
"""How many of the agent's interpreter calls could the calculator have run, and does it agree?

Offline. Reads the local run captures (``runs/*/*/run.jsonl``, untracked) through
``trace.replay_payloads``, takes every Bash call the integrated plugin's agent made that runs an
interpreter (``trace.INTERPRETER``), and reports:

* the total;
* how many the router's ``calc_expression`` fit check accepts (one expression);
* how many ``calc_script`` accepts (a python script ``calc.evaluate_script`` runs);
* for the ``calc_script``-accepted calls, AGREEMENT: every number the calculator prints is found
  among the numbers the real interpreter printed (the call's recorded result), within 1e-6
  relative. Directional on purpose: a real script's labels also contain digits;
* how many calls are PLAIN ARITHMETIC (``is_arithmetic``: the whole call is a python script or
  an awk ``BEGIN`` program that reads no file, input or network and imports only ``math`` or
  ``fractions``), and how many of those the calculator takes.

The same figures are then taken over the TRACE: the tool-gap report's compute-script calls
(``tool_gaps.py``), each joined by tool_use_id to its full text in a capture or the agent's
Claude Code transcript (a call cut off in the trace with no transcript left is counted apart).

Commands naming the plugin's report directory are the agent writing its report, which the router
never routes (the skip pattern); they are counted apart and left out of the rates.

``--write`` writes counts and method to ``CALC-SCRIPT-COVERAGE.md`` (no prompt or command text).
Standard library plus the router package.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from agent_router.core.fit import _CD, _script_candidate, calc_expression, calc_script  # noqa: E402
from agent_router.tools import calc  # noqa: E402
from agent_router.tools import calc_script as script_form  # noqa: E402

# plain arithmetic: one python script (heredoc, -c, or written then run) or an awk BEGIN program,
# nothing else in the call; no file, input, network or module other than math / fractions
_IO_CALLS = frozenset({"open", "input", "exec", "eval", "__import__", "compile"})
_PURE_MODULES = frozenset({"math", "fractions"})

REL_TOL = 1e-6
ABS_TOL = 1e-9  # the calculator prints 10 decimals; below that a value is "0"
# a number in the real output: digit-grouped ("35,149") or plain; a letter before it is allowed,
# because f-string labels run into their values ("3x1", "K5")
_NUMBER = re.compile(
    r"(?<![\d.,])[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\d,])|\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
)


def load_trace() -> Any:
    spec = importlib.util.spec_from_file_location("fp_trace", HERE / "trace.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_FRACTION = re.compile(r"(?<![\w.,/])(-?\d+)/(\d+)(?![\w./])")


def real_numbers(stdout: str) -> list[float]:
    """Every number in the real output; a printed ``Fraction`` (``3/1360``) also counts as its
    value."""
    out = [int(a) / int(b) for a, b in _FRACTION.findall(stdout) if int(b)]
    for token in _NUMBER.findall(stdout):
        try:
            out.append(float(token.replace(",", "")))
        except ValueError:
            continue
    return out


def close(a: float, b: float) -> bool:
    return abs(a - b) <= max(ABS_TOL, REL_TOL * max(abs(a), abs(b)))


def agreement(ours: list[float], real: list[float]) -> tuple[bool, int]:
    """Whether each calculator value is found among the real numbers (each real number used at
    most once), and how many were found."""
    pool = list(real)
    found = 0
    for value in ours:
        hit = next((i for i, r in enumerate(pool) if close(value, r)), None)
        if hit is not None:
            pool.pop(hit)
            found += 1
    return found == len(ours), found


def stdout_of(payload: dict[str, Any], tr: Any) -> str | None:
    if payload.get("hook_event_name") != "PostToolUse":
        return None
    resp = payload.get("tool_response")
    return tr._text_of(resp.get("stdout") if isinstance(resp, dict) else resp)


def reject_reason(command: str) -> str:
    """Why ``calc_script`` refuses a call, as a construct name only (never command text)."""
    script = _script_candidate(command)
    if script is None:
        command = _CD.sub("", command, count=1)
        if re.match(r"\s*(awk|bc|dc|expr|node)\b", command):
            return "shape: awk/bc/dc/expr/node"
        if re.search(r"\bpython[0-9.]*\b", command):
            return "shape: python, not a heredoc or -c script"
        return "shape: other shell command"
    try:
        calc.evaluate_script(script)
    except ValueError as exc:
        msg = re.sub(r"^line \d+: ", "", str(exc))
        return "script: " + re.sub(r"'[^']*'", "'X'", msg)[:70]
    return "script: accepted by evaluate_script but refused by the fit check"


def is_arithmetic(command: str) -> bool:
    """Whether a call is plain arithmetic: the shape parser finds one script in it (the
    whole call), and that script reads nothing and imports only math or fractions."""
    script = _script_candidate(command)
    if script is None:
        return False
    try:
        tree = ast.parse(script)
    except (SyntaxError, ValueError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            a.name.split(".")[0] not in _PURE_MODULES for a in node.names
        ):
            return False
        if isinstance(node, ast.ImportFrom) and (node.module or "") not in _PURE_MODULES:
            return False
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) in _IO_CALLS:
            return False
    return True


def classify(
    command: str,
    real_out: str | None,
    stats: Counter[str],
    reasons: Counter[str],
    label: str,
    disagree: list[str],
) -> None:
    """Apply both fit checks to one call and, when ``calc_script`` takes it, compare the
    calculator's values with the call's recorded output. Counts only."""
    inp = {"command": command}
    by_expr = calc_expression(inp)
    by_script = calc_script(inp)
    if by_expr or is_arithmetic(command):
        stats["plain arithmetic"] += 1
        stats["plain arithmetic accepted"] += by_expr or by_script
    stats["accepted by calc_expression"] += by_expr
    stats["accepted by calc_script"] += by_script
    stats["accepted by either"] += by_expr or by_script
    if not (by_expr or by_script):
        reasons[reject_reason(command)] += 1
    if not by_script:
        return
    ours = script_form.run(_script_candidate(command) or "").values
    if real_out is None:
        stats["calc_script accepted, call failed (no result to compare)"] += 1
        return
    if not ours:
        stats["calc_script accepted, no numeric value printed"] += 1
        return
    ok, found = agreement(ours, real_numbers(real_out))
    stats["agreement: compared"] += 1
    stats["agreement: agree"] += ok
    stats["agreement: values compared"] += len(ours)
    stats["agreement: values found"] += found
    if not ok:
        disagree.append(f"{label}: {found}/{len(ours)} values found")


def captured_calls(runs_dir: Path, tr: Any) -> dict[str, tuple[str, str | None]]:
    """tool_use_id -> (full command, recorded stdout or None) for every Bash call in a capture."""
    out: dict[str, tuple[str, str | None]] = {}
    for capture in sorted(runs_dir.glob("*/*/run.jsonl")):
        for payload, _ts in tr.replay_payloads(capture):
            if payload.get("tool_name") != "Bash" or not payload.get("tool_use_id"):
                continue
            command = str((payload.get("tool_input") or {}).get("command") or "")
            out[str(payload["tool_use_id"])] = (command, stdout_of(payload, tr))
    return out


def scan(runs_dir: Path) -> dict[str, Any]:
    tr = load_trace()
    captures = sorted(runs_dir.glob("*/*/run.jsonl"))
    seen: set[tuple[str, str]] = set()
    stats: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    disagree: list[str] = []
    for capture in captures:
        for payload, _ts in tr.replay_payloads(capture):
            if payload.get("tool_name") != "Bash":
                continue
            inp = payload.get("tool_input") or {}
            command = str(inp.get("command") or "")
            if not tr.INTERPRETER.search(command):
                continue
            key = (str(payload.get("session_id")), str(payload.get("tool_use_id")))
            if key in seen:
                stats["duplicate calls dropped"] += 1
                continue
            seen.add(key)
            if tr.REPORT_DIR.search(command):
                stats["report commands (never routed, excluded)"] += 1
                continue
            stats["interpreter calls"] += 1
            if payload.get("hook_event_name") == "PostToolUseFailure":
                stats["interpreter calls that failed"] += 1
            classify(command, stdout_of(payload, tr), stats, reasons, capture.parent.name, disagree)
    return {"captures": len(captures), "stats": stats, "reasons": reasons, "disagree": disagree}


def _transcript_call(tid: str, session: str, agent_id: str, hints: list[str]) -> Any:
    """(command, stdout) of one Bash call in the agent's Claude Code transcript, or None."""
    from agent_router.demo import why

    path = why.find_transcript(session, agent_id, hints)
    if path is None:
        return None
    command, stdout = None, None
    for rec in why.read_transcript(path):
        content = (rec.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("id") == tid:
                command = str((block.get("input") or {}).get("command") or "")
            if block.get("type") == "tool_result" and block.get("tool_use_id") == tid:
                result = rec.get("toolUseResult")
                if isinstance(result, dict) and isinstance(result.get("stdout"), str):
                    stdout = result["stdout"]
                elif not block.get("is_error"):
                    stdout = why._text(block.get("content"))
    return None if command is None else (command, stdout)


def scan_traces(runs_dir: Path) -> dict[str, Any]:
    """The gap report's compute-script calls (``tool_gaps.py``'s ``compute_script`` pattern over
    the same state roots), each joined by tool_use_id to its full text: a run capture, else the
    agent's Claude Code transcript, else the trace's own command when it was not cut off."""
    tr = load_trace()
    spec = importlib.util.spec_from_file_location("fp_tool_gaps", HERE / "tool_gaps.py")
    assert spec and spec.loader
    gaps = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gaps)
    captured = captured_calls(runs_dir, tr)
    stats: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    disagree: list[str] = []
    seen: set[tuple[Any, ...]] = set()
    for state in gaps.default_states():
        for path in sorted((state / "trace").glob("*.jsonl")):
            for n, rec in enumerate(gaps._read(path)):
                tid = rec.get("tool_use_id")
                key = (rec.get("session"), tid) if tid else (str(path), n)
                if key in seen or gaps.pattern_of(rec) != "compute_script":
                    continue
                seen.add(key)
                stats["compute-script calls"] += 1
                full = captured.get(str(tid)) if tid else None
                source = "capture"
                if full is None and tid and rec.get("session") and rec.get("agent_id"):
                    hints = [str(rec[k]) for k in ("transcript", "transcript_path") if rec.get(k)]
                    full = _transcript_call(
                        str(tid), str(rec["session"]), str(rec["agent_id"]), hints
                    )
                    source = "transcript"
                if full is None:
                    command = str(rec.get("command") or "")
                    if len(command) >= gaps.TRACE_COMMAND_CHARS:
                        stats["full text gone (cut off in the trace, no transcript)"] += 1
                        continue
                    full, source = (command, None), "trace"
                stats[f"full text from: {source}"] += 1
                if rec.get("kind") == "tool_failed":
                    stats["calls that failed"] += 1
                command, stdout = full
                if rec.get("kind") == "tool_failed":
                    stdout = None
                stats["with full text"] += 1
                classify(command, stdout, stats, reasons, str(rec.get("session"))[:8], disagree)
    return {"stats": stats, "reasons": reasons, "disagree": disagree}


def pct(n: int, d: int) -> str:
    return f"{n} ({100 * n / d:.0f}%)" if d else f"{n} (n/a)"


def row(label: str, value: Any) -> str:
    return f"| {label} | {value} |"


def render_traces(t: dict[str, Any]) -> list[str]:
    s = t["stats"]
    full = s["with full text"]
    compared = s["agreement: compared"]
    lines = [
        "",
        "## Over the trace: the tool-gap report's compute-script calls",
        "",
        "The population `tool_gaps.py` reports as *Multi-step compute scripts*, from the hooks'",
        "state and every saved run's. Each call's full text comes from a capture, else the",
        "agent's Claude Code transcript, else the trace's own command when it was not cut off",
        "at 200 characters.",
        "",
        "| Measure | Calls |",
        "|---|---|",
        row("compute-script calls in the trace", s["compute-script calls"]),
        row("full text found", full),
        row("  from a capture", s["full text from: capture"]),
        row("  from a Claude Code transcript", s["full text from: transcript"]),
        row("  the trace's own (not cut off)", s["full text from: trace"]),
        row(
            "full text gone (cut off, no transcript)",
            s["full text gone (cut off in the trace, no transcript)"],
        ),
        row("accepted by either fit check", pct(s["accepted by either"], full)),
        row("plain arithmetic", s["plain arithmetic"]),
        row(
            "plain arithmetic accepted",
            pct(s["plain arithmetic accepted"], s["plain arithmetic"]),
        ),
        row("agreement: calls compared / agree", f"{compared} / {s['agreement: agree']}"),
        row(
            "agreement: values compared / found",
            f"{s['agreement: values compared']} / {s['agreement: values found']}",
        ),
        "",
        "| Why the other calls are refused (by both) | Calls |",
        "|---|---|",
    ]
    lines += [f"| {reason} | {n} |" for reason, n in t["reasons"].most_common()]
    return lines


def render(result: dict[str, Any], runs_dir: Path, traces: dict[str, Any] | None = None) -> str:
    s = result["stats"]
    total = s["interpreter calls"]
    compared = s["agreement: compared"]
    lines = [
        "# calc_script coverage (offline measurement)",
        "",
        "Counts only; no prompt or command text. Regenerate with",
        "`python3 integrations/first-principles/measure_calc_fit.py --write`.",
        f"Measured {datetime.now(UTC).date().isoformat()} over {result['captures']} local captures",
        "(`runs/*/*/run.jsonl`, untracked; they are not in the repository, so the figures are a",
        "snapshot of this checkout's recordings, not reproducible from a fresh clone).",
        "",
        "## Method",
        "",
        "1. `trace.replay_payloads` rebuilds the hook payloads of the plugin's agent from",
        "   each capture. A call is every Bash call whose command matches `trace.INTERPRETER`.",
        "   Commands naming the plugin's report directory are the agent writing its report; the",
        "   router never routes them, so they are counted apart and left out of the rates. Calls",
        "   repeated across captures (same session and tool-use id) are counted once.",
        "2. `calc_expression` and `calc_script` (`core/fit.py`) are applied to each call's input,",
        "   as the router's fit check does. They never both accept one call.",
        "3. AGREEMENT, for calls `calc_script` accepts and whose real result was recorded:",
        "   `calc_script.run` runs the script; each number it shows (a `<source> = <value>`",
        "   value, a list item, an f-string field as formatted) must be found among the",
        f"   numbers in the recorded stdout of the real call, within {REL_TOL:g} relative",
        f"   ({ABS_TOL:g} absolute), each real number used at most once. The check is directional",
        "   because the real output's labels also contain digits. A call whose script prints no",
        "   number the calculator can show, and a call that failed, are not compared.",
        "",
        "## Result",
        "",
        "| Measure | Calls |",
        "|---|---|",
        f"| interpreter calls (excluding report commands) | {total} |",
        row(
            "accepted by `calc_expression` (one expression)",
            pct(s["accepted by calc_expression"], total),
        ),
        row("accepted by `calc_script`", pct(s["accepted by calc_script"], total)),
        row("accepted by either", pct(s["accepted by either"], total)),
        row("refused by both", pct(total - s["accepted by either"], total)),
        row("plain arithmetic (see Method)", s["plain arithmetic"]),
        row(
            "plain arithmetic accepted",
            pct(s["plain arithmetic accepted"], s["plain arithmetic"]),
        ),
        row("failed calls among the interpreter calls", s["interpreter calls that failed"]),
        row("report commands excluded", s["report commands (never routed, excluded)"]),
        row("duplicate calls dropped", s["duplicate calls dropped"]),
        "",
        "### Agreement on the `calc_script`-accepted calls",
        "",
        "| Measure | Count |",
        "|---|---|",
        row("compared", compared),
        row(
            "agree (every calculator value found in the real output)",
            pct(s["agreement: agree"], compared),
        ),
        row(
            "values compared / found",
            f"{s['agreement: values compared']} / {s['agreement: values found']}",
        ),
        row(
            "accepted but the call failed",
            s["calc_script accepted, call failed (no result to compare)"],
        ),
        row(
            "accepted but no numeric value printed",
            s["calc_script accepted, no numeric value printed"],
        ),
        "",
        "### Why the other calls are refused (by both)",
        "",
        "| Reason | Calls |",
        "|---|---|",
    ]
    lines += [f"| {reason} | {n} |" for reason, n in result["reasons"].most_common()]
    if result["disagree"]:
        lines += ["", "### Disagreements", ""] + [f"- {d}" for d in result["disagree"]]
    if traces is not None:
        lines += render_traces(traces)
    lines += [
        "",
        "## Reading it",
        "",
        "Acceptance is what the router can offer; agreement is whether following the note would",
        "have produced the same figures. A disagreement is a calculator-vs-float difference or a",
        "script the real interpreter treated differently (integer division, rounding), not a",
        "decision the router made.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--runs-dir", type=Path, default=HERE / "runs")
    ap.add_argument("--write", action="store_true", help="write CALC-SCRIPT-COVERAGE.md")
    ap.add_argument(
        "--no-traces", action="store_true", help="captures only: skip the trace population"
    )
    args = ap.parse_args(argv)
    result = scan(args.runs_dir)
    if not result["captures"]:
        print(f"no captures under {args.runs_dir}/*/*/run.jsonl", file=sys.stderr)
        return 1
    traces = None if args.no_traces else scan_traces(args.runs_dir)
    text = render(result, args.runs_dir, traces)
    print(text)
    if args.write:
        (HERE / "CALC-SCRIPT-COVERAGE.md").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
