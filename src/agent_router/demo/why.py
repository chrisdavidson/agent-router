"""Why each step of a traced run happened, read from the agent's own Claude Code transcript.

The trace records *what* an agent did (one record per tool call, keyed by ``tool_use_id``). The
agent's transcript (``<project>/<session>/subagents/agent-<agent_id>.jsonl``, written by Claude
Code) holds what it said around each call. Joined on the same ``tool_use_id``, per call:

- ``said``: the agent's last message before the call (its stated intent), with its time
- ``thinking``: non-empty reasoning in the same turn, when the transcript kept any
- ``purpose``: the note the agent wrote on the call itself (Bash ``description``, WebFetch
  ``prompt``), which a quiet agent writes even when it says nothing between calls
- ``said_after``: its first message after the call's result came back
- ``offered_by``: the line of its delegating prompt that names the tool, if one does
- ``used_in``: for calculator calls, later calls whose input repeats a number from the result
  (a match, not proof)

and per run the agent's messages in order (``narrations``), which the Trace tab uses as headers.
Read-only, local files only.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

_AGENT_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_SAID = 600
MAX_THINKING = 1500
MAX_USED = 8
# numbers worth tracing from a calculator result: the value after "=", 3+ digits
_RESULT_VALUE = re.compile(r"=\s*(-?\d[\d,]*(?:\.\d+)?)")


def claude_projects_dir() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    return (Path(base) if base else Path.home() / ".claude") / "projects"


def find_transcript(session: str, agent_id: str, hints: list[str] | None = None) -> Path | None:
    """The subagent transcript for one run: next to a recorded transcript path, else under
    Claude Code's projects folder. Only ever a file named ``agent-<agent_id>.jsonl``."""
    if not _AGENT_RE.match(agent_id or "") or not _AGENT_RE.match(session.replace(".", "_")):
        return None
    name = f"agent-{agent_id}.jsonl"
    for hint in hints or []:
        p = Path(hint)
        for cand in (
            p,
            p.with_suffix("") / "subagents" / name,
            p.parent / session / "subagents" / name,
        ):
            if cand.name == name and cand.is_file():
                return cand
    projects = claude_projects_dir()
    if projects.is_dir():
        for cand in projects.glob(f"*/{session}/subagents/{name}"):
            if cand.is_file():
                return cand
    return None


def _clip(text: str, n: int) -> str:
    text = text.strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def short_tool(name: str) -> str:
    """``mcp__plugin_x__calc_script`` -> ``calc_script``."""
    return re.sub(r"^mcp__.*__", "", name or "")


def offered_line(prompt: str, tool: str) -> str | None:
    """The prompt line that names the tool (``calc_script`` also matches a line naming ``calc``)."""
    short = short_tool(tool)
    if not short or not prompt:
        return None
    names = [short]
    if "_" in short:
        names.append(short.split("_")[0])
    for name in names:
        pat = re.compile(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])")
        for line in prompt.splitlines():
            if pat.search(line):
                return _clip(line, 400)
    return None


def _number_pattern(value: str) -> re.Pattern[str] | None:
    digits = value.replace(",", "").lstrip("-")
    whole = digits.split(".")[0]
    if len(whole.replace(".", "")) < 3:
        return None  # 7, 12, 60: too common to mean anything
    if "." in digits:
        body = re.escape(digits)
    else:  # allow thousands separators: 2852 also matches 2,852
        groups = []
        s = whole
        while len(s) > 3:
            groups.insert(0, s[-3:])
            s = s[:-3]
        groups.insert(0, s)
        body = ",?".join(groups)
    return re.compile(rf"(?<![\d.]){body}(?![\d])")


def result_numbers(result: str) -> list[str]:
    seen: list[str] = []
    for m in _RESULT_VALUE.finditer(result):
        v = m.group(1).rstrip(",")
        if v not in seen and _number_pattern(v):
            seen.append(v)
    return seen


