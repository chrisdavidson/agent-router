"""Files and lines of code per language for a workspace directory (agent-router, MIT)."""

import os
from pathlib import Path

from agent_router.tools._paths import resolve_inside

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
}

LANGUAGES = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".hpp": "C++",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".sh": "Shell",
    ".zsh": "Shell",
    ".bash": "Shell",
    ".sql": "SQL",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "CSS",
    ".md": "Markdown",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".xml": "XML",
}

MAX_FILES = 50_000
MAX_FILE_BYTES = 5 * 1024 * 1024
TOP_N = 5


def _count_lines(path: Path) -> int | None:
    """Line count, or None for binary/unreadable/oversized files."""
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:8192]:
        return None
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


def stats(path: str = ".", *, root: Path) -> str:
    """Markdown tables of files/lines per language and the largest files under ``path``."""
    base = Path(root).resolve()
    top = resolve_inside(root, path)
    if not top.is_dir():
        raise ValueError(f"not a directory: {path}")

    per_lang: dict[str, list[int]] = {}
    files: list[tuple[int, str]] = []
    seen = 0
    for dirpath, dirnames, filenames in os.walk(top):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            fp = Path(dirpath) / name
            lang = LANGUAGES.get(fp.suffix.lower())
            if lang is None or fp.is_symlink():
                continue
            seen += 1
            if seen > MAX_FILES:
                raise ValueError(f"too many files (> {MAX_FILES}); narrow the path")
            lines = _count_lines(fp)
            if lines is None:
                continue
            counts = per_lang.setdefault(lang, [0, 0])
            counts[0] += 1
            counts[1] += lines
            files.append((lines, fp.relative_to(base).as_posix()))

    rel = top.relative_to(base).as_posix() or "."
    if not per_lang:
        return f"No source files found under `{rel}`.\n"

    out = [
        f"## Code stats for `{rel}`",
        "",
        "| Language | Files | Lines |",
        "|---|---:|---:|",
    ]
    for lang, (n, lines) in sorted(per_lang.items(), key=lambda kv: (-kv[1][1], kv[0])):
        out.append(f"| {lang} | {n} | {lines} |")
    total_files = sum(v[0] for v in per_lang.values())
    total_lines = sum(v[1] for v in per_lang.values())
    out.append(f"| **Total** | **{total_files}** | **{total_lines}** |")
    out += ["", f"### Largest files (top {TOP_N})", "", "| File | Lines |", "|---|---:|"]
    for lines, name in sorted(files, key=lambda f: (-f[0], f[1]))[:TOP_N]:
        out.append(f"| {name} | {lines} |")
    return "\n".join(out) + "\n"
