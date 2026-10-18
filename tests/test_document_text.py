"""document_text: a PDF's own text, page by page or by passage; its fit check, MCP tool, catalog
entry and trace record. Offline: a URL is served from a local HTTP server."""

import asyncio
import http.server
import importlib.util
import json
import threading
from pathlib import Path

import pytest

from agent_router.core.fit import FITS, reads_pdf
from agent_router.tools import document_text

INTEG = Path(__file__).resolve().parents[1] / "integrations" / "first-principles"
FP = "first-principles:first-principles"


def make_pdf(pages: list[list[list[str]]]) -> bytes:
    """A text PDF: each page is a list of paragraphs, each paragraph a list of lines."""

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    objs: list[bytes] = []
    n_pages = len(pages)
    page_ids = [4 + 2 * i for i in range(n_pages)]
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{i} 0 R" for i in page_ids)
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, paragraphs in enumerate(pages):
        ops = ["BT /F1 11 Tf 72 740 Td"]
        for p, lines in enumerate(paragraphs):
            if p:
                ops.append("0 -30 Td")
            for k, line in enumerate(lines):
                if k:
                    ops.append("0 -14 Td")
                ops.append(f"({esc(line)}) Tj")
        ops.append("ET")
        stream = "\n".join(ops).encode()
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {page_ids[i] + 1} 0 R >>".encode()
        )
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


FEES = make_pdf(
    [
        [
            ["Business Fees"],
            ["Limited Liability Companies:", "Articles of Organization ..... $100.00"],
            ["Certificate of Authority ..... $150.00"],
        ],
        [["Annual Report License Tax", "Minimum $60 or two-tenths of one mill"]],
        [["Corporations:", "Articles of Incorporation ..... $100.00"]],
    ]
)


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "fees.pdf").write_bytes(FEES)
    (tmp_path / "page.html").write_text("<!doctype html><html><body>hi</body></html>")
    (tmp_path / "blank.pdf").write_bytes(make_pdf([[[""]]]))
    return tmp_path


def test_whole_document_with_page_markers(workspace):
    out = document_text.extract(path="fees.pdf", root=workspace)
    assert out.startswith("fees.pdf: 3 page(s)")
    assert "[page 1]" in out and "[page 2]" in out and "[page 3]" in out
    assert "Articles of Organization ..... $100.00" in out
    assert out.index("[page 2]") < out.index("Annual Report") < out.index("[page 3]")


def test_pages_limit_what_is_read(workspace):
    out = document_text.extract(path="fees.pdf", pages="2-3", root=workspace)
    assert "pages 2-3 read" in out and "[page 1]" not in out and "Corporations" in out


def test_find_returns_passages_with_their_page(workspace):
    out = document_text.extract(
        path="fees.pdf", find="articles of organization, mill", root=workspace
    )
    assert "2 passage(s) containing" in out
    assert "[page 1] Limited Liability Companies: Articles of Organization ..... $100.00" in out
    assert "[page 2] Annual Report License Tax Minimum $60 or two-tenths of one mill" in out
    assert "Certificate of Authority" not in out  # another paragraph on page 1
    missing = document_text.extract(path="fees.pdf", find="franchise tax", root=workspace)
    assert missing.endswith("No passage contains: franchise tax")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({}, "exactly one of path or url"),
        ({"path": "fees.pdf", "url": "https://x/y.pdf"}, "exactly one"),
        ({"path": "../outside.pdf"}, "outside the workspace"),
        ({"path": "nope.pdf"}, "file not found"),
        ({"path": "page.html"}, "is an HTML page"),
        ({"path": "blank.pdf"}, "no text layer"),
        ({"path": "fees.pdf", "pages": "9"}, "no such pages"),
        ({"path": "fees.pdf", "pages": "x"}, "bad page range"),
        ({"path": "fees.pdf", "find": " , "}, "at least one term"),
        ({"url": "file:///etc/passwd"}, "http:// or https://"),
    ],
)
def test_errors_say_why(workspace, kwargs, message):
    with pytest.raises(ValueError, match=message):
        document_text.extract(**kwargs, root=workspace)


def test_a_damaged_pdf_is_an_error_not_a_crash(workspace):
    (workspace / "bad.pdf").write_bytes(b"%PDF-1.4\n" + b"\x00garbage" * 50)
    with pytest.raises(ValueError, match="bad.pdf"):
        document_text.extract(path="bad.pdf", root=workspace)


def test_long_documents_are_cut_with_a_pointer_to_pages_and_find(workspace, monkeypatch):
    monkeypatch.setattr(document_text, "MAX_OUTPUT_CHARS", 80)
    out = document_text.extract(path="fees.pdf", root=workspace)
    assert "[cut at page" in out and "ask for pages or use find" in out


