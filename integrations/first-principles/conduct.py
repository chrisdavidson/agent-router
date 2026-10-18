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
    conduct.py report [<analysis-path>] [--since EPOCH] [--root DIR] [--markdown]
    conduct.py hook    (hook JSON on stdin: the hand-off hooks, see below)
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

``report`` renders the one report the user is shown after a run, from ``verify``'s result
(``integration_tools.render_report``). The conductor skill shows it verbatim, and so does a run
started from a plain prompt, so the two ways of starting a run end in the same report.

``hook`` is the hand-off pair behind ``plugin/bin/handoff-hook`` that gives a plain-prompt run the
conductor's shape. Both halves are steering, never blocking: they emit ``updatedInput`` or
``additionalContext`` and nothing else (D-02, D-08).

- ``PreToolUse`` on the main session's ``Agent`` call to the integrated agent rewrites its prompt
  to the one ``compose`` would build. The question is the user's prompt verbatim when the router
  routed this turn's prompt to the agent (the conductor passes its argument verbatim too), else
  the main session's own prompt. A prompt ``compose`` already wrote (a conductor run) is left
  alone.
- ``PostToolUse`` on that call hands the main session the report: rendered at once when the agent
  ran in the foreground, or, for a background run (the host's default), the ``report`` command to
  run when the completion notification arrives. A conductor run is left to the skill.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
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
LAUNCHERS = ("conductor", "router-hook")
SHOW_VERBATIM = (
    "Your reply about the analysis is this report exactly as given, with nothing before or "
    "after it: do not summarise, reword, re-derive or add to it, and do not edit or re-run the "
    "analysis."
)
SINCE_SKEW_S = 5  # an analysis file written this long before the hook fired still counts
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


# --- run checks: the same for every way a run starts ------------------------------------------
#
# Neither the conductor nor the hand-off hook stops a run (D-02 never blocks; the user chose
# "both proceed and warn", 2026-10-16). Both record the install checks and the router's preflight
# for the question in the hand-off record at compose time, and the report shows any that are not
# clean, so a broken install or an out-of-scope question reads the same either way.

HEALTH_BUDGET_S = 6.0  # the hand-off hook has 12 s (bin/_failopen.sh); compose stays well inside
PREFLIGHT_BUDGET_S = 4.0


def _bounded(fn: Any, budget: float) -> tuple[bool, Any]:
    """``(True, fn())`` within ``budget`` seconds, ``(False, error text)`` on error or timeout.
    The worker is a daemon thread, so a hung check never holds the process open."""
    box: dict[str, Any] = {}

    def work() -> None:
        try:
            box["value"] = fn()
        except Exception as exc:  # noqa: BLE001 - any failure is recorded, never raised
            box["error"] = f"{type(exc).__name__}: {exc}"

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    worker.join(budget)
    if worker.is_alive():
        return False, f"timed out after {budget:g} s"
    if "error" in box:
        return False, box["error"]
    return True, box.get("value")


def run_checks(question: str) -> dict[str, Any]:
    """The install checks (``doctor``) and the router's preflight for ``question``, compactly."""
    ok, health = _bounded(integration_tools.doctor_report, HEALTH_BUDGET_S)
    if ok and isinstance(health, dict):
        flagged = [
            {"name": c.get("name"), "status": c.get("status"), "detail": c.get("detail")}
            for c in health.get("checks") or []
            if isinstance(c, dict) and c.get("status") != "PASS"
        ]
        health_rec: dict[str, Any] = {"ran": True, "ok": bool(health.get("ok")), "flagged": flagged}
    else:
        health_rec = {"ran": False, "error": str(health)}
    ok, pre = _bounded(lambda: preflight(question), PREFLIGHT_BUDGET_S)
    pre_rec = (
        {"ran": True, **pre} if ok and isinstance(pre, dict) else {"ran": False, "error": str(pre)}
    )
    return {"health": health_rec, "preflight": pre_rec}


# --- compose -----------------------------------------------------------------------------------


def calc_tools(integ: integ_mod.Integration, resolved: integ_mod.Resolved) -> list[str]:
    """Names of the calculator (and document-text) tools the plugin serves, or [] when they are
    not reachable.

    Read from the plugin's own files, no live MCP call: ``.mcp.json`` must declare the server and
    its launcher must exist, and the launcher's ``--tools`` list must include the tool. The
    calculator tools also need the manifest to list ``exact-arithmetic`` among
    ``capabilities_used``; ``document_text`` needs the descriptor to name its catalog entry.
    """
    arithmetic = "exact-arithmetic" in resolved.manifest.capabilities_used
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
    if "calc" in served and arithmetic:
        out.append(integ.calc_tool)
    if "calc_script" in served and arithmetic:
        out.append(integ.calc_script_tool)
    if "document_text" in served and integ.document_entry:
        out.append(integ.document_tool)
    return out


def capability_line(integ: integ_mod.Integration, tools: Sequence[str]) -> str | None:
    if not tools:
        return None
    parts = []
    if integ.calc_tool in tools:
        parts.append(f"{integ.calc_tool} for a single expression")
    if integ.calc_script_tool in tools:
        parts.append(f"{integ.calc_script_tool} for a script (loops, lists, small functions)")
    line = (
        "Exact arithmetic is available: " + " and ".join(parts) + "; load them with ToolSearch."
        if parts
        else ""
    )
    if integ.document_tool in tools:
        line += (" " if line else "") + (
            f"To read a PDF (a link or a workspace file) as its own text, page by page or only "
            f"the passages naming given terms, use {integ.document_tool} (load it with "
            "ToolSearch); WebFetch summarises a PDF instead of returning it."
        )
    return line or None


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
    launcher: str = "conductor",
    checks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The composed prompt, and the hand-off record that lets the trace recognise it.
    ``launcher`` says who composed it: the conductor skill, or the router's hand-off hook.
    The record also carries the run checks (``run_checks``; ``checks`` overrides them, for tests),
    which the report shows when they are not clean. Nothing here stops the run."""
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
        "launcher": launcher if launcher in LAUNCHERS else "conductor",
        "checks": checks if checks is not None else run_checks(question),
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
        "checks": record["checks"],
    }


# --- verify ------------------------------------------------------------------------------------


reader_report_paths = integration_tools.reader_report_paths


def verify(path: str, *, root: str | None = None, handoff: str | None = None) -> dict[str, Any]:
    """The contract reading of the analysis at ``path``, plus where its reports and trace are."""
    _integration()
    base = Path(root) if root else Path.cwd()
    analysis = (base / path).resolve()
    try:
        return integration_tools.verify_summary(str(analysis), root=base, handoff=handoff)
    except ValueError as exc:
        raise ConductError(str(exc)) from exc


def _newest_analysis(integ: integ_mod.Integration, base: Path, since: float | None) -> Path | None:
    pattern = _resolved(integ).manifest.output_glob
    try:
        found = [p for p in base.glob(pattern) if p.is_file()]
        if since is not None:
            found = [p for p in found if p.stat().st_mtime >= since]
    except (OSError, ValueError):
        found = []
    return max(found, key=lambda p: (p.stat().st_mtime, p.name), default=None)


def report(
    path: str | None = None,
    *,
    since: float | None = None,
    root: str | None = None,
    final_message: str | None = None,
    handoff: str | None = None,
) -> dict[str, Any]:
    """The report the user is shown after a run, as ``{"report_markdown", "verification"}``.

    ``path`` is the analysis the agent named; without it, the newest analysis under ``root``
    (default the cwd) written at or after ``since`` (epoch seconds). No analysis found: the
    report says so and carries ``final_message`` unchanged. A path outside ``root`` is read
    with the analysis's own project directory as the root (the agent named it). ``handoff`` is
    the composed prompt's sha256: its record's run checks are added to the report, and a missing
    record is said so, never silently dropped."""
    integ = _integration()
    checks = _checks_for(handoff)
    base = Path(root) if root else Path.cwd()
    analysis = Path(path) if path else _newest_analysis(integ, base, since)
    if analysis is None or not (base / analysis).is_file():
        name = _resolved(integ).manifest.plugin_name
        return {
            "report_markdown": integration_tools.render_missing(name, final_message, checks),
            "verification": None,
        }
    analysis = (base / analysis).resolve()
    if not analysis.is_relative_to(base.resolve()):
        base = analysis.parent.parent  # <project>/<output dir>/analysis-*.md
    result = verify(str(analysis), root=str(base), handoff=handoff)
    return {"report_markdown": result["report_markdown"], "verification": result}


_checks_for = integration_tools.handoff_checks


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
    newest = _newest_analysis(integ, Path(cwd) if cwd else Path.cwd(), None)
    return {"path": str(newest) if newest else None}


# --- hook: the hand-off pair for a run started from a plain prompt -----------------------------

HANDOFF_TTL_S = 3600  # as trace.py: an older hand-off record is not recognised


def handoff_record(prompt: str, now: datetime | None = None) -> dict[str, Any] | None:
    """The hand-off record ``compose`` left for ``prompt``, when it is under an hour old."""
    sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    try:
        rec = json.loads((state_root() / HANDOFF_DIR / f"{sha}.json").read_text(encoding="utf-8"))
        composed = datetime.fromisoformat(rec["composed_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if composed.tzinfo is None:
        composed = composed.replace(tzinfo=UTC)
    age = ((now or datetime.now(UTC)) - composed).total_seconds()
    if not isinstance(rec, dict) or rec.get("sha256") != sha or not 0 <= age <= HANDOFF_TTL_S:
        return None
    return rec


def _routed_prompt(integ: integ_mod.Integration, payload: dict[str, Any]) -> str | None:
    """This turn's user prompt, when the router suggested the integrated agent for it."""
    from agent_router.adapters.claude_code import load_state, safe_name, turn_id

    session = safe_name(str(payload.get("session_id") or ""))
    state = load_state(state_root() / "sessions" / f"{session}.json")
    prompts = [p for p in state.get("prompts", []) if isinstance(p, str)]
    if not prompts or not prompts[-1].strip():
        return None
    turn = turn_id(payload, len(prompts))
    suggested = {
        (t, e)
        for t, e in (state.get("suggested") or [])
        if isinstance(t, int) and isinstance(e, str)
    }
    return prompts[-1] if (turn, integ.delegate_entry) in suggested else None


def _record_rewrite(original: str, composed: dict[str, Any]) -> None:
    """Leave ``<state>/conductor/from-<sha256 of the original prompt>.json``. The trace records
    the delegation at PreToolUse in parallel with this hook, so it sees the original prompt; at
    the run's end it reads this file to learn the prompt the agent actually got."""
    sha = hashlib.sha256(original.encode("utf-8")).hexdigest()
    record = {
        "original_sha256": sha,
        "composed_sha256": composed["sha256"],
        "launcher": "router-hook",
        "composed_at": datetime.now(UTC).isoformat(),
        "prompt_names_calc": "Exact arithmetic is available" in composed["prompt"],
    }
    directory = state_root() / HANDOFF_DIR
    try:
        directory.mkdir(parents=True, exist_ok=True)
        tmp = directory / f".from-{sha}.tmp"
        tmp.write_text(json.dumps(record), encoding="utf-8")
        tmp.replace(directory / f"from-{sha}.json")
    except OSError:
        pass  # only the trace's label depends on it


def _is_handoff(payload: dict[str, Any], agent_type: str) -> bool:
    inp = payload.get("tool_input")
    return (
        not payload.get("agent_type")  # the main session's call, not one inside a subagent
        and payload.get("tool_name") == "Agent"
        and isinstance(inp, dict)
        and inp.get("subagent_type") == agent_type
    )


def _context(event: str, text: str) -> dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def pre_agent(payload: dict[str, Any]) -> dict[str, Any]:
    """PreToolUse: give the delegating prompt the conductor's composed form (``updatedInput``)."""
    integ = _integration()
    agent_type = _resolved(integ).manifest.agent_type
    if not _is_handoff(payload, agent_type):
        return {}
    inp = dict(payload["tool_input"])
    prompt = str(inp.get("prompt") or "")
    if not prompt.strip() or handoff_record(prompt) is not None:
        return {}  # nothing to hand over, or compose already wrote it (a conductor run)
    question = _routed_prompt(integ, payload) or prompt
    composed = compose(question, launcher="router-hook")
    if composed["prompt"] == prompt:
        return {}
    _record_rewrite(prompt, composed)
    inp["prompt"] = composed["prompt"]
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": inp}}


def _message_text(response: Any) -> str:
    """The agent's final message from an Agent ``tool_response`` (text blocks joined)."""
    content = response.get("content") if isinstance(response, dict) else response
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            str(b.get("text") or "")
            for b in content
            if isinstance(b, dict) and b.get("type", "text") == "text"
        ]
        return "\n".join(p for p in parts if p)
    return ""


