"""Read-only tool logic for a conductor: route a step, verify a report, check the install.

These back the MCP tools ``route``, ``verify_summary`` and ``doctor`` that the stdio server
(:mod:`agent_router.adapters.mcp_stdio`) serves only when it runs with an integration
(``AGENT_ROUTER_INTEGRATION``, see :mod:`agent_router.contracts.integration`). Nothing here
names a particular plugin: the catalog, the manifest, the summary heading and the accepted
schema versions come from the integration directory and the plugin's resolved manifest.

All three are read-only and fail soft: a bad request raises ``ValueError`` (the MCP layer turns
it into a tool error), never anything else the caller has to catch. None of them can block: the
router runs in advisory mode, and ``verify_summary`` reports a contract status, it never
enforces one.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agent_router.contracts import integration as integ_mod
from agent_router.contracts.summary_block import read_contract
from agent_router.tools._paths import read_text_inside

ANSWER_CHARS = 1500
_ANSWER_HEADING = re.compile(r"^##[ \t]+Answer[ \t]*$", re.M)
_NEXT_SECTION = re.compile(r"^##[ \t]", re.M)


def _integration(env: Mapping[str, str] | None = None) -> integ_mod.Integration:
    directory = integ_mod.integration_dir(None, env)
    if directory is None:
        raise ValueError(f"no integration: {integ_mod.ENV_INTEGRATION} is not set")
    try:
        return integ_mod.load_integration(directory)
    except integ_mod.IntegrationError as exc:
        raise ValueError(str(exc)) from exc


def _state_root() -> Path:
    from agent_router.adapters.claude_code import state_root

    return state_root()


# --- route -------------------------------------------------------------------------------------


def route(
    text: str,
    point: str = "prompt",
    tool: str | None = None,
    tool_input_json: str | Mapping[str, Any] | None = None,
    agent_type: str | None = None,
) -> dict[str, Any]:
    """The routing decision for one step, as ``agent-router route --json`` prints it.

    Uses the integration's catalog (manifest variables filled in) and calibration and the
    local backend unless ``AGENT_ROUTER_BACKEND`` says otherwise. Advisory and in-memory: no
    audit record is written and nothing is enforced. ``agent_type`` is the subagent making a
    tool call (entries are scoped to an agent context); omit it for the main thread.
    """
    from agent_router import cli
    from agent_router.core.types import HookPoint, RouterEvent
    from agent_router.deciders import local

    if not isinstance(text, str):
        raise ValueError("text must be a string")
    try:
        hook_point = HookPoint(point)
    except ValueError as exc:
        raise ValueError(
            f"unknown point {point!r}; expected one of {', '.join(h.value for h in HookPoint)}"
        ) from exc
    tool_input: dict[str, Any] | None = None
    if isinstance(tool_input_json, Mapping):  # the MCP layer may hand over parsed JSON
        tool_input = dict(tool_input_json)
    elif tool_input_json:
        try:
            parsed = json.loads(tool_input_json)
        except ValueError as exc:
            raise ValueError(f"tool_input_json is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("tool_input_json must be a JSON object")
        tool_input = parsed
    integ = _integration()
    catalog = os.environ.get("AGENT_ROUTER_CATALOG", "").strip() or str(integ.dir / "catalog.yaml")
    calibration = os.environ.get("AGENT_ROUTER_CALIBRATION", "").strip()
    args = argparse.Namespace(
        backend=os.environ.get("AGENT_ROUTER_BACKEND", "").strip() or "local",
        catalog=catalog,
        mode="advisory",
        threshold=None,
        timeout=None,
        embedder=None,
    )
    try:
        cli._derive_integration(args)  # catalog variables and the default skip patterns
        args.never_block = cli._never_block(args)
        if not calibration and (integ.dir / "calibration.json").is_file():
            local.CALIBRATION_PATH = integ.dir / "calibration.json"
        else:
            cli._apply_calibration_env()
        router = cli._router(args, env=True)
        router.audit = type(router.audit)(None)  # in memory: this tool writes nothing
        if hook_point == HookPoint.SKILL and tool is None:
            tool = "Skill"
        event = RouterEvent(
            point=hook_point,
            session_id="mcp",
            turn_id=1,
            text=text,
            tool_name=tool,
            tool_input=tool_input,
            agent_type=agent_type or None,
        )
        decision = router.route(event)
    except cli.CliError as exc:
        raise ValueError(str(exc)) from exc
    except ValueError:
        raise
    except Exception as exc:  # never a crash: the caller gets the reason
        raise ValueError(f"routing failed: {type(exc).__name__}: {exc}") from exc
    res = decision.result
    return {
        "action": str(decision.action),
        "choice": res.choice if res else None,
        "entry_id": decision.entry_id,
        "probabilities": res.probabilities if res else {},
        "confidence": res.confidence if res else None,
        "reason": decision.reason,
        "hint": decision.hint,
        "options": list(decision.options),
        "backend": res.backend if res else args.backend,
        "latency_ms": res.latency_ms if res else None,
        "stages": list(res.stages) if res else [],
        "threshold": router.config.threshold,
        "applied_threshold": decision.threshold,
    }


# --- verify_summary ------------------------------------------------------------------------------


def _list(v: Any) -> list[Any]:
    return v if isinstance(v, list) else []


def _dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _count(values: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def block_decisions(block: Any) -> dict[str, Any] | None:
    """The decisions a conductor needs, read straight from a summary block (no prose). A field
    that is missing or of the wrong shape reads as None / empty; nothing is guessed."""
    if not isinstance(block, dict):
        return None
    rows = [a for a in _list(block.get("assumptions")) if isinstance(a, dict)]
    truths = [g for g in _list(block.get("ground_truths")) if isinstance(g, dict)]
    gate = block.get("gate")
    conclusion = _dict(block.get("conclusion"))
    recommendation = conclusion.get("recommendation")
    return {
        "run_mode": block.get("run_mode"),
        "conclusion": {
            "recommended": recommendation if isinstance(recommendation, str) else None,
            "confidence": conclusion.get("confidence"),
            "rests_on": conclusion.get("rests_on"),
        },
        "gate_cleared": _dict(gate).get("cleared") if isinstance(gate, dict) else None,
        "fix_repeat": _dict(gate).get("fix_repeat_fired") if isinstance(gate, dict) else None,
        "unverified_ground_truths": [
            f"{g.get('id')}?" for g in truths if g.get("read_at_source") is False
        ],
        "assumptions": {
            "count": len(rows),
            "by_type": _count([str(r.get("type") or "unspecified") for r in rows]),
            "by_verdict": _count([str(r.get("verdict") or "unspecified") for r in rows]),
        },
    }


def answer_section(text: str) -> str | None:
    """The report's whole ``## Answer`` section (to the next ``##`` heading), or None."""
    m = _ANSWER_HEADING.search(text)
    if not m:
        return None
    rest = text[m.end() :]
    nxt = _NEXT_SECTION.search(rest)
    body = (rest[: nxt.start()] if nxt else rest).strip()
    return body or None


