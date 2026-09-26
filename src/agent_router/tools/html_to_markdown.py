"""Convert a workspace HTML file or HTML text to Markdown (python-markdownify, MIT)."""

import re
from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import ATX, MarkdownConverter

from agent_router.tools._paths import one_source, read_text_inside

_DROP = ("script", "style", "noscript", "template")


def convert(path: str | None = None, html: str | None = None, *, root: Path) -> str:
    """Return Markdown for HTML from ``path`` (inside ``root``) or ``html``.

    Script/style elements are removed with their contents; headings use ATX (``#``) style.
    """
    one_source(path, html, "html")
    raw = read_text_inside(root, path) if path is not None else html
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup.find_all(_DROP):
        tag.decompose()
    if soup.head is not None:
        soup.head.decompose()
    md = MarkdownConverter(heading_style=ATX, bullets="-").convert_soup(soup)
    md = re.sub(r"[ \t]+\n", "\n", md)
    return re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
