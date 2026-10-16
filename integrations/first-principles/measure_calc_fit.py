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
  relative. Directional on purpose: a real script's labels also contain digits.

Commands naming the plugin's report directory are the agent writing its report, which the router
never routes (the skip pattern); they are counted apart and left out of the rates.

``--write`` writes counts and method to ``CALC-SCRIPT-COVERAGE.md`` (no prompt or command text).
Standard library plus the router package.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from agent_router.core.fit import _script_candidate, calc_expression, calc_script  # noqa: E402
from agent_router.tools import calc  # noqa: E402

REL_TOL = 1e-6
ABS_TOL = 1e-9  # the calculator prints 10 decimals; below that a value is "0"
_NUMBER = re.compile(r"(?<![\w.])[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
# a calculator value, after "= ": "≈ 1.5", "7/2 (≈ 3.5)" or an integer
_VALUE = re.compile(r"= (?:≈ (-?\d+(?:\.\d+)?)|-?\d+/\d+ \(≈ (-?\d+(?:\.\d+)?)\)|(-?\d+))(?=, |$)")


def load_trace() -> Any:
    spec = importlib.util.spec_from_file_location("fp_trace", HERE / "trace.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def calc_values(output: str) -> list[float]:
    """The numeric values the calculator printed, one per expression."""
    out: list[float] = []
    for line in output.splitlines():
        for m in _VALUE.finditer(line):
            out.append(float(next(g for g in m.groups() if g is not None)))
    return out


def real_numbers(stdout: str) -> list[float]:
    out: list[float] = []
    for token in _NUMBER.findall(stdout):
        try:
            out.append(float(token))
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
        if re.match(r"\s*cd\s", command):
            return "shape: cd ... && prefix"
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


def scan(runs_dir: Path) -> dict[str, Any]:
    tr = load_trace()
    captures = sorted(runs_dir.glob("*/*/run.jsonl"))
    seen: set[tuple[str, str]] = set()
    stats: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    errors: list[float] = []
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
            by_expr = calc_expression(inp)
            by_script = calc_script(inp)
            stats["accepted by calc_expression"] += by_expr
            stats["accepted by calc_script"] += by_script
            stats["accepted by either"] += by_expr or by_script
            if not (by_expr or by_script):
                reasons[reject_reason(command)] += 1
            if not by_script:
                continue
            script = _script_candidate(command) or ""
            ours = calc_values(calc.evaluate_script(script))
            real_out = stdout_of(payload, tr)
            if real_out is None:
                stats["calc_script accepted, call failed (no result to compare)"] += 1
                continue
            if not ours:
                stats["calc_script accepted, no numeric value printed"] += 1
                continue
            ok, found = agreement(ours, real_numbers(real_out))
            stats["agreement: compared"] += 1
            stats["agreement: agree"] += ok
            stats["agreement: values compared"] += len(ours)
            stats["agreement: values found"] += found
            if not ok:
                disagree.append(f"{capture.parent.name}: {found}/{len(ours)} values found")
    return {
        "captures": len(captures),
        "stats": stats,
        "reasons": reasons,
        "disagree": disagree,
        "errors": errors,
    }


def pct(n: int, d: int) -> str:
    return f"{n} ({100 * n / d:.0f}%)" if d else f"{n} (n/a)"


def row(label: str, value: Any) -> str:
    return f"| {label} | {value} |"


def render(result: dict[str, Any], runs_dir: Path) -> str:
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
        "   `calc.evaluate_script` runs the script; each number it prints must be found among the",
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
    args = ap.parse_args(argv)
    result = scan(args.runs_dir)
    if not result["captures"]:
        print(f"no captures under {args.runs_dir}/*/*/run.jsonl", file=sys.stderr)
        return 1
    text = render(result, args.runs_dir)
    print(text)
    if args.write:
        (HERE / "CALC-SCRIPT-COVERAGE.md").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
