#!/usr/bin/env python3
"""The deterministic steps of the conductor skill (CONDUCT-02): preflight, compose, verify.

The skill (``plugin/skills/analyze/SKILL.md``) sequences these and makes the judgement calls;
everything that can be decided by code is decided here, so it is unit-tested offline and the
skill stays short. Each sub-command prints one JSON object on stdout and exits 0, or prints
``{"error": ...}`` and exits 1. Nothing here blocks anything, and nothing here edits an
analysis: ``verify`` only reads it (D-02, D-09).

    conduct.py preflight "<question>"
    conduct.py compose "<question>" [--mode full|focused-<technique>] [--domain D]
                                    [--constraint C]... [--ground-truth G]...
    conduct.py verify <analysis-path> [--root DIR]
    conduct.py record-root <plugin-root>
    conduct.py latest-analysis [--cwd DIR]

It is thin over :mod:`agent_router.integration_tools`, the same logic the plugin's MCP tools
``route`` and ``verify_summary`` serve. Every name (agent type, tool names, output glob, command
prefix) comes from the integration descriptor and the resolved manifest, never from a literal
here; see ``MANIFEST.md``.

``compose`` follows the publisher's Input Contract (its agent body, "## Input Contract"): a
problem statement, and optionally a domain, key constraints and known ground truths. The
question goes in verbatim as the problem statement. It adds one capability line naming the
calculator tools when the plugin serves them, and nothing else: the agent owns its procedure.
It also leaves ``<state>/conductor/<sha256 of the prompt>.json`` so the trace can recognise the
hand-off as the conductor's (CONDUCT-05; ``trace.py`` reads it).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
try:
    from agent_router import integration_tools
    from agent_router.adapters.claude_code import state_root
    from agent_router.contracts import integration as integ_mod
except ImportError:  # a checkout without an install finds the package through ../../src
    sys.path.insert(0, str(HERE.parents[1] / "src"))
    from agent_router import integration_tools
    from agent_router.adapters.claude_code import state_root
    from agent_router.contracts import integration as integ_mod

HANDOFF_DIR = "conductor"
MODE_RE = re.compile(r"full|focused-[a-z][a-z-]*")
_TOOLS_FLAG = re.compile(r"--tools\s+([A-Za-z0-9_,]+)")


class ConductError(ValueError):
    """A request the conductor cannot act on; the message is printed as the JSON error."""


def _integration() -> integ_mod.Integration:
    os.environ.setdefault(integ_mod.ENV_INTEGRATION, str(HERE))
    try:
        return integ_mod.load_integration(integ_mod.integration_dir(None) or HERE)
    except integ_mod.IntegrationError as exc:
        raise ConductError(str(exc)) from exc


def _resolved(integ: integ_mod.Integration) -> integ_mod.Resolved:
    return integ_mod.resolve(integ, state_root=state_root())


def _plugin_dir(integ: integ_mod.Integration) -> Path:
    """The router-side plugin's root: the directory above its ``.claude-plugin/plugin.json``."""
    return (integ.dir / _own_plugin_json(integ)).resolve().parent.parent


def _own_plugin_json(integ: integ_mod.Integration) -> str:
    data = json.loads((integ.dir / "descriptor.json").read_text(encoding="utf-8"))
    return str(data["own_plugin_json"])


# --- preflight ---------------------------------------------------------------------------------


def preflight(question: str) -> dict[str, Any]:
    """Would the router delegate this question to the integrated agent? (``route`` at the
    prompt point with the integration catalog; advisory, in memory, nothing written.)"""
    integ = _integration()
    try:
        res = integration_tools.route(question, point="prompt")
    except ValueError as exc:
        raise ConductError(str(exc)) from exc
    probs = res.get("probabilities") or {}
    applied = res.get("applied_threshold")
    return {
        "delegate": res.get("entry_id") == integ.delegate_entry,
        "entry": res.get("entry_id"),
        "score": probs.get(integ.delegate_entry),
        "threshold": applied if applied is not None else res.get("threshold"),
        "reason": res.get("reason"),
    }


# --- compose -----------------------------------------------------------------------------------


