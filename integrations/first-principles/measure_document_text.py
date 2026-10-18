#!/usr/bin/env python3
"""Would ``document_text`` have read the PDFs the agents could not? Re-run them through it.

The population is every PDF the plugin's agent tried to read: the tool-gap report's
``document_to_text`` calls (``tool_gaps.py``, over the hooks' state and every saved run's) and
every ``WebFetch`` of a ``.pdf`` link in the local run captures, joined by tool_use_id.

* WebFetch half. Each link is fetched again through ``document_text`` (``--fetch``: this
  sends one request per distinct link, as the agent did; without it nothing leaves the
  machine and only the population is counted). Reported: did it return the document's text,
  and was what the agent asked for in it? ANSWERED is a proxy for "useful content": the
  specific terms of the agent's WebFetch prompt (its numbers, quoted words, capitalised names
  and long words, not its instructions) are looked up with ``find``; a link is answered when
  at least half of them occur in the text. It is set against what WebFetch said for the same
  call (the trace's ``outcome``: ``ok``, ``reported_missing``, a failure).
* pdftotext half. Where the agent ran ``pdftotext`` and the result was recorded, and the PDF is
  still on disk (or its link is in the command, with ``--fetch``): ``document_text`` reads the
  same file, and AGREEMENT is the share of the words ``pdftotext`` printed (3+ letters) that
  ``document_text`` also returns.

Counts only: no URL, host, prompt or text is printed or written. ``--write`` writes
``DOCUMENT-TEXT-COVERAGE.md``.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import shlex
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from agent_router.tools import document_text as dt  # noqa: E402

# the agent's instructions to WebFetch, not what it was looking for
_INSTRUCTION_WORDS = """
    quote verbatim exact exactly passage passages sentence sentences any give find what
    which from with that this into also about especially including covering between rows
    row table tables figure figures value values document title author page pages the and
    for any its their there where when does whether every each plus only other more most
    such than then stating mentioning listing used using rate rates
