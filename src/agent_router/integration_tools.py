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


def answer_excerpt(text: str, limit: int = ANSWER_CHARS) -> str | None:
    """The report's ``## Answer`` section (to the next ``##`` heading), cut at ``limit``."""
    m = _ANSWER_HEADING.search(text)
    if not m:
        return None
    rest = text[m.end() :]
    nxt = _NEXT_SECTION.search(rest)
    body = (rest[: nxt.start()] if nxt else rest).strip()
    return body[:limit] if body else None


def verify_summary(path: str, *, root: Path | str | None = None) -> dict[str, Any]:
    """Read the analysis at ``path`` (inside ``root``, default the working directory) against the
    plugin's published summary contract. Never raises for a bad report: that is a
    ``contract_status``. A path outside ``root`` or unreadable is a ``ValueError``."""
    root_path = Path(root if root is not None else os.getcwd()).resolve()
    text = read_text_inside(root_path, path)
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
    return {
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
        "answer_excerpt": answer_excerpt(text),
    }


# --- doctor ------------------------------------------------------------------------------------


def doctor_report() -> dict[str, Any]:
    """The install checks of ``agent-router doctor`` for this integration, as JSON."""
    from agent_router import doctor

    integ = _integration()
    checks = doctor.run_checks(integ.dir)
    return {"ok": not doctor.failed(checks), "checks": [c.record() for c in checks]}
