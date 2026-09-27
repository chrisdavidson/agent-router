"""Workspace path confinement shared by the file-reading tools."""

from pathlib import Path

MAX_FILE_BYTES = 10 * 1024 * 1024


def resolve_inside(root: Path, path: str) -> Path:
    """Resolve ``path`` (relative to ``root``, or absolute) and require it to stay inside root.

    Symlinks are resolved on both sides, so a link pointing out of the workspace is rejected.
    """
    base = Path(root).resolve()
    target = (base / path).resolve()
    if not target.is_relative_to(base):
        raise ValueError(f"path {path!r} is outside the workspace")
    return target


def read_text_inside(root: Path, path: str) -> str:
    target = resolve_inside(root, path)
    if not target.is_file():
        raise ValueError(f"file not found: {path}")
    if target.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"file too large (> {MAX_FILE_BYTES} bytes): {path}")
    return target.read_text(encoding="utf-8", errors="replace")


def one_source(path: str | None, text: str | None, kind: str) -> None:
    if (path is None) == (text is None):
        raise ValueError(f"give exactly one of path or {kind}")