def explain(lines: list[dict[str, Any]]) -> dict[str, Any]:
    """Narrations and per-call reasons from one transcript's entries."""
    prompt = ""
    narrations: list[dict[str, Any]] = []
    calls: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    inputs: dict[str, str] = {}
    results: dict[str, tuple[str, str]] = {}
    said: dict[str, Any] | None = None
    thinking = ""
    for entry in lines:
        msg = entry.get("message") or {}
        ts = entry.get("timestamp")
        kind = entry.get("type")
        content = msg.get("content")
        if kind == "user":
            if not prompt and isinstance(content, str):
                prompt = content
                continue
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        results[str(b.get("tool_use_id"))] = (_text(b.get("content")), ts)
                if not prompt:
                    prompt = _text(
                        [b for b in content if isinstance(b, dict) and b.get("type") == "text"]
                    )
            continue
        if kind != "assistant" or not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text" and b.get("text", "").strip():
                said = {"ts": ts, "text": _clip(b["text"], MAX_SAID)}
                narrations.append(said)
                thinking = ""
            elif b.get("type") == "thinking" and b.get("thinking", "").strip():
                thinking = _clip(b["thinking"], MAX_THINKING)
            elif b.get("type") == "tool_use":
                tid = str(b.get("id"))
                name = str(b.get("name") or "")
                args = b.get("input") if isinstance(b.get("input"), dict) else {}
                inputs[tid] = json.dumps(args, ensure_ascii=False)
                purpose = args.get("description") or (
                    args.get("prompt") if short_tool(name) == "WebFetch" else None
                )
                order.append(tid)
                calls[tid] = {
                    "tool": name,
                    "ts": ts,
                    "said": said,
                    "thinking": thinking or None,
                    "purpose": _clip(purpose, 300)
                    if isinstance(purpose, str) and purpose.strip()
                    else None,
                    "offered_by": offered_line(prompt, name),
                }
                thinking = ""  # reasoning belongs to the turn that made the call
    for tid, call in calls.items():
        done = results.get(tid)
        after = done[1] if done else call["ts"]
        call["said_after"] = next(
            (n for n in narrations if after and n["ts"] and n["ts"] > after), None
        )
        name = short_tool(call["tool"])
        if done and name.startswith("calc"):
            nums = result_numbers(done[0])
            pats = [(v, p) for v in nums if (p := _number_pattern(v))]
            used: list[dict[str, Any]] = []
            for later in order[order.index(tid) + 1 :]:
                if short_tool(calls[later]["tool"]).startswith("calc"):
                    continue  # feeding another calculation is not the result being used
                hit = [v for v, p in pats if p.search(inputs[later])]
                if hit:
                    used.append({"tool_use_id": later, "numbers": hit[:6]})
                if len(used) >= MAX_USED:
                    break
            call["used_in"] = used
    return {
        "prompt": _clip(prompt, 4000),
        "narrations": narrations,
        "calls": calls,
    }


def read_transcript(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:  # a line still being written
                continue
            if isinstance(rec, dict):
                out.append(rec)
    return out


MAX_KEPT_NARRATIONS = 120


def compact(w: dict[str, Any]) -> dict[str, Any]:
    """``explain()`` output sized for a trace record: each message and prompt line once, calls
    pointing at them by index (``expand`` reverses it)."""
    narrations = w.get("narrations", [])[:MAX_KEPT_NARRATIONS]
    index = {(n["ts"], n["text"]): i for i, n in enumerate(narrations)}
    offers: list[str] = []
    calls: dict[str, Any] = {}
    for tid, c in (w.get("calls") or {}).items():
        row: dict[str, Any] = {"tool": c.get("tool"), "ts": c.get("ts")}
        for key, out in (("said", "said_i"), ("said_after", "after_i")):
            n = c.get(key)
            if n and (n["ts"], n["text"]) in index:
                row[out] = index[(n["ts"], n["text"])]
        if c.get("offered_by"):
            if c["offered_by"] not in offers:
                offers.append(c["offered_by"])
            row["offer_i"] = offers.index(c["offered_by"])
        for key in ("thinking", "purpose", "used_in"):
            if c.get(key):
                row[key] = c[key]
        calls[tid] = row
    return {
        "prompt": _clip(w.get("prompt") or "", 2000),
        "narrations": narrations,
        "offers": offers,
        "calls": calls,
    }


def expand(kept: dict[str, Any]) -> dict[str, Any]:
    narrations = kept.get("narrations") or []
    offers = kept.get("offers") or []
    pick = lambda xs, i: xs[i] if isinstance(i, int) and 0 <= i < len(xs) else None  # noqa: E731
    calls = {}
    for tid, c in (kept.get("calls") or {}).items():
        calls[tid] = {
            "tool": c.get("tool"),
            "ts": c.get("ts"),
            "said": pick(narrations, c.get("said_i")),
            "said_after": pick(narrations, c.get("after_i")),
            "offered_by": pick(offers, c.get("offer_i")),
            "thinking": c.get("thinking"),
            "purpose": c.get("purpose"),
            "used_in": c.get("used_in") or [],
        }
    return {"prompt": kept.get("prompt") or "", "narrations": narrations, "calls": calls}
