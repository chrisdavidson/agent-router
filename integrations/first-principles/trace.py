#!/usr/bin/env python3
"""Record what the first-principles agent decides as it moves through an analysis.

A Claude Code command hook for ``agent-router-fp``. Record-only: it
always prints ``{}``, so it can never steer the agent. Standard library only, so it starts in
milliseconds. It sees only the first-principles agent (``plugin/bin/trace`` drops everything
else) and appends one record per event to ``<state dir>/trace/<session>.jsonl``, next to the
router's ``audit/<session>.jsonl``:

  run_start        SubagentStart
  reference_read   Read of a first-principles reference file, with what that read means
  section_written  a ``cat >> .first-principles/analysis-*.md`` append: the headings written
  report_op        any other report-file command: ``op`` = create, revise (the agent
                   rewrites part of its report in place) or check
  calc             a call to the exact calculator: expression and result
  shell            any other Bash call (``math`` when it computes a figure)
  tool_failed      PostToolUseFailure
  run_end          SubagentStop: duration, final message, the analysis file parsed into its
                   decisions, and the router's decisions linked to the run

Usage:
    trace.py                          hook payload on stdin, prints {}
    trace.py --replay RUN.jsonl       feed a ``claude -p`` stream-json capture through the
             [--state DIR]            same handler (offline check; writes DIR/trace/)
    trace.py --report TRACE_DIR       one Markdown row per finished run: what it decided
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

AGENT = "first-principles:first-principles"
CALC_TOOL = "mcp__plugin_agent-router-fp_agent_router__calc"
MAX_TEXT = 300

REPORT_DIR = re.compile(r"\.first-principles(?:/|[\s\"';&)]|$)")
REPORT_PATH = re.compile(r"""[^\s"'<>|;&=]*\.first-principles/analysis-[^\s"'<>|;&=]+\.md""")
APPEND = re.compile(r">>\s*\S*\.first-principles/|>>\s*\"?\$")
HEADING = re.compile(r"^(#{1,3}) (.+)$", re.M)
RESTART = re.compile(r"""(?:^|[;&\n])\s*:\s*>\s*["']?[$\w./]""")  # `: > "$F"` empties the report
REVISE = re.compile(r"\bsed -i|\bperl -\w*i|\.write\(|write_text\(|open\([^)]*['\"][wa]")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)\n\2[ \t]*$", re.S | re.M)
MATH = re.compile(r"\bpython3?\b|\bbc\b|\bawk\b|\bnode -e\b|\bexpr\b|\bdc\b")

# What reading each reference file tells us (agent definition, first-principles 9.13.0).
REFERENCES = {
    "output-template.md": "report assembly starts",
    "validation-rubric.md": "Self-Audit Gate scoring starts",
    "trade-off.md": "trade-off: two or more options survived (Phase 4)",
    "pre-mortem.md": "adversarial pass on a plan (Phase 5)",
    "inversion.md": "adversarial pass on a claim (Phase 5)",
    "assumption-taxonomy.md": "assumption typing (Phase 2)",
    "fishbone-detail.md": "fishbone worked example (Phase 2)",
    "five-whys-detail.md": "reduce-to-primitives worked example (Phase 3)",
    "estimate-detail.md": "estimate worked example (Phase 4)",
    "theoretical-limit-detail.md": "theoretical-limit worked example",
}
ASSUMPTION_TYPES = ("physical law", "current constraint", "convention", "untested belief")
BANDS = ("Rigorous", "Sound", "Hand-wavy", "Absent")


# --- state ----------------------------------------------------------------------------------


def state_root() -> Path:
    """Same rule as the router's hook: $AGENT_ROUTER_STATE_DIR, else XDG state."""
    env = os.environ
    if env.get("AGENT_ROUTER_STATE_DIR", "").strip():
        return Path(env["AGENT_ROUTER_STATE_DIR"].strip())
    base = env.get("XDG_STATE_HOME", "").strip() or str(Path.home() / ".local" / "state")
    return Path(base) / "agent-router"