def calc_tools(integ: integ_mod.Integration, resolved: integ_mod.Resolved) -> list[str]:
    """Names of the calculator tools the plugin serves, or [] when they are not reachable.

    Read from the plugin's own files, no live MCP call: the manifest must list
    ``exact-arithmetic`` among ``capabilities_used``, ``.mcp.json`` must declare the server and
    its launcher must exist, and the launcher's ``--tools`` list must include the tool.
    """
    if "exact-arithmetic" not in resolved.manifest.capabilities_used:
        return []
    plugin = _plugin_dir(integ)
    try:
        servers = json.loads((plugin / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
        command = str(servers[integ_mod.MCP_SERVER]["command"])
        launcher = Path(command.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin)))
        match = _TOOLS_FLAG.search(launcher.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError, TypeError):
        return []
    served = set(match.group(1).split(",")) if match else set()
    out = []
    if "calc" in served:
        out.append(integ.calc_tool)
    if "calc_script" in served:
        out.append(integ.calc_script_tool)
    return out


def capability_line(integ: integ_mod.Integration, tools: Sequence[str]) -> str | None:
    if not tools:
        return None
    parts = []
    if integ.calc_tool in tools:
        parts.append(f"{integ.calc_tool} for a single expression")
    if integ.calc_script_tool in tools:
        parts.append(f"{integ.calc_script_tool} for a straight-line script")
    return "Exact arithmetic is available: " + " and ".join(parts) + "; load them with ToolSearch."


def build_prompt(
    question: str,
    *,
    mode: str = "full",
    domain: str | None = None,
    constraints: Sequence[str] = (),
    ground_truths: Sequence[str] = (),
    capability: str | None = None,
) -> str:
    """The delegating prompt: the Input Contract's fields, the question verbatim first."""
    lines = [f"Problem statement: {question}"]
    if domain:
        lines.append(f"Domain: {domain}")
    for label, items in (("Key constraints", constraints), ("Known ground truths", ground_truths)):
        if items:
            lines.append(f"{label}:")
            lines.extend(f"- {item}" for item in items)
    if mode != "full":  # the agent's Step 0 honours a pre-set MODE and skips phrase detection
        lines.append(f"MODE: {mode}")
    if capability:
        lines.append(capability)
    return "\n".join(lines)


def compose(
    question: str,
    *,
    mode: str = "full",
    domain: str | None = None,
    constraints: Sequence[str] = (),
    ground_truths: Sequence[str] = (),
    now: datetime | None = None,
) -> dict[str, Any]:
    """The composed prompt, and the hand-off record that lets the trace recognise it."""
    if not question.strip():
        raise ConductError("the question is empty")
    if not MODE_RE.fullmatch(mode):
        raise ConductError(f"mode must be 'full' or 'focused-<technique>', got {mode!r}")
    integ = _integration()
    resolved = _resolved(integ)
    prompt = build_prompt(
        question,
        mode=mode,
        domain=domain,
        constraints=constraints,
        ground_truths=ground_truths,
        capability=capability_line(integ, calc_tools(integ, resolved)),
    )
    sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    record = {
        "sha256": sha,
        "composed_at": (now or datetime.now(UTC)).isoformat(),
        "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
    }
    directory = state_root() / HANDOFF_DIR
    try:
        directory.mkdir(parents=True, exist_ok=True)
        tmp = directory / f".{sha}.tmp"
        tmp.write_text(json.dumps(record), encoding="utf-8")
        tmp.replace(directory / f"{sha}.json")
    except OSError:
        pass  # the hand-off record only labels the trace; the prompt is still good
    return {
        "prompt": prompt,
        "sha256": sha,
        "agent_type": resolved.manifest.agent_type,
        "launcher": resolved.manifest.launcher,
    }


# --- verify ------------------------------------------------------------------------------------


def reader_report_paths(analysis: Path) -> dict[str, str | None]:
    """The reader reports the agent writes beside its analysis: ``analysis-<UTC>.md`` becomes
    ``report-<UTC>.md`` and ``report-<UTC>.pdf``. Each is the path when the file exists."""
    name = analysis.name
    stamp = name[len("analysis-") : -len(".md")] if name.startswith("analysis-") else None
    if not stamp or not name.endswith(".md"):
        return {"md": None, "pdf": None}
    found = {}
    for ext in ("md", "pdf"):
        cand = analysis.parent / f"report-{stamp}.{ext}"
        found[ext] = str(cand) if cand.is_file() else None
    return found


