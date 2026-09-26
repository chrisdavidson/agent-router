"""Router configuration (defaults, environment overrides)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agent_router.core.types import HookPoint

Mode = Literal["advisory", "enforce"]
MODES: tuple[Mode, ...] = ("advisory", "enforce")
_TRUTHY = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class RouterConfig:
    mode: Mode = "advisory"
    threshold: float = 0.5
    enabled: bool = True
    audit_path: Path | None = None
    points: tuple[HookPoint, ...] = tuple(HookPoint)

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {self.mode!r}")
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError(f"threshold must be in [0, 1], got {self.threshold}")

    @classmethod
    def from_env(cls) -> RouterConfig:
        """Read ``AGENT_ROUTER_MODE``, ``_THRESHOLD``, ``_DISABLED`` and ``_AUDIT``."""
        env = os.environ
        audit = env.get("AGENT_ROUTER_AUDIT", "").strip()
        return cls(
            mode=env.get("AGENT_ROUTER_MODE", "advisory").strip().lower(),  # type: ignore[arg-type]
            threshold=float(env.get("AGENT_ROUTER_THRESHOLD", "0.5")),
            enabled=env.get("AGENT_ROUTER_DISABLED", "").strip().lower() not in _TRUTHY,
            audit_path=Path(audit) if audit else None,
        )