@pytest.fixture
def server():
    seen: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            seen.append(self.headers.get("User-Agent", ""))
            if self.path == "/fees.pdf":
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.end_headers()
                self.wfile.write(FEES)
            else:
                self.send_response(403)
                self.end_headers()

        def log_message(self, *args):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}", seen
    httpd.shutdown()


def test_a_url_is_fetched_and_identifies_itself(server, tmp_path):
    base, seen = server
    out = document_text.extract(url=f"{base}/fees.pdf", find="Certificate", root=tmp_path)
    assert "[page 1] Certificate of Authority ..... $150.00" in out
    assert seen == [document_text.USER_AGENT]  # never posing as a browser
    with pytest.raises(ValueError, match="HTTP 403"):
        document_text.extract(url=f"{base}/blocked.pdf", root=tmp_path)


# --- the fit check, the MCP tool, the catalog entry and the trace ------------------------------


@pytest.mark.parametrize(
    ("tool_input", "fits"),
    [
        ({"url": "https://sos.example.gov/Business/Docs/Fees.pdf", "prompt": "fees"}, True),
        ({"url": "https://example.org/r.PDF?download=1", "prompt": "x"}, True),
        ({"url": "https://example.org/report.html", "prompt": "x"}, False),
        ({"command": "pdftotext -layout /tmp/r.pdf - | head -100"}, True),
        (
            {"command": "cd /tmp && curl -sL https://x.gov/a.pdf -o a.pdf && pdftotext a.pdf -"},
            True,
        ),
        ({"command": "pdfinfo /tmp/paper.pdf"}, True),
        ({"command": "pandoc /tmp/w.pdf -t plain | grep -i capacity"}, True),
        ({"command": "ls -la /tmp/*.pdf"}, False),
        ({"command": 'pandoc "$R" -o report.pdf --pdf-engine=typst'}, False),  # writing one
        ({"command": "pandoc --output=r.pdf r.md"}, False),
        ({"command": "grep -n fee notes.md"}, False),
        ({}, False),
    ],
)
def test_reads_pdf(tool_input, fits):
    assert reads_pdf(tool_input) is fits
    assert FITS["reads_pdf"] is reads_pdf


def test_mcp_serves_document_text(workspace):
    from agent_router.adapters import mcp_stdio

    assert "document_text" in mcp_stdio.TOOLS
    srv = mcp_stdio.build_server(workspace, ["document_text"])
    res = asyncio.run(srv.call_tool("document_text", {"path": "fees.pdf", "find": "mill"}))
    assert "two-tenths of one mill" in json.dumps(res, default=str)
    with pytest.raises(Exception) as err:
        asyncio.run(srv.call_tool("document_text", {"path": "page.html"}))
    assert "HTML page" in str(err.value) and type(err.value).__name__ == "ToolError"


def _catalog():
    from agent_router.contracts.integration import variables_for_catalog
    from agent_router.core.catalog import load_catalog

    path = INTEG / "catalog.yaml"
    return load_catalog(path, variables=variables_for_catalog(path))


def test_the_catalog_entry_points_at_the_served_tool():
    from agent_router.contracts.integration import load_integration
    from agent_router.core.types import HookPoint

    integ = load_integration(INTEG)
    entry = _catalog().get(integ.document_entry)
    assert entry.target == integ.document_tool and entry.fits == "reads_pdf"
    assert entry.replaces == ("Bash", "WebFetch") and entry.agents == (FP,)
    assert entry.license == "MIT"
    assert [e.id for e in _catalog().eligible(HookPoint.TOOL, "WebFetch", FP)] == ["document-text"]
    assert integ.document_tool.endswith("__document_text")
    hooks = (INTEG / "plugin" / "hooks" / "hooks.json").read_text()
    assert hooks.count(integ.document_tool) == 2  # traced on success and failure


def test_the_trace_records_a_document_call(tmp_path):
    spec = importlib.util.spec_from_file_location("fp_trace_doc", INTEG / "trace.py")
    tr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tr)
    rec = tr.handle(
        {
            "session_id": "s",
            "agent_type": FP,
            "agent_id": "a1",
            "cwd": str(tmp_path),
            "hook_event_name": "PostToolUse",
            "tool_name": tr.DOCUMENT_TOOL,
            "tool_input": {"url": "https://sos.example.gov/Fees.pdf", "find": "LLC"},
            "tool_response": [{"type": "text", "text": "https://sos...: 3 page(s)\n1 passage"}],
        },
        tmp_path,
        now="2026-10-17T10:00:00Z",
    )
    assert rec["kind"] == "document" and rec["host"] == "sos.example.gov"
    assert rec["find"] == "LLC" and rec["total_pages"] == 3