def _safe(session: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", session)[:128] or "unknown"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _when(ts: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def _trunc(text: Any, n: int = MAX_TEXT) -> str:
    return str(text or "")[:n]


# --- the analysis file ----------------------------------------------------------------------


def _section(text: str, number: int) -> str:
    m = re.search(rf"^## {number}\.[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1) if m else ""


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _assumptions(section: str) -> list[dict[str, str]]:
    rows = [line for line in section.splitlines() if line.lstrip().startswith("|")]
    if len(rows) < 2:
        return []
    head = [c.lower() for c in _cells(rows[0])]
    col = {name: head.index(name) for name in ("assumption", "type", "verdict") if name in head}
    out = []
    for row in rows[2:]:
        cells = _cells(row)
        if len(cells) < len(head):
            continue
        kind = cells[col["type"]].lower() if "type" in col else ""
        base = next((t for t in ASSUMPTION_TYPES if kind.startswith(t)), kind.split(" — ")[0])
        verdict = cells[col["verdict"]] if "verdict" in col else ""
        token = re.match(r"\**\s*(\w+)", verdict)
        out.append(
            {
                "assumption": _trunc(cells[col.get("assumption", 0)], 160),
                "type": base,
                "verdict": token.group(1) if token else "",
            }
        )
    return out


def _count(values: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def parse_analysis(text: str) -> dict[str, Any]:
    """The decisions a finished analysis records, from its fixed template markers."""
    assumptions = _assumptions(_section(text, 2))
    gts = {
        m.group(1): bool(m.group(2))
        for m in re.finditer(r"^\s*- \*\*GT-(\d+)(\?)?\*\*", _section(text, 3), re.M)
    }
    chains_text = _section(text, 4)
    chains = []
    heads = list(re.finditer(r"^### Conclusion (C\d+)\b([^:\n]*):?\s*(.*)$", chains_text, re.M))
    for i, h in enumerate(heads):
        body = chains_text[h.end() : heads[i + 1].start() if i + 1 < len(heads) else None]
        conf = re.search(r"^\*\*Confidence:\*\*\s*(HIGH|MEDIUM|LOW)", body, re.M)
        chains.append(
            {
                "id": h.group(1),
                "tag": h.group(2).strip() or None,  # e.g. [Speculative]
                "title": _trunc(h.group(3), 160),
                "confidence": conf.group(1) if conf else None,
            }
        )
    dead = re.findall(r"^### Dead End\b[^:\n]*:?\s*(.*)$", _section(text, 5), re.M)
    not_applied = [
        {"technique": m.group(1), "phase": int(m.group(2)), "reason": _trunc(m.group(3), 200)}
        for m in re.finditer(r"^- ([\w-]+) \(Phase (\d)\) — not applicable — (.+)$", text, re.M)
    ]
    # gate: one block per criterion per scoring pass; a criterion scored again = Fix/Repeat
    passes: list[dict[str, str]] = [{}]
    criteria: dict[str, str] = {}  # number -> name, e.g. "3": "Establish Ground Truths"
    for m in re.finditer(
        r"\*\*Criterion (\d+):\s*([^*]*?)\s*\*\*.*?Band:\s*\**(" + "|".join(BANDS) + r")",
        text,
        re.S,
    ):
        if m.group(1) in passes[-1]:
            passes.append({})
        passes[-1][m.group(1)] = m.group(3)
        criteria[m.group(1)] = m.group(2)
    result = re.search(r"^Gate result:\s*(.+)$", text, re.M)
    conclusion = _section(text, 6)
    rec = re.search(r"\*\*Recommended approach:\*\*\s*(.+)", conclusion)
    conf = re.search(r"\*\*Confidence:\*\*\s*(HIGH|MEDIUM|LOW)", conclusion)
    mode = re.search(r"Run mode:\s*`([^`]+)`", text)
    # the agent must disclose any re-entry edge (Fix/Repeat, Criterion 1 return, ...) that fired
    edge = re.search(r"[^.\n]*\bre-entry\b[^.\n]*(?:\.[^.\n]*)?", text, re.I)
    return {
        "sections": [h for level, h in HEADING.findall(text) if level == "##"],
        "run_mode": mode.group(1) if mode else None,
        "re_entry": None
        if edge is None
        else {
            "fired": not re.search(r"\b(no|none)\b", edge.group(0), re.I),
            "disclosure": _trunc(re.sub(r"\*+", "", edge.group(0)).strip(" ->"), 240),
        },
        "assumptions": {
            "count": len(assumptions),
            "by_type": _count([a["type"] for a in assumptions]),
            "by_verdict": _count([a["verdict"] for a in assumptions]),
            "rows": assumptions,
        },
        "ground_truths": {
            "count": len(gts),
            "unverified": [f"GT-{n}?" for n, q in gts.items() if q],
        },
        "chains": chains,
        "dead_ends": [_trunc(d, 160) for d in dead],
        "techniques_not_applied": not_applied,
        "gate": {
            "bands": passes[-1] if passes[-1] else {},
            "criteria": criteria,
            "passes": len([p for p in passes if p]),
            "fix_repeat": len([p for p in passes if p]) > 1,
            "result": _trunc(result.group(1), 200) if result else None,
        },
        "conclusion": {
            "recommended": _trunc(rec.group(1), 400) if rec else None,
            "confidence": conf.group(1) if conf else None,
        },
    }


# --- one hook event -> one record -----------------------------------------------------------


def _text_of(response: Any) -> str:
    """Tool output as text, whatever shape the host gave it."""
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        if "stdout" in response:
            return str(response.get("stdout") or "")
        if "content" in response:
            return _text_of(response["content"])
        if "text" in response:
            return str(response["text"])
    if isinstance(response, list):
        return "\n".join(_text_of(x) for x in response)
    return "" if response is None else json.dumps(response)


def _tool_record(payload: dict[str, Any]) -> dict[str, Any] | None:
    tool = str(payload.get("tool_name") or "")
    inp = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    if tool == CALC_TOOL:
        return {
            "kind": "calc",
            "expression": _trunc(inp.get("expression")),
            "result": _trunc(_text_of(payload.get("tool_response")), 200),
        }
    if tool == "Read":
        path = str(inp.get("file_path") or "")
        name = Path(path).name
        if "/references/" not in path:
            return None
        meaning = REFERENCES.get(name) or (
            "worked example" if "/references/examples/" in path else "reference"
        )
        return {"kind": "reference_read", "file": name, "meaning": meaning}
    if tool == "Bash":
        cmd = str(inp.get("command") or "")
        if REPORT_DIR.search(cmd):
            path = REPORT_PATH.search(cmd)
            if APPEND.search(cmd) and "<<" in cmd:
                heads = [h for _, h in HEADING.findall(cmd)]
                body = "".join(m.group(3) + "\n" for m in HEREDOC.finditer(cmd))
                return {
                    "kind": "section_written",
                    "path": path.group(0) if path else None,
                    "headings": [_trunc(h, 160) for h in heads],
                    "revises": bool(REVISE.search(cmd)),  # e.g. sed -i on earlier text, then append
                    "restarts": bool(RESTART.search(cmd)),  # empties the report and writes it again
                    "chars": len(cmd),
                    "text": body,  # what was appended, so the report can be rebuilt offline
                }
            return {
                "kind": "report_op",
                "op": _report_op(cmd),
                "path": path.group(0) if path else None,
                "command": _trunc(cmd, 160),
            }
        return {"kind": "shell", "math": bool(MATH.search(cmd)), "command": _trunc(cmd, 200)}
    return None


def _report_op(cmd: str) -> str:
    """What a non-append report command does: create, revise (rewrite in place) or check."""
    if REVISE.search(cmd):
        return "revise"
    if re.search(r":\s*>\s*\S|\btouch\b|\bmkdir\b", cmd):
        return "create"
    return "check"


def _analysis_path(records: list[dict[str, Any]], cwd: str) -> Path | None:
    """The file the run appended to; else the newest analysis in the agent's cwd."""
    for rec in reversed(records):
        if rec.get("kind") in ("section_written", "report_op") and rec.get("path"):
            p = Path(rec["path"])
            p = p if p.is_absolute() else Path(cwd or ".") / p
            if p.is_file():
                return p
    found = sorted(
        Path(cwd or ".").glob(".first-principles/analysis-*.md"), key=lambda f: f.stat().st_mtime
    )
    return found[-1] if found else None


def _from_appends(records: list[dict[str, Any]]) -> tuple[str, bool]:
    """The report rebuilt from its appended sections, and whether that is exact (no in-place
    revision touched it). An emptied report (``: > "$F"`` or a second create) starts again."""
    text, exact = "", True
    for rec in records:
        if rec.get("op") == "create" or rec.get("restarts"):
            text, exact = "", True
        if rec.get("op") == "revise" or rec.get("revises"):
            exact = False
        if rec.get("kind") == "section_written":
            text += str(rec.get("text") or "")
    return text, exact


def _analysis(
    run: list[dict[str, Any]], cwd: str, payload: dict[str, Any]
) -> tuple[Path | None, str | None, str | None, bool]:
    """(path, text, source, exact) of the finished report. Source: ``file`` on disk, else
    ``capture`` (a full copy a replay found in the session), else ``appends`` (rebuilt from the
    trace's own section records; exact only when nothing was revised in place)."""
    path = _analysis_path(run, cwd)
    if path:
        try:
            return path, path.read_text(encoding="utf-8"), "file", True
        except OSError:
            pass
    copies = (
        payload.get("analysis_texts") if isinstance(payload.get("analysis_texts"), dict) else {}
    )
    for rec in reversed(run):
        raw = str(rec.get("path") or "")
        for key in (raw, str(Path(cwd or ".") / raw)):
            if raw and isinstance(copies.get(key), str) and copies[key].strip():
                return path, copies[key], "capture", True
    text, exact = _from_appends(run)
    if text.strip():
        return path, text, "appends", exact
    return path, None, None, False


def _routing(
    audit: list[dict[str, Any]],
    run: list[dict[str, Any]],
    start: datetime | None,
    end: datetime | None,
) -> dict[str, Any]:
    """The router's decisions that belong to this run, from its audit log."""

    def inside(rec: dict[str, Any]) -> bool:
        t = _when(rec.get("ts"))
        return t is not None and (start is None or t >= start) and (end is None or t <= end)

    before = [
        r
        for r in audit
        if r.get("point") == "prompt" and (start is None or (_when(r.get("ts")) or start) <= start)
    ]
    prompt = before[-1] if before else None
    notes = [
        r
        for r in audit
        if inside(r)
        and r.get("agent_type") == AGENT
        and r.get("action") == "suggest"
        and r.get("entry_id") == "exact-calc"
    ]
    first = _when(notes[0]["ts"]) if notes else None
    calcs = [r for r in run if r.get("kind") == "calc" or r.get("was") == "calc"]
    maths = [r for r in run if r.get("kind") == "shell" and r.get("math")]

    def after(recs: list[dict[str, Any]]) -> int:
        return sum(1 for r in recs if first and (_when(r.get("ts")) or first) >= first)

    return {
        "delegation": None
        if prompt is None
        else {
            "action": prompt.get("action"),
            "entry_id": prompt.get("entry_id"),
            "p": (prompt.get("probabilities") or {}).get("first-principles-agent"),
            "applied_threshold": prompt.get("applied_threshold"),
        },
        "calc_notes": len(notes),
        "calc_calls": len(calcs),
        "calc_failures": sum(1 for r in calcs if r.get("kind") == "tool_failed"),
        "shell_math_calls": len(maths),
        "calc_calls_after_note": after(calcs) if notes else None,
        "shell_math_after_note": after(maths) if notes else None,
        "calc_note_followed": (after(calcs) > 0) if notes else None,
    }


def handle(
    payload: dict[str, Any], root: Path | None = None, now: str | None = None
) -> dict[str, Any] | None:
    """Append the record for one hook payload; returns it (None when nothing is recorded)."""
    if payload.get("agent_type") != AGENT:
        return None
    root = root if root is not None else state_root()
    session = _safe(str(payload.get("session_id") or ""))
    trace = root / "trace" / f"{session}.jsonl"
    event = str(payload.get("hook_event_name") or "")
    rec: dict[str, Any] | None
    if event == "SubagentStart":
        rec = {"kind": "run_start"}
    elif event == "PostToolUse":
        rec = _tool_record(payload)
    elif event == "PostToolUseFailure":
        base = _tool_record(payload) or {}
        rec = {
            **base,
            "kind": "tool_failed",
            "tool_name": payload.get("tool_name"),
            "was": base.get("kind"),
            "error": _trunc(payload.get("error"), 200),
        }
        rec.pop("result", None)
    elif event == "SubagentStop":
        agent_id = payload.get("agent_id")
        run = [r for r in _read_jsonl(trace) if r.get("agent_id") == agent_id]
        start = next((_when(r["ts"]) for r in run if r.get("kind") == "run_start"), None)
        end = _when(now) if now else datetime.now(UTC)
        path, text, source, exact = _analysis(run, str(payload.get("cwd") or ""), payload)
        decisions = parse_analysis(text) if text else None
        audit_env = os.environ.get("AGENT_ROUTER_AUDIT", "").strip()
        audit = _read_jsonl(Path(audit_env) if audit_env else root / "audit" / f"{session}.jsonl")
        rec = {
            "kind": "run_end",
            "duration_s": round((end - start).total_seconds(), 1) if start and end else None,
            "final_message": _trunc(payload.get("last_assistant_message")),
            "analysis": str(path) if path else None,
            "analysis_source": source,
            "analysis_exact": exact if text else None,
            "analysis_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None,
            "analysis_text": text,  # the finished report itself, so the trace outlives the file
            "sections_written": sum(1 for r in run if r.get("kind") == "section_written"),
            "report_restarts": sum(1 for r in run if r.get("restarts"))
            + max(0, sum(1 for r in run if r.get("op") == "create") - 1),
            "report_revisions": sum(1 for r in run if r.get("op") == "revise" or r.get("revises")),
            "references_read": [r["file"] for r in run if r.get("kind") == "reference_read"],
            "tool_failures": sum(1 for r in run if r.get("kind") == "tool_failed"),
            "decisions": decisions,
            "routing": _routing(audit, run, start, end),
        }
    else:
        return None
    if rec is None:
        return None
    rec = {
        "ts": now or datetime.now(UTC).isoformat(),
        "session": payload.get("session_id"),
        "agent_id": payload.get("agent_id"),
        **rec,
    }
    if "tool_name" not in rec and payload.get("tool_name"):
        rec["tool_name"] = payload.get("tool_name")
    if payload.get("tool_use_id"):  # the same id the router's audit record carries
        rec["tool_use_id"] = payload.get("tool_use_id")
    trace.parent.mkdir(parents=True, exist_ok=True)
    with trace.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


# --- offline replay of a capture -------------------------------------------------------------


_READ_LINE = re.compile(r"^\s*\d+\t", re.M)


def _captured_reports(events: list[dict[str, Any]]) -> dict[str, str]:
    """Full copies of analysis files the main session read (``Read`` without offset/limit, or a
    ``cat``) in a capture, by path: the exact report even when the file is gone."""
    uses: dict[str, tuple[str, str]] = {}
    out: dict[str, str] = {}
    for e in events:
        content = (e.get("message") or {}).get("content")
        if e.get("parent_tool_use_id") or not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if e.get("type") == "assistant" and b.get("type") == "tool_use":
                inp = b.get("input") or {}
                if b.get("name") == "Read" and not ({"offset", "limit", "pages"} & set(inp)):
                    uses[b["id"]] = ("read", str(inp.get("file_path") or ""))
                elif b.get("name") == "Bash":
                    m = re.fullmatch(r"\s*cat\s+(\S+\.md)\s*", str(inp.get("command") or ""))
                    if m:
                        uses[b["id"]] = ("cat", m.group(1).strip("'\""))
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in uses:
                how, path = uses.pop(b["tool_use_id"])
                text = _text_of(b.get("content"))
                if (
                    not REPORT_PATH.search(path)
                    or b.get("is_error")
                    or "<persisted-output>" in text
                ):
                    continue
                if how == "read":
                    text = _READ_LINE.sub("", text)
                if len(text) > len(out.get(path, "")):
                    out[path] = text
    return out


def replay_payloads(capture: Path) -> list[tuple[dict[str, Any], str | None]]:
    """The hook payloads a ``claude -p`` capture implies, in order, with their timestamps.

    Only the first-principles agent's events are rebuilt: SubagentStart at its first event,
    PostToolUse / PostToolUseFailure per tool result, SubagentStop at the Agent tool's result.
    """
    events = [e for e in _read_jsonl(capture)]
    session = next((e.get("session_id") for e in events if e.get("session_id")), "")
    cwd = next((e.get("cwd") for e in events if e.get("type") == "system" and e.get("cwd")), "")
    base = {"session_id": session, "cwd": cwd, "agent_type": AGENT}
    reports = _captured_reports(events)
    agents: dict[str, str] = {}  # Agent tool_use id -> synthetic agent_id
    calls: dict[str, dict[str, Any]] = {}
    out: list[tuple[dict[str, Any], str | None]] = []
    ts = None  # system events carry no timestamp: they take the last one seen
    for e in events:
        msg = e.get("message") or {}
        content = msg.get("content") if isinstance(msg.get("content"), list) else []
        parent = e.get("parent_tool_use_id")
        ts = e.get("timestamp") or ts
        if e.get("type") == "assistant":
            for b in content:
                if b.get("type") != "tool_use":
                    continue
                if (
                    not parent
                    and b.get("name") in ("Agent", "Task")
                    and AGENT in json.dumps(b.get("input", {}))
                ):
                    agents[b["id"]] = f"replay-{len(agents) + 1}"
                    out.append(
                        (
                            {
                                **base,
                                "hook_event_name": "SubagentStart",
                                "agent_id": agents[b["id"]],
                            },
                            ts,
                        )
                    )
                elif parent in agents:
                    calls[b["id"]] = {
                        "name": b["name"],
                        "input": b.get("input", {}),
                        "agent_id": agents[parent],
                    }
        elif e.get("type") == "user":
            for b in content:
                if b.get("type") != "tool_result":
                    continue
                tid = b.get("tool_use_id")
                if tid in calls:
                    c = calls.pop(tid)
                    body = b.get("content")
                    p = {
                        **base,
                        "agent_id": c["agent_id"],
                        "tool_use_id": tid,
                        "tool_name": c["name"],
                        "tool_input": c["input"],
                    }
                    if b.get("is_error"):
                        out.append(
                            (
                                {
                                    **p,
                                    "hook_event_name": "PostToolUseFailure",
                                    "error": _text_of(body),
                                },
                                ts,
                            )
                        )
                    else:
                        resp = {"stdout": _text_of(body)} if c["name"] == "Bash" else body
                        out.append(
                            ({**p, "hook_event_name": "PostToolUse", "tool_response": resp}, ts)
                        )
                elif tid in agents and not parent and "async_launched" not in _text_of(body):
                    out.append(
                        (
                            {
                                **base,
                                "hook_event_name": "SubagentStop",
                                "analysis_texts": reports,
                                "agent_id": agents.pop(tid),
                                "last_assistant_message": _text_of(body),
                            },
                            ts,
                        )
                    )
        elif e.get("subtype") == "task_notification" and e.get("tool_use_id") in agents:
            # a backgrounded agent ends with a notification, not with the Agent tool's result
            out.append(
                (
                    {
                        **base,
                        "hook_event_name": "SubagentStop",
                        "analysis_texts": reports,
                        "agent_id": agents.pop(e["tool_use_id"]),
                        "last_assistant_message": e.get("summary"),
                    },
                    ts,
                )
            )
    return out


def _fix_repeat(decisions: dict[str, Any]) -> str:
    """Did the gate re-score? A rewritten report can drop the first pass, so also read the
    agent's re-entry disclosure."""
    if (decisions.get("gate") or {}).get("fix_repeat"):
        return "yes"
    edge = decisions.get("re_entry") or {}
    if edge.get("fired") and "fix/repeat" in str(edge.get("disclosure")).lower():
        return "yes (disclosed)"
    return "no"


def report(trace_dir: Path) -> str:
    """One Markdown row per finished run in ``trace_dir``: what the agent decided."""
    lines = [
        "| session | run | s | sections | references read | delegation | calc notes / calls "
        "/ followed | GT (unverified) | chains (confidence) | dead ends | not applied "
        "| gate | Fix/Repeat | report restarts / revisions | assumptions | confidence |",
        "|---" * 16 + "|",
    ]
    for path in sorted(trace_dir.glob("*.jsonl")):
        for end in (r for r in _read_jsonl(path) if r.get("kind") == "run_end"):
            d = end.get("decisions") or {}
            rt = end.get("routing") or {}
            gate = d.get("gate") or {}
            chains = d.get("chains") or []
            conf = _count([c.get("confidence") or "?" for c in chains])
            verdicts = (d.get("assumptions") or {}).get("by_verdict") or {}
            deleg = (rt.get("delegation") or {}).get("action") or "-"
            cells = [
                str(end.get("session"))[:8],
                str(end.get("agent_id"))[:8],
                str(end.get("duration_s")),
                str(end.get("sections_written")),
                ", ".join(f.removesuffix(".md") for f in end.get("references_read") or []),
                "note" if deleg == "suggest" else deleg,
                f"{rt.get('calc_notes')} / {rt.get('calc_calls')} / "
                f"{'-' if rt.get('calc_note_followed') is None else rt['calc_note_followed']}",
                f"{(d.get('ground_truths') or {}).get('count')} "
                f"({len((d.get('ground_truths') or {}).get('unverified') or [])})",
                f"{len(chains)} (" + ", ".join(f"{k} {v}" for k, v in conf.items()) + ")",
                str(len(d.get("dead_ends") or [])),
                ", ".join(t["technique"] for t in d.get("techniques_not_applied") or []) or "-",
                "".join(b[0] for b in (gate.get("bands") or {}).values()) or "-",
                _fix_repeat(d),
                f"{end.get('report_restarts', 0)} / {end.get('report_revisions', 0)}",
                ", ".join(f"{k} {v}" for k, v in verdicts.items()) or "-",
                str((d.get("conclusion") or {}).get("confidence")),
            ]
            lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--replay", type=Path, help="a claude -p stream-json capture")
    ap.add_argument("--state", type=Path, help="state dir for --replay (default: state_root)")
    ap.add_argument("--report", type=Path, help="a trace dir: print one row per finished run")
    args = ap.parse_args()
    if args.report:
        print(report(args.report))
        return 0
    if args.replay:
        n = 0
        for payload, ts in replay_payloads(args.replay):
            n += handle(payload, args.state, now=ts) is not None
        print(f"{n} trace records from {args.replay}")
        return 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if isinstance(payload, dict):
            handle(payload)
    except Exception:  # record-only: a tracing failure must never reach the agent
        pass
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