"""
_INSTRUCTION = frozenset(_INSTRUCTION_WORDS.split())
_TERM = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?|[A-Za-z][A-Za-z0-9/_-]*")
_WORD = re.compile(r"[A-Za-z]{3,}")


def _load(name: str, file: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def prompt_terms(prompt: str) -> list[str]:
    """The specific things a WebFetch prompt asks for: numbers, quoted words, capitalised names
    and long words, without the instructions around them. At most 8, longest first."""
    terms: list[str] = []
    for q in re.findall(r"['\"“]([^'\"”]{3,40})['\"”]", prompt):
        terms.append(q.strip())
    for i, tok in enumerate(_TERM.findall(prompt)):
        low = tok.lower().strip("$%")
        if low in _INSTRUCTION or len(low) < 3:
            continue
        if tok[0].isdigit() or tok[0] == "$":
            num = tok.rstrip(".,")
            if len(num.strip("$%")) >= 2 and num not in ("2024", "2025", "2026"):
                terms.append(num)
        elif (tok[0].isupper() and i > 0) or len(tok) >= 7:
            terms.append(tok)
    seen: list[str] = []
    for t in terms:
        if t.lower() not in (s.lower() for s in seen):
            seen.append(t)
    return sorted(seen, key=len, reverse=True)[:8]


def term_found(term: str, text: str) -> bool:
    low = text.lower()
    if term.lower() in low:
        return True
    plain = term.replace(",", "").replace("$", "")
    return bool(re.search(r"\d", plain)) and plain.lower() in low.replace(",", "")


def webfetch_calls(gaps: Any, tr: Any, runs_dir: Path) -> list[dict[str, Any]]:
    """Every WebFetch of a PDF link: url, the agent's prompt (when kept) and WebFetch's outcome."""
    from agent_router.demo import why

    calls: dict[str, dict[str, Any]] = {}
    for capture in sorted(runs_dir.glob("*/*/run.jsonl")):
        for payload, _ts in tr.replay_payloads(capture):
            inp = payload.get("tool_input") or {}
            url = str(inp.get("url") or "")
            if payload.get("tool_name") != "WebFetch" or not _is_pdf_link(url):
                continue
            tid = str(payload.get("tool_use_id"))
            rec = (
                tr._tool_record(payload)
                if payload.get("hook_event_name") == "PostToolUse"
                else None
            )
            outcome = rec.get("outcome") if rec else "failed"
            calls[tid] = {"url": url, "prompt": inp.get("prompt"), "webfetch": outcome}
    for state in gaps.default_states():
        for path in sorted((state / "trace").glob("*.jsonl")):
            for rec in gaps._read(path):
                if gaps.pattern_of(rec) != "document_to_text":
                    continue
                if rec.get("tool") != "WebFetch" and rec.get("tool_name") != "WebFetch":
                    continue
                tid = str(rec.get("tool_use_id"))
                url = str(rec.get("target") or "")
                if tid in calls or not url:
                    continue
                prompt = None
                found = why.find_transcript(
                    str(rec.get("session")), str(rec.get("agent_id") or ""), []
                )
                for line in why.read_transcript(found) if found else []:
                    for block in (line.get("message") or {}).get("content") or []:
                        if isinstance(block, dict) and block.get("id") == tid:
                            prompt = (block.get("input") or {}).get("prompt")
                outcome = "failed" if rec.get("kind") == "tool_failed" else rec.get("outcome")
                calls[tid] = {
                    "url": url,
                    "prompt": prompt or rec.get("purpose"),
                    "webfetch": outcome,
                }
    return list(calls.values())


def _is_pdf_link(url: str) -> bool:
    return bool(re.match(r"https?://", url, re.I)) and re.sub(r"[?#].*$", "", url).lower().endswith(
        ".pdf"
    )


def pdftotext_calls(gaps: Any, tr: Any, runs_dir: Path, calc_fit: Any) -> list[dict[str, Any]]:
    """Bash calls that ran pdftotext with a recorded result: the PDF they read and the output."""
    captured = calc_fit.captured_calls(runs_dir, tr)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for state in gaps.default_states():
        for path in sorted((state / "trace").glob("*.jsonl")):
            for rec in gaps._read(path):
                tid = str(rec.get("tool_use_id"))
                if gaps.pattern_of(rec) != "document_to_text" or tid in seen:
                    continue
                if (rec.get("kind") if rec.get("kind") != "tool_failed" else rec.get("was")) != (
                    "shell"
                ):
                    continue
                seen.add(tid)
                full = captured.get(tid)
                if full is None and rec.get("agent_id"):
                    full = calc_fit._transcript_call(
                        tid, str(rec.get("session")), str(rec["agent_id"]), []
                    )
                out.append(
                    {"command": full[0] if full else None, "stdout": full[1] if full else None}
                )
    return out


def _pdf_source(command: str) -> tuple[str | None, str | None]:
    """(local pdf path, url) that a pdftotext command reads, as far as its text says."""
    try:
        words = shlex.split(command.replace("\n", " ; "))
    except ValueError:
        words = command.split()
    path = next((w for w in words if w.lower().endswith(".pdf") and not w.startswith("http")), None)
    url = next((w for w in words if _is_pdf_link(w)), None)
    return path, url


def scan(runs_dir: Path, fetch: bool) -> dict[str, Any]:
    gaps = _load("fp_tool_gaps", "tool_gaps.py")
    tr = _load("fp_trace", "trace.py")
    calc_fit = _load("fp_measure_calc_fit", "measure_calc_fit.py")
    web = webfetch_calls(gaps, tr, runs_dir)
    s: Counter[str] = Counter()
    by_webfetch: Counter[tuple[str, str]] = Counter()
    docs: dict[str, Any] = {}
    for call in web:
        s["webfetch calls on a PDF link"] += 1
        wf = str(call["webfetch"] or "unknown")
        s[f"webfetch said: {wf}"] += 1
        terms = prompt_terms(str(call["prompt"] or ""))
        if terms:
            s["with the agent's ask (prompt or stated purpose)"] += 1
        if not fetch:
            continue
        url = call["url"]
        if url not in docs:
            try:
                docs[url] = dt.read_document(dt._fetch(url), "link")
            except ValueError as exc:
                docs[url] = _error_kind(str(exc))
        doc = docs[url]
        if isinstance(doc, str):
            s[f"document_text: {doc}"] += 1
            by_webfetch[(wf, doc)] += 1
            continue
        s["document_text: returned the text"] += 1
        s["pages returned"] += len(doc.pages)
        text = "\n".join(doc.pages)
        if not terms:
            by_webfetch[(wf, "text, ask unknown")] += 1
            continue
        hits = sum(term_found(t, text) for t in terms)
        answered = hits * 2 >= len(terms)
        s["terms looked up"] += len(terms)
        s["terms found"] += hits
        s["answered (half or more of the asked terms in the text)"] += answered
        by_webfetch[(wf, "text, answered" if answered else "text, not answered")] += 1
    s["distinct links"] = len({c["url"] for c in web})

    p: Counter[str] = Counter()
    for call in pdftotext_calls(gaps, tr, runs_dir, calc_fit):
        p["pdf shell calls"] += 1
        command, stdout = call["command"], call["stdout"]
        if not command:
            p["full text gone"] += 1
            continue
        if not stdout or not re.search(r"\bpdftotext\b", command):
            p["no pdftotext output recorded"] += 1
            continue
        path, url = _pdf_source(command)
        data = None
        if path and Path(path).expanduser().is_file():
            data = Path(path).expanduser().read_bytes()
            p["pdf still on disk"] += 1
        elif url and fetch:
            try:
                data = dt._fetch(url)
                p["pdf fetched from the link in the command"] += 1
            except ValueError:
                p["pdf gone, link failed"] += 1
                continue
        else:
            p["pdf gone"] += 1
            continue
        try:
            doc = dt.read_document(data, "file")
        except ValueError as exc:
            p[f"document_text: {_error_kind(str(exc))}"] += 1
            continue
        ours = {w.lower() for w in _WORD.findall("\n".join(doc.pages))}
        theirs = [w.lower() for w in _WORD.findall(stdout)]
        if not theirs:
            p["pdftotext printed no words"] += 1
            continue
        recall = sum(w in ours for w in theirs) / len(theirs)
        p["compared with pdftotext"] += 1
        p["agree (90%+ of pdftotext's words returned)"] += recall >= 0.9
        p["recall x1000 (sum)"] += round(recall * 1000)
    return {"web": s, "by_webfetch": by_webfetch, "pdftotext": p, "fetched": fetch}


def _error_kind(msg: str) -> str:
    if "HTTP" in msg:
        m = re.search(r"HTTP (\d+)", msg)
        return f"HTTP {m.group(1)}" if m else "HTTP error"
    if "HTML page" in msg:
        return "an HTML page, not a PDF"
    if "no text layer" in msg:
        return "no text layer (scanned)"
    if "ConnectError" in msg or "Name or service" in msg or "getaddrinfo" in msg:
        return "host unreachable"
    if "Timeout" in msg:
        return "timed out"
    return "unreadable"


def row(label: str, value: Any) -> str:
    return f"| {label} | {value} |"


def render(r: dict[str, Any]) -> str:
    s, p = r["web"], r["pdftotext"]
    n = s["webfetch calls on a PDF link"]
    lines = [
        "# document_text coverage (re-run of the agents' PDF reads)",
        "",
        "Counts only; no URL, host, prompt or text. Regenerate with",
        "`python3 integrations/first-principles/measure_document_text.py --fetch --write`",
        f"(measured {datetime.now(UTC).date().isoformat()}; `--fetch` sends one request per",
        "distinct link, as the agent did). The population comes from this checkout's local",
        "traces and captures, so the figures are a snapshot, not reproducible from a clone.",
        "",
        "## WebFetch on a PDF link, then document_text on the same link",
        "",
        "| Measure | Calls |",
        "|---|---|",
        row("WebFetch calls on a PDF link", n),
        row("distinct links", s["distinct links"]),
    ]
    lines += [row(k, v) for k, v in sorted(s.items()) if k.startswith("webfetch said: ")]
    lines += [
        row(
            "with the agent's ask (prompt or stated purpose)",
            s["with the agent's ask (prompt or stated purpose)"],
        )
    ]
    if r["fetched"]:
        lines += [row(k, v) for k, v in sorted(s.items()) if k.startswith("document_text: ")]
        lines += [
            row("pages returned (all calls)", s["pages returned"]),
            row(
                "answered: half or more of the asked terms in the text",
                s["answered (half or more of the asked terms in the text)"],
            ),
            row("asked terms found / looked up", f"{s['terms found']} / {s['terms looked up']}"),
            "",
            "| What WebFetch said | What document_text gave | Calls |",
            "|---|---|---|",
        ]
        lines += [f"| {a} | {b} | {c} |" for (a, b), c in sorted(r["by_webfetch"].items())]
    lines += [
        "",
        "## pdftotext, then document_text on the same file",
        "",
        "| Measure | Calls |",
        "|---|---|",
    ]
    lines += [row(k, v) for k, v in p.items() if k != "recall x1000 (sum)"]
    if p["compared with pdftotext"]:
        lines.append(
            row(
                "mean share of pdftotext's words returned",
                f"{p['recall x1000 (sum)'] / p['compared with pdftotext'] / 10:.1f}%",
            )
        )
    lines += [
        "",
        "## Reading it",
        "",
        "*Answered* is a proxy, not a reading: it says the specific numbers and names the agent",
        "asked about are in the document's text, which WebFetch's summary had said they were not.",
        "A link that is gone, blocked or an HTML page fails here as it did for WebFetch; that is",
        "a sources problem, not a PDF one. pdftotext agreement is word overlap, so layout",
        "differences (columns, hyphenation) lower it without losing content.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--runs-dir", type=Path, default=HERE / "runs")
    ap.add_argument("--fetch", action="store_true", help="fetch each PDF link again")
    ap.add_argument("--write", action="store_true", help="write DOCUMENT-TEXT-COVERAGE.md")
    args = ap.parse_args(argv)
    text = render(scan(args.runs_dir, args.fetch))
    print(text)
    if args.write:
        (HERE / "DOCUMENT-TEXT-COVERAGE.md").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