def answer_excerpt(text: str, limit: int = ANSWER_CHARS) -> str | None:
    """The report's ``## Answer`` section (to the next ``##`` heading), cut at ``limit``."""
    body = answer_section(text)
    return body[:limit] if body else None


def reader_report_paths(analysis: Path) -> dict[str, str | None]:
    """The reader reports the agent writes beside its analysis: ``analysis-<UTC>.md`` becomes
    ``report-<UTC>.md`` and ``report-<UTC>.pdf``. Each is the path when the file exists."""
    name = analysis.name
    stamp = name[len("analysis-") : -len(".md")] if name.startswith("analysis-") else None
    if not stamp or not name.endswith(".md"):
        return {"md": None, "pdf": None}
    found: dict[str, str | None] = {}
    for ext in ("md", "pdf"):
        cand = analysis.parent / f"report-{stamp}.{ext}"
        found[ext] = str(cand) if cand.is_file() else None
    return found


# --- the report a conductor shows ----------------------------------------------------------------
#
# One renderer for every way a run is started (the conductor skill, or a plain prompt the
# router's hand-off hooks recognise), so the user reads the same report either way. Every line
# comes from the verification result; nothing is re-derived from the prose.

NOT_VALID_NOTE = (
    "the summary block could not be read or did not match the published schema, so the "
    "figures above are unverified"
)


def _item(label: str, value: Any) -> str:
    """One bullet; a multi-line value's later lines are indented so they stay inside it."""
    head, *rest = str(value).strip().split("\n")
    return "\n".join([f"- **{label}:** {head}", *(f"  {r}" if r.strip() else "" for r in rest)])


