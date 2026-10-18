"""The text of a PDF, from a workspace file or a URL (pdfminer.six, MIT).

The first-principles agents asked WebFetch to read 21 PDF links and got useful content once:
WebFetch hands a PDF to a small model that summarises what it can, and 17 times that summary
said the fact was not there. The agents fell back to ``curl ... && pdftotext`` (poppler, GPL).
This tool returns the document's own text instead, page by page, so the agent can quote it.

``extract`` returns the text with a ``[page N]`` marker before each page. ``pages`` limits it
(``"1-3,7"``). ``find`` returns only the passages that contain a term (comma-separated, case
insensitive), each with its page, so a 300-page report does not flood the context. A URL is
fetched with httpx (BSD-3) as ``agent-router-document-text``: it identifies itself and accepts a
refusal rather than posing as a browser. Nothing is stored; the text is only returned.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

from agent_router.tools._paths import resolve_inside

MAX_DOCUMENT_BYTES = 50 * 1024 * 1024
MAX_PAGES = 1_000
MAX_OUTPUT_CHARS = 60_000  # a whole document beyond this is cut, with a note to use pages/find
MAX_PASSAGES = 40
PASSAGE_CHARS = 600  # a passage is the paragraph holding the term, cut to this around it
FETCH_TIMEOUT_S = 30.0
USER_AGENT = "agent-router-document-text/1 (+https://github.com/chrisdavidson/agent-router)"


@dataclass
class Document:
    pages: list[str]  # text of every page read, in order
    numbers: list[int]  # 1-based page numbers of ``pages``
    total_pages: int
    source: str


def parse_pages(spec: str | None, total: int) -> list[int]:
    """``"1-3,7"`` -> ``[1, 2, 3, 7]`` (1-based, within ``total``); None or "" -> every page."""
    if spec is None or not str(spec).strip():
        return list(range(1, total + 1))
    out: list[int] = []
    for part in str(spec).split(","):
        part = part.strip()
        m = re.fullmatch(r"(\d+)\s*(?:-\s*(\d+)?)?", part)
        if not m:
            raise ValueError(f"bad page range {part!r} (use e.g. '1-3,7')")
        lo = int(m.group(1))
        hi = lo if "-" not in part else int(m.group(2) or total)
        if lo < 1 or hi < lo:
            raise ValueError(f"bad page range {part!r}")
        out.extend(n for n in range(lo, min(hi, total) + 1) if n not in out)
    if not out:
        raise ValueError(f"no such pages: the document has {total}")
    return out


def _fetch(url: str) -> bytes:
    import httpx

    if not re.match(r"https?://", url, re.I):
        raise ValueError("url must start with http:// or https://")
    try:
        with (
            httpx.Client(
                follow_redirects=True,
                timeout=FETCH_TIMEOUT_S,
                headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*;q=0.5"},
            ) as client,
            client.stream("GET", url) as resp,
        ):
            if resp.status_code >= 400:
                raise ValueError(f"fetching the document failed: HTTP {resp.status_code}")
            data = bytearray()
            for chunk in resp.iter_bytes():
                data += chunk
                if len(data) > MAX_DOCUMENT_BYTES:
                    raise ValueError(f"document larger than {MAX_DOCUMENT_BYTES} bytes")
            return bytes(data)
    except httpx.HTTPError as exc:
        raise ValueError(f"fetching the document failed: {type(exc).__name__}: {exc}") from exc


def _read_path(root: Path, path: str) -> bytes:
    target = resolve_inside(root, path)
    if not target.is_file():
        raise ValueError(f"file not found: {path}")
    if target.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError(f"file larger than {MAX_DOCUMENT_BYTES} bytes: {path}")
    return target.read_bytes()


def read_document(
    data: bytes, source: str, pages: str | None = None, *, need_text: bool = True
) -> Document:
    """Every requested page's text. ``ValueError`` when ``data`` is not a readable PDF."""
    if not data.lstrip()[:5].startswith(b"%PDF"):
        head = data.lstrip()[:200].lower()
        kind = "an HTML page" if b"<html" in head or b"<!doctype" in head else "not a PDF"
        raise ValueError(f"{source} is {kind}; document_text reads PDFs")
    from pdfminer.converter import TextConverter
    from pdfminer.layout import LAParams
    from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdfparser import PDFSyntaxError

    fp = io.BytesIO(data)
    try:
        all_pages = list(PDFPage.get_pages(fp, check_extractable=False))
    except (PDFSyntaxError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"cannot read {source} as a PDF: {type(exc).__name__}: {exc}") from exc
    except Exception as exc:  # pdfminer raises its own types for encryption and damage
        raise ValueError(f"cannot read {source} as a PDF: {type(exc).__name__}: {exc}") from exc
    total = len(all_pages)
    if total == 0:
        raise ValueError(f"{source} has no pages")
    wanted = parse_pages(pages, total)[:MAX_PAGES]
    rsrc = PDFResourceManager()
    buf = io.StringIO()
    device = TextConverter(rsrc, buf, laparams=LAParams())
    interp = PDFPageInterpreter(rsrc, device)
    texts: list[str] = []
    try:
        for n in wanted:
            buf.seek(0)
            buf.truncate()
            try:
                interp.process_page(all_pages[n - 1])
            except Exception as exc:  # one damaged page should not lose the others
                texts.append(f"(page {n} could not be read: {type(exc).__name__})")
                continue
            texts.append(_tidy(buf.getvalue()))
    finally:
        device.close()
    if need_text and not any(t.strip() for t in texts):
        raise ValueError(
            f"{source} has no text layer on the pages read (a scanned PDF needs OCR, "
            "which this tool does not do)"
        )
    return Document(texts, wanted, total, source)