def verify(path: str, *, root: str | None = None) -> dict[str, Any]:
    """The contract reading of the analysis at ``path``, plus where its reports and trace are."""
    _integration()
    base = Path(root) if root else Path.cwd()
    analysis = (base / path).resolve()
    try:
        out = integration_tools.verify_summary(str(analysis), root=base)
    except ValueError as exc:
        raise ConductError(str(exc)) from exc
    return {
        **out,
        "paths": {
            "analysis": str(analysis),
            "reader_report": reader_report_paths(analysis),
            "trace_dir": str(state_root() / "trace"),
        },
    }


# --- record-root and latest-analysis -----------------------------------------------------------


def record_root(plugin_root: str) -> dict[str, Any]:
    """Record the integrated plugin's root so later hook and trace calls on this machine
    resolve it (source ``recorded``). The directory must be that plugin's own root."""
    integ = _integration()
    root = Path(plugin_root).expanduser().resolve()
    manifest = root / ".claude-plugin" / "plugin.json"
    try:
        name = json.loads(manifest.read_text(encoding="utf-8")).get("name")
    except (OSError, ValueError, AttributeError) as exc:
        raise ConductError(f"{root} is not a plugin root: cannot read {manifest}: {exc}") from exc
    if name != integ.expected_plugin:
        raise ConductError(f"{root} is the plugin {name!r}, not {integ.expected_plugin!r}")
    target = integ_mod.recorded_root_file(integ, state_root())
    assert target is not None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(root) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ConductError(f"cannot write {target}: {exc}") from exc
    return {"recorded": str(root), "file": str(target), "resolved": _resolved(integ).record()}


def latest_analysis(cwd: str | None = None) -> dict[str, Any]:
    """The newest analysis file under ``cwd`` (the manifest's output glob), or null."""
    integ = _integration()
    base = Path(cwd) if cwd else Path.cwd()
    pattern = _resolved(integ).manifest.output_glob
    try:
        found = [p for p in base.glob(pattern) if p.is_file()]
    except (OSError, ValueError):
        found = []
    newest = max(found, key=lambda p: (p.stat().st_mtime, p.name), default=None)
    return {"path": str(newest) if newest else None}


# --- command line ------------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="conduct.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("preflight", help="would the router delegate this question?")
    p.add_argument("question")
    p = sub.add_parser("compose", help="the delegating prompt and its hand-off record")
    p.add_argument("question")
    p.add_argument("--mode", default="full", help="full (default) or focused-<technique>")
    p.add_argument("--domain")
    p.add_argument("--constraint", action="append", default=[], dest="constraints")
    p.add_argument("--ground-truth", action="append", default=[], dest="ground_truths")
    p = sub.add_parser("verify", help="read an analysis against the summary contract")
    p.add_argument("analysis")
    p.add_argument("--root", help="directory the path must be inside (default: the cwd)")
    p = sub.add_parser("record-root", help="record the plugin root for later resolution")
    p.add_argument("plugin_root")
    p = sub.add_parser("latest-analysis", help="the newest analysis file under a directory")
    p.add_argument("--cwd")
    sub.add_parser("doctor", help="the install checks (agent-router doctor) as JSON")
    return ap


def run(argv: Sequence[str] | None = None) -> dict[str, Any]:
    args = _parser().parse_args(argv)
    if args.command == "preflight":
        return preflight(args.question)
    if args.command == "compose":
        return compose(
            args.question,
            mode=args.mode,
            domain=args.domain,
            constraints=args.constraints,
            ground_truths=args.ground_truths,
        )
    if args.command == "verify":
        return verify(args.analysis, root=args.root)
    if args.command == "record-root":
        return record_root(args.plugin_root)
    if args.command == "doctor":
        return integration_tools.doctor_report()
    return latest_analysis(args.cwd)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        result = run(argv)
    except ConductError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