def check_lines(checks: Any) -> list[str]:
    """Report lines for the run checks recorded at compose time, only for what is not clean:
    install checks that did not all pass, a preflight that did not route the question to the
    agent, a check that could not run, or no record at all. A clean run adds nothing."""
    if not isinstance(checks, dict):
        return []
    if checks.get("missing"):
        return [
            "- **Run checks:** not recorded (no hand-off record for this run's prompt), so the "
            "install and routing checks are unknown"
        ]
    out = []
    health = checks.get("health") if isinstance(checks.get("health"), dict) else {}
    if not health.get("ran"):
        out.append(f"- **Install health:** not checked ({health.get('error') or 'unknown'})")
    else:
        flagged = [c for c in health.get("flagged") or [] if isinstance(c, dict)]
        if flagged:
            items = "; ".join(
                f"{c.get('status')} {c.get('name')}: {c.get('detail')}" for c in flagged
            )
            verdict = "FAIL" if not health.get("ok") else "warnings"
            out.append(f"- **Install health ({verdict}):** {items}")
    pre = checks.get("preflight") if isinstance(checks.get("preflight"), dict) else {}
    if not pre.get("ran"):
        out.append(f"- **Router preflight:** not run ({pre.get('error') or 'unknown'})")
    elif pre.get("delegate") is not True:
        score, threshold = pre.get("score"), pre.get("threshold")
        nums = (
            f" (score {score:.2f}, threshold {threshold:.2f})"
            if isinstance(score, (int, float)) and isinstance(threshold, (int, float))
            else ""
        )
        out.append(
            "- **Router preflight:** the router would not have routed this question to the "
            f"agent{nums}; it was analysed anyway"
        )
    return out


def _title(plugin_name: Any) -> str:
    return f"## {plugin_name} analysis: result" if plugin_name else "## Analysis: result"


def _gate_line(decisions: Mapping[str, Any]) -> str:
    cleared = decisions.get("gate_cleared")
    text = {True: "cleared", False: "not cleared"}.get(cleared, "not stated in the summary block")
    if decisions.get("fix_repeat") is True:
        text += " (after a Fix/Repeat pass)"
    return text


def render_report(result: Mapping[str, Any]) -> str:
    """The Markdown report of one verified analysis, from ``verify_summary``'s result."""
    decisions = result.get("decisions") if isinstance(result.get("decisions"), dict) else None
    status = str(result.get("contract_status"))
    plugin = result.get("plugin") if isinstance(result.get("plugin"), dict) else {}
    lines = [_title(plugin.get("name")), ""]
    excerpt = result.get("answer_excerpt")
    lines.append("**Answer**")
    lines.append("")
    if excerpt:
        lines.append(str(excerpt).rstrip())  # a cut can end mid-gap; no run of blank lines
        if result.get("answer_truncated"):
            lines.append("")
            lines.append(
                f"*(The Answer is cut at {ANSWER_CHARS:,} characters here; the full text is in "
                "the analysis.)*"
            )
    else:
        lines.append("*(The analysis has no `## Answer` section.)*")
    lines.append("")
    if decisions is not None:
        conclusion = (
            decisions.get("conclusion") if isinstance(decisions.get("conclusion"), dict) else {}
        )
        recommended = conclusion.get("recommended") or "not stated in the summary block"
        confidence = conclusion.get("confidence") or "not stated in the summary block"
        unverified = [str(g) for g in decisions.get("unverified_ground_truths") or []]
        lines.append(_item("Conclusion", recommended))
        lines.append(f"- **Confidence:** {confidence}")
        lines.append(f"- **Self-Audit Gate:** {_gate_line(decisions)}")
        lines.append(
            f"- **Ground truths not read at source:** {len(unverified)}"
            + (f" ({', '.join(unverified)})" if unverified else "")
        )
    else:
        lines.append(
            "- **Conclusion, confidence, gate, ground truths:** not available, because the "
            "summary block could not be read"
        )
    contract = f"`{status}`" + ("" if status == "valid" else f": {NOT_VALID_NOTE}")
    lines.append(f"- **Summary contract:** {contract}")
    checks = result.get("checks")
    lines += check_lines(checks)
    if plugin.get("source") == "cache" and not isinstance(checks, dict):
        lines.append(
            f"- **Note:** the {plugin.get('name') or 'integrated'} plugin was found in the Claude "
            "plugin cache, which can hold a stale copy of the agent"
        )
    paths = result.get("paths") if isinstance(result.get("paths"), dict) else {}
    reader = paths.get("reader_report") if isinstance(paths.get("reader_report"), dict) else {}
    found = [str(reader[k]) for k in ("md", "pdf") if reader.get(k)]
    lines += ["", "**Files**", ""]
    lines.append(f"- Analysis: `{paths.get('analysis')}`")
    lines.append(
        "- Reader report: " + (", ".join(f"`{p}`" for p in found) if found else "not found")
    )
    lines.append(f"- Trace: `{paths.get('trace_dir')}`")
    return "\n".join(lines) + "\n"


