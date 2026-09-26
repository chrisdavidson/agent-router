"""Cascade decider: a fast local first stage, confirmed by Jev unless it is confidently ``none``.

``decide(state, options)``:

1. Ask ``primary`` (the MIT local classifier). If it chose ``none`` with
   ``p(none) >= native_gate``, return its answer (``backend="cascade:local"``): no escalation.
2. Otherwise ask ``confirm`` (Jev) and return its answer (``backend="cascade:<its backend>"``).
3. If ``confirm`` raises ``DeciderError`` (other exceptions are bugs and propagate), fall
   back conservatively (``backend="cascade:local-fallback"``): the
   primary answer, but a non-``none`` choice with ``p(choice) < fallback_keep`` is moved to
   ``none`` (its probability mass goes to ``none``). If the primary failed too, raise
   ``DeciderError`` (the router fails open to native).

Circuit breaker: after ``breaker_failures`` (3) consecutive confirm failures the confirm
stage is skipped for ``breaker_cooldown`` (60 s): the same local fallback is returned at once,
its confirm stage marked ``skipped="circuit-open"``. After the cooldown one call is tried;
success closes the circuit, failure reopens it. Thread-safe.

Every result carries ``stages``: one plain dict per stage asked (role, backend, choice,
probabilities, confidence, latency, error). ``last_stages`` keeps the latest ones.

Calibration: ``calibration.json["cascade"]`` (``agent-router calibrate-cascade``) holds the
``native_gate`` and router ``threshold`` fit on the cal split. It applies only when it is
feasible and was fit for the same catalog version and local embedder.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from agent_router.core.types import NONE_ID, ChoiceResult, OptionSpec
from agent_router.deciders._math import entropy_confidence
from agent_router.deciders.base import Decider, DeciderError

log = logging.getLogger(__name__)

DEFAULT_NATIVE_GATE = 0.9
FALLBACK_KEEP = 0.95
CALIBRATION_KEY = "cascade"
LOCAL_BACKEND = "cascade:local"
FALLBACK_BACKEND = "cascade:local-fallback"
BREAKER_FAILURES = 3  # consecutive confirm failures that open the circuit
BREAKER_COOLDOWN = 60.0  # seconds the confirm stage is skipped once open
CIRCUIT_OPEN = "circuit-open"


def _stage(
    role: str,
    decider: object,
    result: ChoiceResult | None,
    latency_ms: float,
    error: BaseException | None = None,
    skipped: str | None = None,
) -> dict[str, Any]:
    """One stage record. ``error`` (exception text, possibly remote content) is private:
    ``core.types.public_stages`` drops it for the timeline and UI; the audit truncates it."""
    if result is None:
        return {
            "role": role,
            "backend": str(getattr(decider, "name", "") or role),
            "choice": None,
            "probabilities": {},
            "confidence": None,
            "latency_ms": float(latency_ms),
            "failed": error is not None,
            "error_type": type(error).__name__ if error is not None else None,
            "error": f"{type(error).__name__}: {error}" if error is not None else None,
            "skipped": skipped,
        }
    return {
        "role": role,
        "backend": str(result.backend or getattr(decider, "name", "")),
        "choice": str(result.choice),
        "probabilities": {str(k): float(v) for k, v in result.probabilities.items()},
        "confidence": float(result.confidence),
        "latency_ms": float(result.latency_ms),
        "failed": False,
        "error_type": None,
        "error": None,
        "skipped": None,
    }


def none_biased(result: ChoiceResult, keep: float = FALLBACK_KEEP) -> ChoiceResult:
    """``result`` with an unsure non-``none`` choice moved to ``none`` (mass moved too)."""
    choice = result.choice
    probs = {k: float(v) for k, v in result.probabilities.items()}
    if choice == NONE_ID or probs.get(choice, 0.0) >= keep:
        return result
    probs[NONE_ID] = probs.get(NONE_ID, 0.0) + probs.get(choice, 0.0)
    probs[choice] = 0.0
    total = sum(probs.values())
    if total > 0:
        probs = {k: v / total for k, v in probs.items()}
    else:
        probs = {k: (1.0 if k == NONE_ID else 0.0) for k in probs}
    return replace(
        result,
        choice=NONE_ID,
        probabilities=probs,
        confidence=entropy_confidence(probs.values()),
    )


class CascadeDecider:
    name = "cascade"

    def __init__(
        self,
        primary: Decider,
        confirm: Decider,
        native_gate: float = DEFAULT_NATIVE_GATE,
        *,
        threshold: float | None = None,
        fallback_keep: float = FALLBACK_KEEP,
        breaker_failures: int = BREAKER_FAILURES,
        breaker_cooldown: float = BREAKER_COOLDOWN,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.primary = primary
        self.confirm = confirm
        self.native_gate = float(native_gate)
        self.fallback_keep = float(fallback_keep)
        self._threshold = threshold
        self.last_stages: list[dict[str, Any]] = []
        self.breaker_failures = int(breaker_failures)
        self.breaker_cooldown = float(breaker_cooldown)
        self._clock = clock
        self._breaker_lock = threading.Lock()
        self._failures = 0
        self._open_until = 0.0

    # -- circuit breaker on the confirm stage ------------------------------------------

    def _circuit_open(self) -> bool:
        with self._breaker_lock:
            return self._failures >= self.breaker_failures and self._clock() < self._open_until

    def _record(self, ok: bool) -> None:
        with self._breaker_lock:
            if ok:
                self._failures = 0
                return
            self._failures += 1
            if self._failures >= self.breaker_failures:
                self._open_until = self._clock() + self.breaker_cooldown
                log.warning(
                    "cascade confirm stage failed %d times in a row; skipping it for %.0fs",
                    self._failures,
                    self.breaker_cooldown,
                )

    @property
    def recommended_threshold(self) -> float | None:
        """The calibrated cascade threshold, else the confirm stage's (never the local one:
        most final answers come from the confirm stage)."""
        if self._threshold is not None:
            return float(self._threshold)
        value = getattr(self.confirm, "recommended_threshold", None)
        return float(value) if value is not None else None

    @property
    def timeout(self) -> float | None:
        return getattr(self.confirm, "timeout", None)

    @timeout.setter
    def timeout(self, value: float) -> None:
        if hasattr(self.confirm, "timeout"):
            self.confirm.timeout = value  # type: ignore[attr-defined]

    def decide(self, state: str, options: dict[str, OptionSpec]) -> ChoiceResult:
        start = time.perf_counter()
        stages: list[dict[str, Any]] = []

        def finish(result: ChoiceResult, backend: str) -> ChoiceResult:
            self.last_stages = stages
            return replace(
                result,
                backend=backend,
                latency_ms=(time.perf_counter() - start) * 1000.0,
                stages=tuple(stages),
            )

        first: ChoiceResult | None = None
        t0 = time.perf_counter()
        try:
            first = self.primary.decide(state, options)
        except Exception as exc:  # a broken first stage just means: ask the confirm stage
            log.warning("cascade primary stage failed: %s", exc)
            stages.append(_stage("primary", self.primary, None, _ms(t0), exc))
        else:
            stages.append(_stage("primary", self.primary, first, first.latency_ms))
            p_none = float(first.probabilities.get(NONE_ID, 0.0))
            if first.choice == NONE_ID and p_none >= self.native_gate:
                return finish(first, LOCAL_BACKEND)

        if self._circuit_open():  # Jev keeps failing: don't wait on it, fall back
            stages.append(_stage("confirm", self.confirm, None, 0.0, skipped=CIRCUIT_OPEN))
            self.last_stages = stages
            if first is None:
                raise DeciderError("cascade primary failed and the confirm circuit is open")
            return finish(none_biased(first, self.fallback_keep), FALLBACK_BACKEND)

        t1 = time.perf_counter()
        try:
            second = self.confirm.decide(state, options)
        except DeciderError as exc:  # network, HTTP, deadline, malformed answer
            self._record(ok=False)
            stages.append(_stage("confirm", self.confirm, None, _ms(t1), exc))
            self.last_stages = stages
            if first is None:
                raise DeciderError(f"both cascade stages failed; confirm: {exc}") from exc
            log.warning("cascade confirm stage failed (%s); local fallback", exc)
            return finish(none_biased(first, self.fallback_keep), FALLBACK_BACKEND)
        self._record(ok=True)
        stages.append(_stage("confirm", self.confirm, second, second.latency_ms))
        return finish(second, f"cascade:{second.backend or getattr(self.confirm, 'name', '')}")


def _ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000.0


def load_cascade_calibration(
    *, catalog_version: str | None, embedder: str | None
) -> dict[str, Any] | None:
    """The ``cascade`` block of the active calibration file, if it applies here."""
    from agent_router.deciders import local

    path = local.CALIBRATION_PATH  # read at call time: tests point it elsewhere
    if not path.is_file():
        return None
    try:
        block = json.loads(path.read_text()).get(CALIBRATION_KEY)
    except (ValueError, AttributeError) as exc:
        log.warning("ignoring unreadable calibration %s: %s", path, exc)
        return None
    if not isinstance(block, dict):
        return None
    if block.get("feasible") is False:
        log.warning("cascade calibration in %s is not feasible; using defaults", path)
        return None
    for name, want in (("catalog_version", catalog_version), ("embedder", embedder)):
        if want is None or block.get(name) != want:
            log.warning(
                "cascade calibration in %s was fit for %s=%r, not %r; using defaults",
                path,
                name,
                block.get(name),
                want,
            )
            return None
    try:
        gate = float(block["native_gate"])
        thr = block.get("threshold")
        return {"native_gate": gate, "threshold": float(thr) if thr is not None else None}
    except (KeyError, TypeError, ValueError) as exc:
        log.warning("ignoring malformed cascade calibration in %s: %s", path, exc)
        return None
