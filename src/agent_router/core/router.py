"""The host-agnostic router: gates, Jev ``choice`` decision, templated hint, audit.

Rules (in order):
1. disabled, or hook point not enabled                    -> SKIPPED
2. pending call already targets the catalog (loop guard)  -> SKIPPED
3. no catalog entry eligible at this point / tool         -> SKIPPED
4. build the decider state from the event
5. ask the decider; any exception                         -> NATIVE (fail open)
6. choice outside the offered options                     -> treated as ``none``
7. ``none`` or p(choice) < threshold                      -> NATIVE
8. enforce mode at TOOL -> ENFORCE (deny) every time; marks the entry as suggested
9. entry already suggested this (session, turn) -> SKIPPED; else SUGGEST (hint)
Every call writes exactly one audit record.
"""

from __future__ import annotations

import json
import threading

from agent_router.core.audit import AuditLog
from agent_router.core.catalog import Catalog
from agent_router.core.config import RouterConfig
from agent_router.core.hints import render_deny, render_hint
from agent_router.core.types import (
    NONE_ID,
    Action,
    Decision,
    HookPoint,
    OptionSpec,
    RouterEvent,
)
from agent_router.deciders.base import Decider

OWN_TOOL_PREFIX = "mcp__agent_router__"
NONE_OPTION = OptionSpec("the agent's own tools are enough")
MAX_TOOL_INPUT = 500
MAX_RECENT = 3


def build_state(event: RouterEvent) -> str:
    """Decider input: prompt text, pending call (compact JSON) and recent context."""
    parts = [event.text]
    if event.point in (HookPoint.TOOL, HookPoint.SKILL):
        payload = json.dumps(
            event.tool_input or {}, separators=(",", ":"), ensure_ascii=False, default=str
        )
        parts.append(f"pending {event.tool_name}: {payload[:MAX_TOOL_INPUT]}")
    recent = event.recent[-MAX_RECENT:] if event.recent else ()
    parts.extend(f"previous: {line}" for line in recent)
    return "\n".join(parts)


class Router:
    def __init__(
        self,
        catalog: Catalog,
        decider: Decider,
        config: RouterConfig | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self.catalog = catalog
        self.decider = decider
        self.config = config if config is not None else RouterConfig()
        self.audit = audit if audit is not None else AuditLog(self.config.audit_path)
        self._suggested: set[tuple[str, int, str]] = set()
        self._lock = threading.Lock()

    def route(self, event: RouterEvent) -> Decision:
        state = build_state(event)
        decision = self._decide(event, state)
        self.audit.record(event, decision, self.catalog.version, self.config, state=state)
        return decision

    def _decide(self, event: RouterEvent, state: str) -> Decision:
        cfg = self.config
        # 1. enabled gates
        if not cfg.enabled or event.point not in cfg.points:
            return Decision(Action.SKIPPED, "disabled")
        # 2. loop guard
        tool_name = event.tool_name
        skill = (event.tool_input or {}).get("skill")
        if self.catalog.owns_target(tool_name, skill=skill if isinstance(skill, str) else None) or (
            tool_name is not None and tool_name.startswith(OWN_TOOL_PREFIX)
        ):
            return Decision(Action.SKIPPED, "own tool")
        # 3. structural eligibility
        eligible = self.catalog.eligible(event.point, tool_name)
        if not eligible:
            return Decision(Action.SKIPPED, "no eligible entries")
        options = {e.id: e.option() for e in eligible} | {NONE_ID: NONE_OPTION}
        option_ids = tuple(options)
        # 5. ask the decider, failing open
        try:
            result = self.decider.decide(state, options)
        except Exception as exc:  # any backend failure falls back to native
            return Decision(
                Action.NATIVE, f"decider error: {type(exc).__name__}: {exc}", options=option_ids
            )
        # 6. defensive: an unknown choice is treated as none (its text is never echoed)
        choice = result.choice if result.choice in options else NONE_ID
        if choice != result.choice:
            return Decision(
                Action.NATIVE,
                "decider returned an unknown option",
                result=result,
                options=option_ids,
            )
        # 7. abstain / threshold
        if choice == NONE_ID:
            return Decision(Action.NATIVE, "decider chose none", result=result, options=option_ids)
        prob = float(result.probabilities.get(choice, 0.0))
        if prob < cfg.threshold:
            return Decision(
                Action.NATIVE,
                f"p={prob:.3f} below threshold {cfg.threshold:.3f}",
                entry_id=choice,
                result=result,
                options=option_ids,
            )
        entry = self.catalog.get(choice)
        assert entry is not None  # eligible entries come from the catalog
        key = (event.session_id, event.turn_id, entry.id)
        # 8. enforce at TOOL denies every matching call; it marks but never consults the set
        if cfg.mode == "enforce" and event.point == HookPoint.TOOL:
            with self._lock:
                self._suggested.add(key)
            return Decision(
                Action.ENFORCE,
                f"p={prob:.3f} >= {cfg.threshold:.3f}, enforce mode",
                entry_id=entry.id,
                hint=render_deny(entry, tool_name or ""),
                result=result,
                options=option_ids,
            )
        # 9. advisory hints: once per (session, turn, entry)
        with self._lock:
            if key in self._suggested:
                return Decision(
                    Action.SKIPPED,
                    "already suggested this turn",
                    entry_id=entry.id,
                    result=result,
                    options=option_ids,
                )
            self._suggested.add(key)
        return Decision(
            Action.SUGGEST,
            f"p={prob:.3f} >= {cfg.threshold:.3f}",
            entry_id=entry.id,
            hint=render_hint(entry, event.point, prob),
            result=result,
            options=option_ids,
        )
