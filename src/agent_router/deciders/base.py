"""The decider protocol: every backend answers a Jev ``choice`` question.

Contract (mirrors TypeSafe Jev ``choice``, docs.typesafe.ai/primitives/choice.md):
- ``options`` maps option id -> OptionSpec and always contains ``none``.
- The result's ``choice`` is one of ``options``; ``probabilities`` has one entry per
  option and sums to 1; ``confidence`` is in [0, 1].
"""

from __future__ import annotations

from typing import Protocol

from agent_router.core.types import ChoiceResult, OptionSpec

MAX_OPTIONS = 255


class Decider(Protocol):
    name: str

    def decide(self, state: str, options: dict[str, OptionSpec]) -> ChoiceResult: ...


class DeciderError(RuntimeError):
    """Raised by a backend that could not answer. The router fails open to native."""


def recommended_threshold(decider: object) -> float | None:
    """The router threshold a decider was calibrated for, or None (use the config default).

    Read as an attribute (``LocalJevDecider`` sets it from calibration; the cascade derives
    it) so wrappers that forward attributes keep working.
    """
    value = getattr(decider, "recommended_threshold", None)
    return float(value) if value is not None else None