def named_analysis(integ: integ_mod.Integration, message: str) -> str | None:
    """The last analysis path the agent's final message names (the manifest's output glob)."""
    manifest = _resolved(integ).manifest
    stem = re.escape(manifest.output_dir) + r"/analysis-[^\s`'\"/]+\.md"
    found = re.findall(r"(?:/[^\s`'\"]*?/)?" + stem, message)
    return found[-1] if found else None


def report_command(since: int, handoff: str) -> str:
    conduct = HERE / "plugin" / "bin" / "conduct"
    return f'"{conduct}" report --markdown --handoff {handoff} --since {since}'


def post_agent(payload: dict[str, Any], now: float | None = None) -> dict[str, Any]:
    """PostToolUse: hand the main session the report, or how to get it for a background run."""
    integ = _integration()
    agent_type = _resolved(integ).manifest.agent_type
    if not _is_handoff(payload, agent_type):
        return {}
    prompt = str(payload["tool_input"].get("prompt") or "")
    sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    rec = handoff_record(prompt)
    if rec is not None and rec.get("launcher", "conductor") == "conductor":
        return {}  # the conductor skill reports its own run
    now = time.time() if now is None else now
    response = payload.get("tool_response")
    duration = payload.get("duration_ms")
    started = now - (duration / 1000 if isinstance(duration, (int, float)) else 0)
    since = int(started) - SINCE_SKEW_S
    if isinstance(response, dict) and (
        response.get("status") == "async_launched" or response.get("isAsync") is True
    ):
        return _context(
            "PostToolUse",
            f"[agent-router] The {agent_type} agent is running in the background. When its "
            "completion notification arrives, run this command with Bash and show its output "
            f"as your report of the run (add the analysis path the agent names, if any, after "
            f"`report`): {report_command(since, sha)}\n{SHOW_VERBATIM}",
        )
    message = _message_text(response)
    cwd = str(payload.get("cwd") or os.getcwd())
    try:
        out = report(
            named_analysis(integ, message),
            since=since,
            root=cwd,
            final_message=message,
            handoff=sha,
        )
    except ConductError:
        out = report(None, since=since, root=cwd, final_message=message, handoff=sha)
    return _context(
        "PostToolUse",
        f"[agent-router] The {agent_type} run has finished. {SHOW_VERBATIM}\n\n"
        + out["report_markdown"],
    )


