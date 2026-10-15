"""An integration directory: what the router derives from a plugin's manifest.

An *integration* is a directory next to a catalog that names, in ``descriptor.json``, the plugin
it is integrated with, the environment variable that points at that plugin's root, the pinned
fallback manifest and the router-side plugin that ships with it. From these and the resolved
manifest (:mod:`agent_router.contracts.manifest`) it derives what used to be typed into the
catalog and the hook script: the catalog variables and the default skip patterns.

Nothing here names a particular plugin; every name comes from the descriptor or the manifest.
Standard library only.

Descriptor keys (all strings; unknown keys are ignored)::

    descriptor_version   1
    expected_plugin      the integrated plugin's name; the plugin cache is searched under it
    plugin_root_env      environment variable that may name that plugin's root
    fallback_manifest    pinned manifest, relative to the integration directory
    own_plugin_json      the router-side plugin's ``plugin.json``, relative to the directory
    delegate_entry       catalog entry id of the "delegate to the agent" checkpoint
    calc_entry           catalog entry id of the exact-calculator checkpoint

Catalog variables (``${name}`` in a catalog file, see ``core.catalog.load_catalog``):

    fp.plugin_name  fp.agent_type  fp.command_prefix  fp.launcher  fp.output_dir  fp.output_glob
    self.plugin_name  self.calc_tool

``fp.*`` come from the manifest. ``self.plugin_name`` is the router-side plugin's name and
``self.calc_tool`` the name Claude Code gives its calculator tool.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_router.contracts.manifest import (
    Manifest,
    ManifestError,
    Resolved,
    default_cache_dirs,
    load_manifest,
    resolve_manifest,
)

DESCRIPTOR = "descriptor.json"
ENV_INTEGRATION = "AGENT_ROUTER_INTEGRATION"
ENV_CACHE = "AGENT_ROUTER_PLUGIN_CACHE"
"""Plugin cache directories (``os.pathsep``-separated) replacing ``~/.claude/plugins/cache``."""
MCP_SERVER = "agent_router"


class IntegrationError(ValueError):
    """The descriptor or the router-side plugin file is missing or malformed."""


@dataclass(frozen=True)
class Integration:
    dir: Path
    expected_plugin: str
    root_env: str
    fallback_path: Path
    own_plugin_name: str
    delegate_entry: str
    calc_entry: str

    @property
    def calc_tool(self) -> str:
        return f"mcp__plugin_{self.own_plugin_name}_{MCP_SERVER}__calc"

    def fallback(self) -> Manifest:
        return load_manifest(self.fallback_path)


def _text(data: Mapping[str, Any], key: str, where: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise IntegrationError(f"{where}: {key} must be a non-empty string")
    return value


def load_integration(directory: str | Path) -> Integration:
    root = Path(directory)
    path = root / DESCRIPTOR
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise IntegrationError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("descriptor_version") != 1:
        raise IntegrationError(f"{path}: descriptor_version 1 expected")
    plugin_json = root / _text(data, "own_plugin_json", path)
    try:
        own = json.loads(plugin_json.read_text(encoding="utf-8"))["name"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise IntegrationError(f"cannot read the plugin name from {plugin_json}: {exc}") from exc
    if not isinstance(own, str) or not own:
        raise IntegrationError(f"{plugin_json}: name must be a non-empty string")
    return Integration(
        dir=root,
        expected_plugin=_text(data, "expected_plugin", path),
        root_env=_text(data, "plugin_root_env", path),
        fallback_path=root / _text(data, "fallback_manifest", path),
        own_plugin_name=own,
        delegate_entry=_text(data, "delegate_entry", path),
        calc_entry=_text(data, "calc_entry", path),
    )


def integration_dir(
    catalog_path: str | Path | None = None, env: Mapping[str, str] | None = None
) -> Path | None:
    """The integration directory in force: ``AGENT_ROUTER_INTEGRATION``, else the catalog's own
    directory when it holds a descriptor, else None."""
    env = os.environ if env is None else env
    named = env.get(ENV_INTEGRATION, "").strip()
    if named:
        return Path(named)
    if catalog_path:
        parent = Path(catalog_path).resolve().parent
        if (parent / DESCRIPTOR).is_file():
            return parent
    return None


def cache_dirs(env: Mapping[str, str] | None = None) -> list[Path]:
    env = os.environ if env is None else env
    raw = env.get(ENV_CACHE)
    if raw is None:
        return default_cache_dirs()
    return [Path(p) for p in raw.split(os.pathsep) if p]


def recorded_root_file(integ: Integration, state_root: Path | None) -> Path | None:
    """Where a launcher records the plugin root it started the session with."""
    if state_root is None:
        return None
    return state_root / "integration" / f"{integ.expected_plugin}.root"


def resolve(
    integ: Integration,
    *,
    env: Mapping[str, str] | None = None,
    state_root: Path | None = None,
) -> Resolved:
    """Resolve the manifest of the integrated plugin (never raises for a bad manifest)."""
    env = os.environ if env is None else env
    return resolve_manifest(
        integ.expected_plugin,
        fallback=integ.fallback(),
        env=env,
        root_env=integ.root_env,
        recorded_root_file=recorded_root_file(integ, state_root),
        cache_dirs=cache_dirs(env),
    )


def variables(integ: Integration, manifest: Manifest) -> dict[str, str]:
    return {
        "fp.plugin_name": manifest.plugin_name,
        "fp.agent_type": manifest.agent_type,
        "fp.command_prefix": manifest.command_prefix,
        "fp.launcher": manifest.launcher,
        "fp.output_dir": manifest.output_dir,
        "fp.output_glob": manifest.output_glob,
        "self.plugin_name": integ.own_plugin_name,
        "self.calc_tool": integ.calc_tool,
    }


def skip_patterns(integ: Integration, manifest: Manifest) -> tuple[str, str]:
    """Default ``AGENT_ROUTER_SKIP_INPUT`` and ``AGENT_ROUTER_SKIP_PROMPT``.

    Input: the plugin's report directory, so the agent's own report commands are never routed.
    Prompt: a prompt that starts with one of the plugin's commands or with one of the
    router-side plugin's own commands (a conductor launched from there already delegates).
    """
    skip_input = re.escape(manifest.output_dir) + r"(?!\w)"  # \b would fail after a non-word end
    prefixes = [manifest.command_prefix, f"/{integ.own_plugin_name}:"]
    skip_prompt = r"^\s*(?:" + "|".join(re.escape(p) for p in dict.fromkeys(prefixes)) + ")"
    return skip_input, skip_prompt


def variables_for_catalog(
    catalog_path: str | Path | None,
    env: Mapping[str, str] | None = None,
    state_root: Path | None = None,
) -> dict[str, str] | None:
    """Catalog variables for ``catalog_path`` when an integration applies, else None."""
    directory = integration_dir(catalog_path, env)
    if directory is None:
        return None
    integ = load_integration(directory)
    return variables(integ, resolve(integ, env=env, state_root=state_root).manifest)


__all__ = [
    "ENV_CACHE",
    "ENV_INTEGRATION",
    "Integration",
    "IntegrationError",
    "ManifestError",
    "cache_dirs",
    "integration_dir",
    "load_integration",
    "resolve",
    "skip_patterns",
    "variables",
    "variables_for_catalog",
]
