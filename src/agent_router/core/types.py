"""Core value types shared by the router, deciders and adapters.

Nothing in ``agent_router.core`` may import a host SDK. Adapters translate host events
into ``RouterEvent`` and ``Decision`` back into host hook output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

NONE_ID = "none"
"""Reserved option id: no catalog entry fits, the agent's native path is enough."""


class HookPoint(StrEnum):
    PROMPT = "prompt"  # the user submitted a prompt
    TOOL = "tool"  # the agent is about to call a native tool
    SKILL = "skill"  # the agent is about to invoke a skill


class Action(StrEnum):
    SUGGEST = "suggest"  # advisory hint injected; the agent decides
    ENFORCE = "enforce"  # native call denied with a templated reason
    NATIVE = "native"  # decider chose none, or confidence below threshold
    SKIPPED = "skipped"  # a gate stopped routing before the decider was asked


@dataclass(frozen=True)
class OptionSpec:
    """One option of a Jev ``choice`` question, in Jev's structured-criteria form."""

    what: str
    not_for: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChoiceResult:
    """The Jev ``choice`` answer: the most likely option and the full distribution."""

    choice: str
    probabilities: dict[str, float]
    confidence: float
    backend: str = ""
    latency_ms: float = 0.0


@dataclass(frozen=True)
class RouterEvent:
    point: HookPoint
    session_id: str
    turn_id: int
    text: str
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    recent: tuple[str, ...] = ()


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str
    entry_id: str | None = None
    hint: str | None = None
    result: ChoiceResult | None = None
    options: tuple[str, ...] = field(default_factory=tuple)