def hook(payload: Any) -> dict[str, Any]:
    """One hand-off hook call; ``{}`` for anything it does not handle (fail open)."""
    if not isinstance(payload, dict):
        return {}
    event = payload.get("hook_event_name")
    try:
        if event == "PreToolUse":
            return pre_agent(payload)
        if event == "PostToolUse":
            return post_agent(payload)
    except (ConductError, OSError, ValueError, KeyError, TypeError):
        return {}
    return {}


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
    p = sub.add_parser("report", help="the report shown to the user after a run")
    p.add_argument("analysis", nargs="?")
    p.add_argument("--since", type=float, help="newest analysis written at/after (epoch s)")
    p.add_argument("--root", help="directory to look in (default: the cwd)")
    p.add_argument("--markdown", action="store_true", help="print only the Markdown report")
    p.add_argument("--handoff", help="sha256 of the composed prompt: add its run checks")
    sub.add_parser("hook", help="the hand-off hooks: hook JSON on stdin, hook JSON on stdout")
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
    if args.command == "report":
        return report(args.analysis, since=args.since, root=args.root, handoff=args.handoff)
    if args.command == "hook":
        try:
            payload = json.loads(sys.stdin.read() or "null")
        except ValueError:
            payload = None
        return hook(payload)
    if args.command == "record-root":
        return record_root(args.plugin_root)
    if args.command == "doctor":
        return integration_tools.doctor_report()
    return latest_analysis(args.cwd)


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        result = run(argv)
    except ConductError as exc:
        if argv[:1] == ["hook"]:  # a hook answers {} rather than an error (fail open)
            print("{}")
            return 0
        print(json.dumps({"error": str(exc)}))
        return 1
    if argv[:1] == ["hook"]:
        print(json.dumps(result))  # one line: bin/_failopen.sh vets a single-line object
    elif argv[:1] == ["report"] and "--markdown" in argv:
        sys.stdout.write(result["report_markdown"])
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
