"""The integration manifest a plugin publishes, and how its location is found.

A plugin that agent-router is integrated with may publish ``<plugin root>/references/
integration.json``: its identity as the router needs it (agent type, command prefix, where its
reports are written, its summary schema). This module reads that file and finds it. Nothing
here knows which plugin it is: the plugin name, the environment variable naming its root and
the pinned fallback are parameters. Standard library only.

The format is ``MANIFEST.md`` next to the integration. ``manifest_version`` is an integer;
the format is add-only, so a key this reader does not know is ignored, and removing or
renaming a key bumps the version. A version this reader does not know is refused.

Every plugin root is looked up in this order (:func:`resolve_manifest`):

1. ``root_env`` (an environment variable naming the plugin root),
2. a *recorded* root file (the root a launcher wrote down for this session),
3. the copy Claude Code has installed, from ``installed_plugins.json`` beside the cache,
4. the Claude plugin cache, ``<cache>/*/<plugin>/*/``, highest version first,
5. the pinned fallback manifest.

A manifest that is unknown, malformed or points at a schema file that is not there never
raises: the fallback manifest is used, with the root kept when it is known, and the reason is
recorded as a warning. The order and outcome are reported in :class:`Resolved`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

MANIFEST_RELPATH = Path("references") / "integration.json"
SUPPORTED_VERSIONS = frozenset({1})
SOURCES = ("env", "recorded", "installed", "cache", "fallback+root", "fallback")
INSTALLED_RECORD = "installed_plugins.json"  # Claude Code's record, beside its plugin cache
CACHE_STALE_WARNING = (
    "plugin root found in the Claude plugin cache: the cache can hold a stale copy, and a "
    "session started with --plugin-dir uses another root"
)


class ManifestError(ValueError):
    """The manifest is unreadable, malformed, or of a version this reader does not know."""


@dataclass(frozen=True)
class Manifest:
    manifest_version: int
    plugin_name: str
    agent_type: str
    command_prefix: str
    launcher: str
    output_dir: str
    output_glob: str
    schema: str  # relative to the plugin root
    heading: str
    schema_version: int  # what the publisher emits; the versions accepted stay the reader's
    examples_dir: str  # relative to the plugin root
    capabilities_used: tuple[str, ...] = ()

    def record(self) -> dict[str, Any]:
        return {"manifest_version": self.manifest_version, "plugin_name": self.plugin_name}


@dataclass(frozen=True)
class Resolved:
    manifest: Manifest
    plugin_root: Path | None
    source: str  # one of SOURCES
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def record(self) -> dict[str, Any]:
        """What is kept in the session state and the trace: how the manifest was found."""
        return {
            "source": self.source,
            "plugin_root": str(self.plugin_root) if self.plugin_root else None,
            "manifest_version": self.manifest.manifest_version,
            "warnings": list(self.warnings),
        }


# --- loading ---------------------------------------------------------------------------------


def _str(obj: Mapping[str, Any], key: str, where: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{where}{key}: expected a non-empty string")
    return value


def _obj(obj: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = obj.get(key)
    if not isinstance(value, dict):
        raise ManifestError(f"{key}: expected an object")
    return value


def _relpath(value: str, where: str) -> str:
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts:
        raise ManifestError(f"{where}: must be a relative path inside the plugin, got {value!r}")
    return value


def parse_manifest(data: Any) -> Manifest:
    """Validate parsed JSON as a manifest; :class:`ManifestError` says which key is wrong."""
    if not isinstance(data, dict):
        raise ManifestError("manifest must be a JSON object")
    version = data.get("manifest_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ManifestError("manifest_version: expected an integer")
    if version not in SUPPORTED_VERSIONS:
        known = ", ".join(str(v) for v in sorted(SUPPORTED_VERSIONS))
        raise ManifestError(f"manifest_version {version} is not supported (known: {known})")
    output = _obj(data, "output")
    summary = _obj(data, "summary")
    schema_version = summary.get("schema_version")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise ManifestError("summary.schema_version: expected an integer")
    caps = data.get("capabilities_used", [])
    if not isinstance(caps, list) or not all(isinstance(c, str) for c in caps):
        raise ManifestError("capabilities_used: expected a list of strings")
    return Manifest(
        manifest_version=version,
        plugin_name=_str(data, "plugin_name", ""),
        agent_type=_str(data, "agent_type", ""),
        command_prefix=_str(data, "command_prefix", ""),
        launcher=_str(data, "launcher", ""),
        output_dir=_str(output, "dir", "output."),
        output_glob=_str(output, "glob", "output."),
        schema=_relpath(_str(summary, "schema", "summary."), "summary.schema"),
        heading=_str(summary, "heading", "summary."),
        schema_version=schema_version,
        examples_dir=_relpath(_str(data, "examples_dir", ""), "examples_dir"),
        capabilities_used=tuple(caps),
    )


def load_manifest(path: str | Path) -> Manifest:
    """Read and validate one manifest file; :class:`ManifestError` on any problem."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestError(f"cannot read {path}: {exc}") from exc
    return parse_manifest(data)


# --- resolution ------------------------------------------------------------------------------


def default_cache_dirs() -> list[Path]:
    return [Path.home() / ".claude" / "plugins" / "cache"]


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _version_key(root: Path) -> tuple[int, ...]:
    """A root's version as numbers, from its ``plugin.json`` else its directory name; ``()``
    when neither parses, which ranks below every real version."""
    try:
        data = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        raw = data.get("version") if isinstance(data, dict) else None
    except (OSError, ValueError):
        raw = None
    for text in (raw, root.name):
        if isinstance(text, str):
            parts = text.strip().lstrip("v").split("-")[0].split(".")
            if parts and all(p.isdigit() for p in parts):
                return tuple(int(p) for p in parts)
    return ()


