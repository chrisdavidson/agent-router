#!/usr/bin/env python3
"""What did the agent keep doing that the router had no tool for? A gap report over past runs.

Offline. Reads the trace hooks' records (``<state>/trace/*.jsonl``) and the router's audit log
(``<state>/audit/*.jsonl``) from one or more state roots: by default the hooks' own
(``trace.state_root()``) and every saved run's (``runs/*/state``). Each thing the plugin's agent
did is put in one pattern by its construct (an interpreter script, a PDF, curl, a source that
came back without the content, ...), never by its text, and joined by ``tool_use_id`` to what the
router made of that call: skipped as not fitting any entry, skipped by a skip pattern, classified
as none, acted on, or never checked (the router does not see ``WebFetch`` / ``WebSearch``).

A pattern that is not housekeeping and recurs (``--min-calls`` calls in ``--min-sessions``
sessions) is a CANDIDATE: a tool worth considering for the catalog. Candidates are what the
next step stores and trials in shadow; this script only measures.

Counts and construct names only: no prompt or command text, no URLs and no host names (each
pattern keeps how many distinct hosts it touched, not which). ``--write`` writes
``TOOL-GAPS.md``; ``--json PATH`` writes the same figures for the candidate store.
Standard library only.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

# One pattern per call, tried in this order. ``noise``: work no catalog tool would take over
# (looking at files, housekeeping), counted so the router's quiet checkpoints are explained.
PATTERNS: dict[str, dict[str, Any]] = {
    "document_to_text": {
        "title": "Reading documents (PDF) as text",
        "need": "the text of a PDF or other document, to search or quote",
        "proposal": "a document-to-text tool: fetch a PDF or file and return its text",
        "noise": False,
    },
    "web_via_shell": {
        "title": "Fetching pages with curl / wget",
        "need": "a page's own text (WebFetch returns a small model's summary instead)",
        "proposal": "a raw fetch tool: the page's text, not a summary of it",
        "noise": False,
    },
    "compute_script": {
        "title": "Multi-step compute scripts",
        "need": "exact results from a short script (imports, loops, several printed values)",
        "proposal": "extend calc_script, or a sandboxed script runner",
        "noise": False,
    },
    "source_without_content": {
        "title": "Sources that came back without the content",
        "need": "the fact at its source when the page is blocked, gone or lacks it",
        "proposal": "a source fallback: an archived copy or an alternate source",
        "noise": False,
    },
    "repo_history": {
        "title": "Repository history and search (git, gh)",
        "need": "what a repository says or said at a version",
        "proposal": "a repository history / search tool",
        "noise": False,
    },
    "inspect_files": {
        "title": "Looking at files (ls, cat, grep, sed -n, ...)",
        "need": "",
        "proposal": "",
        "noise": True,
    },
    "housekeeping": {
        "title": "Housekeeping (date, echo, mkdir, cd, ...)",
        "need": "",
        "proposal": "",
        "noise": True,
    },
    "other_shell": {
        "title": "Other shell commands",
        "need": "",
        "proposal": "",
        "noise": True,
    },
}

_DOCUMENT = re.compile(r"\.pdf\b|\bpdftotext\b|\bpdfinfo\b|\bmutool\b|\bpandoc\b", re.I)
_WEB = re.compile(r"\b(?:curl|wget)\b")
_REPO = re.compile(r"(?:^|[\s;&|(])(?:git|gh)\s")
_CD = r"^\s*(?:cd\s+[^;&|]+(?:&&|;)\s*)?(?:[A-Z_]\w*=\S+\s*;?\s*)*"
_INSPECT = re.compile(
    _CD + r"(?:ls|find|cat|head|tail|grep|rg|wc|stat|file|sed\s+-n|cut|sort|uniq|diff|du|tree)\b"
)
_HOUSEKEEPING = re.compile(_CD + r"(?:date|pwd|echo|printf|mkdir|touch|rm|cp|mv|cd|true|sleep)\b")
TRACE_COMMAND_CHARS = 200  # trace.py keeps a shell command's first 200 characters
_URL_HOST = re.compile(r"https?://([A-Za-z0-9.-]+)")

# what the router made of a call, from its audit row (or the lack of one)
ROUTER_SEEN = [
    "acted on",
    "classified none",
    "did not fit",
    "skip pattern",
    "own tool",
    "not checked",
]


def load_trace() -> Any:
    spec = importlib.util.spec_from_file_location("fp_trace", HERE / "trace.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def shell_pattern(rec: dict[str, Any]) -> str:
    """The pattern of a shell call, by construct; the command is only matched, never kept."""
    cmd = str(rec.get("command") or "")
    if _DOCUMENT.search(cmd):
        return "document_to_text"
    if _WEB.search(cmd):
        return "web_via_shell"
    if rec.get("interpreter", rec.get("math")):  # traces before 2026-09-30: ``math``
        return "compute_script"
    if _REPO.search(cmd):
        return "repo_history"
    if _INSPECT.match(cmd):
        return "inspect_files"
    if _HOUSEKEEPING.match(cmd):
        return "housekeeping"
    return "other_shell"


def pattern_of(rec: dict[str, Any]) -> str | None:
    """The pattern of one trace record, or None for what is not a gap: the calculator (the
    catalog's own tool), the report, the plugin's references, a source that answered."""
    kind = rec.get("kind")
    was = rec.get("was") if kind == "tool_failed" else kind
    if was == "shell":
        return shell_pattern(rec)
    if was == "source":
        if _DOCUMENT.search(str(rec.get("target") or "")):
            return "document_to_text"
        if kind == "tool_failed" or rec.get("outcome") in ("reported_missing", "http_error"):
            return "source_without_content"
    return None


def _host_in(command: Any) -> str | None:
    """The first URL's host in a shell command (the host only; the command is not kept)."""
    text = str(command or "")
    m = _URL_HOST.search(text)
    if m is None or (m.end() == len(text) and len(text) >= TRACE_COMMAND_CHARS):
        return None  # cut off where the trace truncated the command: not a whole host
    return m.group(1).lower()


def router_seen(row: dict[str, Any] | None) -> str:
    if row is None:
        return "not checked"
    action, reason = row.get("action"), str(row.get("reason") or "")
    if action in ("suggest", "enforce", "gated"):
        return "acted on"
    if reason.startswith("does not fit"):
        return "did not fit"
    if reason == "skip pattern":
        return "skip pattern"
    if reason == "own tool":
        return "own tool"
    return "classified none"


def _read(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue  # a half-written last line
        if isinstance(rec, dict):
            out.append(rec)
    return out


def default_states() -> list[Path]:
    states = [load_trace().state_root()]
    states += sorted(p for p in (HERE / "runs").glob("*/state") if p.is_dir())
    return states


def scan(states: list[Path], min_calls: int = 5, min_sessions: int = 2) -> dict[str, Any]:
    audit: dict[str, dict[str, Any]] = {}  # tool_use_id -> the router's tool checkpoint
    checkpoints: Counter[tuple[str, str]] = Counter()
    seen_audit: set[tuple[Any, ...]] = set()
    for state in states:
        for path in sorted((state / "audit").glob("*.jsonl")):
            for row in _read(path):
                key = (row.get("session"), row.get("ts"), row.get("point"), row.get("tool_use_id"))
                if key in seen_audit:
                    continue
                seen_audit.add(key)
                checkpoints[(str(row.get("point")), router_seen(row))] += 1
                if row.get("point") == "tool" and row.get("tool_use_id"):
                    audit[str(row["tool_use_id"])] = row

    calls: dict[str, Counter[str]] = defaultdict(Counter)
    runs: dict[str, set[str]] = defaultdict(set)
    sessions: dict[str, set[str]] = defaultdict(set)
    hosts: dict[str, set[str]] = defaultdict(set)  # counted, never written out
    totals: Counter[str] = Counter()
    seen: set[tuple[Any, ...]] = set()
    all_runs: set[str] = set()
    all_sessions: set[str] = set()
    trace_files = 0
    for state in states:
        for path in sorted((state / "trace").glob("*.jsonl")):
            trace_files += 1
            for n, rec in enumerate(_read(path)):
                tid = rec.get("tool_use_id")
                key = (rec.get("session"), tid) if tid else (str(path), n)
                if key in seen:
                    continue  # the same call in two state roots (a copied run)
                seen.add(key)
                run = f"{rec.get('session')}/{rec['agent_id']}" if rec.get("agent_id") else None
                if run:  # replayed runs reuse ids like replay-1, so a run is session + agent
                    all_runs.add(run)
                if rec.get("session"):
                    all_sessions.add(str(rec["session"]))
                if rec.get("kind") == "calc":
                    totals["calculator calls"] += 1
                pat = pattern_of(rec)
                if pat is None:
                    continue
                c = calls[pat]
                c["calls"] += 1
                c["failed"] += rec.get("kind") == "tool_failed"
                c["router: " + router_seen(audit.get(str(tid)) if tid else None)] += 1
                if run:
                    runs[pat].add(run)
                if rec.get("session"):
                    sessions[pat].add(str(rec["session"]))
                host = rec.get("host") or _host_in(rec.get("command"))
                if host:
                    hosts[pat].add(str(host).lower())

    patterns = []
    for pid, meta in PATTERNS.items():
        c = calls.get(pid, Counter())
        n_sessions = len(sessions[pid])
        patterns.append(
            {
                "id": pid,
                "title": meta["title"],
                "need": meta["need"],
                "proposal": meta["proposal"],
                "noise": meta["noise"],
                "calls": c["calls"],
                "failed": c["failed"],
                "runs": len(runs[pid]),
                "sessions": n_sessions,
                "router": {k: c["router: " + k] for k in ROUTER_SEEN if c["router: " + k]},
                "hosts": len(hosts[pid]),  # distinct hosts: a count, not a list
                "candidate": not meta["noise"]
                and c["calls"] >= min_calls
                and n_sessions >= min_sessions,
            }
        )
    patterns.sort(key=lambda p: (p["noise"], not p["candidate"], -p["calls"]))
    return {
        "generated": datetime.now(UTC).date().isoformat(),
        "states": [str(s) for s in states],
        "trace_files": trace_files,
        "runs": len(all_runs),
        "sessions": len(all_sessions),
        "calculator_calls": totals["calculator calls"],
        "checkpoints": {f"{p} / {o}": n for (p, o), n in sorted(checkpoints.items())},
        "thresholds": {"min_calls": min_calls, "min_sessions": min_sessions},
        "patterns": patterns,
    }


def _router_cell(router: dict[str, int]) -> str:
    return ", ".join(f"{n} {k}" for k, n in router.items()) or "–"


def render(result: dict[str, Any]) -> str:
    th = result["thresholds"]
    candidates = [p for p in result["patterns"] if p["candidate"]]
    lines = [
        "# Tool gaps (offline measurement)",
        "",
        "Counts and construct names only; no prompt or command text, no URLs or host names.",
        "Regenerate with `python3 integrations/first-principles/tool_gaps.py --write`",
        "(or `make tool-gaps`).",
        f"Measured {result['generated']} over {result['trace_files']} trace files: "
        f"{result['runs']} agent runs in {result['sessions']} sessions, from the hooks' state and",
        "the saved runs (`runs/*/state`, untracked; a snapshot of this checkout's recordings, not",
        "reproducible from a fresh clone).",
        "",
        "## What the router's checkpoints did",
        "",
        "Every checkpoint in the audit logs, by where it fired and what the router made of it.",
        "",
        "| Checkpoint / outcome | Count |",
        "|---|---|",
    ]
    lines += [f"| {k} | {n} |" for k, n in result["checkpoints"].items()]
    lines += [
        "",
        f"The agents also used the catalog's calculator {result['calculator_calls']} times; that",
        "is covered, so it is not counted below.",
        "",
        "## What the agent kept doing",
        "",
        "One row per pattern; each call counts once, in the first pattern it matches. *Router* is",
        "what the router made of those calls: `did not fit` (checked, no catalog entry fits),",
        "`skip pattern`, `classified none`, `acted on`, or `not checked` (WebFetch / WebSearch",
        "are not routed, and older traces have no call id to join).",
        "",
        "| Pattern | Calls | Failed | Runs | Sessions | Router | Candidate |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in result["patterns"]:
        mark = "**yes**" if p["candidate"] else ("housekeeping" if p["noise"] else "no")
        lines.append(
            f"| {p['title']} | {p['calls']} | {p['failed']} | {p['runs']} | {p['sessions']} "
            f"| {_router_cell(p['router'])} | {mark} |"
        )
    lines += [
        "",
        f"A candidate is a pattern that is not housekeeping, with at least {th['min_calls']} calls",
        f"in at least {th['min_sessions']} sessions.",
        "",
        "## Candidates",
        "",
    ]
    if not candidates:
        lines += ["None at these thresholds.", ""]
    for p in candidates:
        lines += [
            f"### {p['title']}",
            "",
            f"- **Need:** {p['need']}.",
            f"- **Proposal:** {p['proposal']}.",
            f"- **Evidence:** {p['calls']} calls ({p['failed']} failed) in {p['runs']} runs and "
            f"{p['sessions']} sessions; router: {_router_cell(p['router'])}.",
        ]
        if p["hosts"]:
            lines.append(f"- **Distinct hosts:** {p['hosts']}.")
        lines.append("")
    lines += [
        "## Reading it",
        "",
        "A candidate is a need that recurs with no catalog entry to meet it, not a decision that",
        "a tool should be built. The next step stores candidates and lets the router classify",
        "against them in shadow (recorded, never shown to the agent), so how often each would",
        "have been the right call is measured before anything is added to the catalog.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--state",
        type=Path,
        action="append",
        help="a state root with trace/ and audit/ (repeatable; default: the hooks' state "
        "root and runs/*/state)",
    )
    ap.add_argument("--min-calls", type=int, default=5)
    ap.add_argument("--min-sessions", type=int, default=2)
    ap.add_argument("--write", action="store_true", help="write TOOL-GAPS.md")
    ap.add_argument("--json", type=Path, help="also write the figures as JSON to this path")
    args = ap.parse_args(argv)
    result = scan(args.state or default_states(), args.min_calls, args.min_sessions)
    if not result["trace_files"]:
        print("no trace files under the state roots' trace/ folders", file=sys.stderr)
        return 1
    text = render(result)
    print(text)
    if args.write:
        (HERE / "TOOL-GAPS.md").write_text(text, encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