def render_missing(
    plugin_name: str | None, final_message: str | None = None, checks: Any = None
) -> str:
    """The report when no analysis file exists: say so, then the agent's message as it is."""
    out = [_title(plugin_name), "", "No analysis file was found."]
    flagged = check_lines(checks)
    if flagged:
        out += ["", *flagged, ""]
    if final_message:
        out += ["The agent's final message, unchanged:", "", final_message.strip()]
    return "\n".join(out) + "\n"


HANDOFF_DIR = "conductor"
_SHA256 = re.compile(r"[0-9a-f]{64}")


def handoff_checks(handoff: str | None) -> dict[str, Any] | None:
    """The run checks a hand-off record (``<state>/conductor/<handoff>.json``, written when the
    delegating prompt was composed) carries; ``{"missing": True}`` when there is no such record,
    None when none was asked for."""
    if not handoff:
        return None
    if not _SHA256.fullmatch(handoff):
        return {"missing": True}
    try:
        rec = json.loads((_state_root() / HANDOFF_DIR / f"{handoff}.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {"missing": True}
    checks = rec.get("checks") if isinstance(rec, dict) else None
    return checks if isinstance(checks, dict) else {"missing": True}


def verify_summary(
    path: str, *, root: Path | str | None = None, handoff: str | None = None
) -> dict[str, Any]:
    """Read the analysis at ``path`` (inside ``root``, default the working directory) against the
    plugin's published summary contract. Never raises for a bad report: that is a
    ``contract_status``. A path outside ``root`` or unreadable is a ``ValueError``. ``handoff``
    (the composed prompt's sha256) adds that run's recorded checks to the result and report."""
    root_path = Path(root if root is not None else os.getcwd()).resolve()
    text = read_text_inside(root_path, path)
    analysis = (root_path / path).resolve()
    integ = _integration()
    state = _state_root()
    resolved = integ_mod.resolve(integ, state_root=state)
    schema_path, source = integ_mod.schema_location(integ, state_root=state)
    contract = read_contract(
        text,
        heading=resolved.manifest.heading,
        schema_path=schema_path,
        accepted_versions=integ.accepted_schema_versions,
    )
    block = contract.pop("block", None)
    status = contract["contract_status"]
    usable = status in ("valid", "unsupported_version", "schema_violation")
    section = answer_section(text)
    out: dict[str, Any] = {
        "contract_status": status,
        "violations": contract["violations"],
        "schema": {
            "path": str(schema_path),
            "source": source,
            "block_version": contract.get("schema_version"),
            "accepted_versions": sorted(integ.accepted_schema_versions),
        },
        "decisions_verified": status == "valid",
        "decisions": block_decisions(block) if usable else None,
        "answer_excerpt": section[:ANSWER_CHARS] if section else None,
        "answer_truncated": bool(section) and len(section) > ANSWER_CHARS,
        "plugin": {"name": resolved.manifest.plugin_name, **resolved.record()},
        "paths": {
            "analysis": str(analysis),
            "reader_report": reader_report_paths(analysis),
            "trace_dir": str(state / "trace"),
        },
    }
    checks = handoff_checks(handoff)
    if checks is not None:
        out["checks"] = checks
    out["report_markdown"] = render_report(out)
    return out


# --- doctor ------------------------------------------------------------------------------------


def doctor_report() -> dict[str, Any]:
    """The install checks of ``agent-router doctor`` for this integration, as JSON."""
    from agent_router import doctor

    integ = _integration()
    checks = doctor.run_checks(integ.dir)
    return {"ok": not doctor.failed(checks), "checks": [c.record() for c in checks]}