def _installed_root(cache_dirs: Sequence[Path], plugin: str, cwd: Path) -> Path | None:
    """The root Claude Code's install record names for ``plugin`` (``<plugin>@<marketplace>``),
    or None. A project-scoped install counts only inside its project; among the rest the most
    recently updated wins. A missing or unreadable record is not an error: the cache is next."""
    found: list[tuple[str, Path]] = []
    for cache in cache_dirs:
        try:
            data = json.loads((cache.parent / INSTALLED_RECORD).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        plugins = data.get("plugins") if isinstance(data, dict) else None
        if not isinstance(plugins, dict):
            continue
        for key, entries in plugins.items():
            if not (isinstance(key, str) and key.split("@")[0] == plugin):
                continue
            for entry in entries if isinstance(entries, list) else []:
                if not isinstance(entry, dict) or not isinstance(entry.get("installPath"), str):
                    continue
                project = entry.get("projectPath")
                if isinstance(project, str) and not cwd.is_relative_to(Path(project)):
                    continue
                path = Path(entry["installPath"])
                if path.is_dir():
                    found.append((str(entry.get("lastUpdated") or ""), path))
    return max(found, key=lambda f: f[0])[1] if found else None


def _cache_candidates(cache_dirs: Sequence[Path], plugin: str) -> list[Path]:
    """Plugin roots in the cache (``<cache>/<marketplace>/<plugin>/<version>/``), best first:
    a root that publishes a manifest before one that does not (a leftover stub of an old
    version keeps only ``plugin.json``), then the highest version, then the newest file."""
    found: list[Path] = []
    for cache in cache_dirs:
        try:
            found += [
                p
                for p in cache.glob(f"*/{plugin}/*")
                if (p / MANIFEST_RELPATH).is_file()
                or (p / ".claude-plugin" / "plugin.json").is_file()
            ]
        except OSError:
            continue
    # never rank by a directory's mtime alone: removing an old version's files touches it
    found.sort(
        key=lambda p: (
            (p / MANIFEST_RELPATH).is_file(),
            _version_key(p),
            _mtime(p / MANIFEST_RELPATH) or _mtime(p / ".claude-plugin" / "plugin.json"),
        ),
        reverse=True,
    )
    return found


def _read_recorded(path: Path | None) -> Path | None:
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return Path(text) if text else None


def _with_root(
    root: Path, fallback: Manifest, source: str, plugin: str, warnings: list[str]
) -> Resolved:
    """The result for a plugin root: its own manifest when it has a usable one, else the
    fallback manifest kept with that root."""
    path = root / MANIFEST_RELPATH
    if not path.is_file():
        warnings.append(f"no manifest at {path}: using the pinned fallback with this root")
        return Resolved(fallback, root, "fallback+root", tuple(warnings))
    try:
        manifest = load_manifest(path)
        if manifest.plugin_name != plugin:
            raise ManifestError(f"plugin_name {manifest.plugin_name!r} is not {plugin!r}")
        if not (root / manifest.schema).is_file():
            raise ManifestError(f"summary.schema {manifest.schema!r} is not under {root}")
    except ManifestError as exc:
        warnings.append(f"manifest {path} ignored ({exc}): using the pinned fallback")
        return Resolved(fallback, root, "fallback+root", tuple(warnings))
    return Resolved(manifest, root, source, tuple(warnings))


def resolve_manifest(
    expected_plugin: str,
    *,
    fallback: Manifest | str | Path,
    env: Mapping[str, str] | None = None,
    root_env: str = "",
    recorded_root_file: Path | None = None,
    cache_dirs: Sequence[Path] | None = None,
    cwd: Path | None = None,
) -> Resolved:
    """Find the plugin root and its manifest; never raises for a bad or missing manifest.

    ``fallback`` is a :class:`Manifest` or the path of the pinned fallback file (an unreadable
    fallback does raise :class:`ManifestError`: it is shipped with the integration, so a bad
    one is a build error, not a runtime condition).
    """
    env = os.environ if env is None else env
    base = fallback if isinstance(fallback, Manifest) else load_manifest(fallback)
    warnings: list[str] = []
    raw = env.get(root_env, "").strip() if root_env else ""
    if raw:
        if Path(raw).is_dir():
            return _with_root(Path(raw), base, "env", expected_plugin, warnings)
        warnings.append(f"{root_env}={raw} is not a directory: ignored")
    recorded = _read_recorded(recorded_root_file)
    if recorded is not None:
        if recorded.is_dir():
            return _with_root(recorded, base, "recorded", expected_plugin, warnings)
        warnings.append(f"recorded plugin root {recorded} is not a directory: ignored")
    dirs = list(default_cache_dirs() if cache_dirs is None else cache_dirs)
    installed = _installed_root(dirs, expected_plugin, Path.cwd() if cwd is None else cwd)
    if installed is not None:
        return _with_root(installed, base, "installed", expected_plugin, warnings)
    candidates = _cache_candidates(dirs, expected_plugin)
    if candidates:
        warnings.append(CACHE_STALE_WARNING)
        return _with_root(candidates[0], base, "cache", expected_plugin, warnings)
    warnings.append("no plugin root found: using the pinned fallback")
    return Resolved(base, None, "fallback", tuple(warnings))