def _tidy(text: str) -> str:
    text = text.replace("\x0c", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def passages(doc: Document, find: str) -> list[tuple[int, str]]:
    """(page, passage) for each paragraph holding a term, in page order, at most MAX_PASSAGES."""
    terms = [t.strip().lower() for t in find.split(",") if t.strip()]
    if not terms:
        raise ValueError("find needs at least one term")
    out: list[tuple[int, str]] = []
    for n, text in zip(doc.numbers, doc.pages, strict=True):
        for para in re.split(r"\n\s*\n", text):
            low = para.lower()
            hits = [low.find(t) for t in terms if t in low]
            if not hits:
                continue
            para = re.sub(r"\s*\n\s*", " ", para).strip()
            if len(para) > PASSAGE_CHARS:
                at = min(h for h in hits if h >= 0)
                start = max(0, min(at - PASSAGE_CHARS // 3, len(para) - PASSAGE_CHARS))
                para = ("…" if start else "") + para[start : start + PASSAGE_CHARS] + "…"
            out.append((n, para))
            if len(out) >= MAX_PASSAGES:
                return out
    return out


def render(doc: Document, find: str | None = None) -> str:
    head = f"{doc.source}: {doc.total_pages} page(s)" + (
        f", pages {_ranges(doc.numbers)} read" if len(doc.numbers) < doc.total_pages else ""
    )
    if find is not None and find.strip():
        found = passages(doc, find)
        if not found:
            return f"{head}\nNo passage contains: {find}"
        more = " (first ones only: narrow find or pages)" if len(found) >= MAX_PASSAGES else ""
        body = "\n\n".join(f"[page {n}] {p}" for n, p in found)
        return f"{head}\n{len(found)} passage(s) containing: {find}{more}\n\n{body}"
    parts: list[str] = []
    used = 0
    for n, text in zip(doc.numbers, doc.pages, strict=True):
        block = f"[page {n}]\n{text}"
        if used + len(block) > MAX_OUTPUT_CHARS:
            parts.append(
                f"[cut at page {n}: the text is longer than {MAX_OUTPUT_CHARS} characters; "
                "ask for pages or use find]"
            )
            break
        parts.append(block)
        used += len(block)
    return head + "\n\n" + "\n\n".join(parts)


def _ranges(ns: list[int]) -> str:
    """``[1, 2, 3, 7]`` -> ``"1-3,7"``."""
    out: list[str] = []
    start = prev = None
    for n in [*ns, None]:
        if prev is not None and n == prev + 1:
            prev = n
            continue
        if start is not None:
            out.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = n
    return ",".join(out)


def extract(
    path: str | None = None,
    url: str | None = None,
    pages: str | None = None,
    find: str | None = None,
    *,
    root: Path,
) -> str:
    """The text of the PDF at ``path`` (inside ``root``) or ``url``; see the module docstring."""
    if (path is None) == (url is None):
        raise ValueError("give exactly one of path or url")
    data = _read_path(root, path) if path is not None else _fetch(str(url))
    doc = read_document(data, path if path is not None else str(url), pages)
    return render(doc, find)
