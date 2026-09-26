"""Hosted Jev decider: asks TypeSafe Jev a ``choice`` question over the catalog options.

Two transports carry the same request body:

- ``openrouter``: ``POST https://openrouter.ai/api/alpha/decisions`` with model
  ``~typesafe/jev-latest`` and ``OPENROUTER_API_KEY``.
- ``typesafe``: ``POST https://api.typesafe.ai/v1/systemone`` with model ``jev-latest`` and
  ``TYPESAFE_API_KEY``.

``transport="auto"`` picks openrouter when ``OPENROUTER_API_KEY`` is set, else typesafe when
``TYPESAFE_API_KEY`` is set. An explicit ``api_key`` with ``auto`` picks openrouter for
``sk-or-`` keys and typesafe otherwise. ``model`` / ``base_url`` default per transport.

Jev's probabilities are normalised into the decider contract: every option key present,
unknown keys dropped, negatives clamped, sum 1. A choice outside the options is an error.
"""

from __future__ import annotations

import math
import os
import time
from typing import Any, Literal

import httpx

from agent_router.core.types import NONE_ID, ChoiceResult, OptionSpec
from agent_router.deciders.base import MAX_OPTIONS, DeciderError

Transport = Literal["auto", "openrouter", "typesafe"]

INSTRUCTIONS = (
    "Which catalog tool, if any, fits this agent step? "
    "Choose none if the agent's own tools are enough."
)
NONE_WHAT = "No catalog tool fits; the agent's own tools are enough for this step."

_TRANSPORTS: dict[str, dict[str, str]] = {
    "openrouter": {
        "env": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/alpha",
        "path": "/decisions",
        "model": "~typesafe/jev-latest",
    },
    "typesafe": {
        "env": "TYPESAFE_API_KEY",
        "base_url": "https://api.typesafe.ai",
        "path": "/v1/systemone",
        "model": "jev-latest",
    },
}


def criteria(options: dict[str, OptionSpec]) -> dict[str, dict[str, Any]]:
    """Jev structured criteria: ``{id: {what, not_for?, examples?}}``, empty lists omitted."""
    out: dict[str, dict[str, Any]] = {}
    for oid, spec in options.items():
        what = spec.what.strip() if spec.what else ""
        if not what and oid == NONE_ID:
            what = NONE_WHAT
        crit: dict[str, Any] = {"what": what}
        if spec.not_for:
            crit["not_for"] = list(spec.not_for)
        if spec.examples:
            crit["examples"] = list(spec.examples)
        out[oid] = crit
    return out


class TypeSafeJevDecider:
    name = "jev"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 2.0,
        client: httpx.Client | None = None,
        transport: Transport = "auto",
    ) -> None:
        if transport not in ("auto", *_TRANSPORTS):
            raise ValueError(f"transport must be auto, openrouter or typesafe, not {transport!r}")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.transport: Transport = transport
        self._client = client

    # -- transport ---------------------------------------------------------

    def _resolve(self) -> tuple[str, str, str, str]:
        """Return (transport, url, model, api_key) or raise DeciderError."""
        name: str = self.transport
        key = self.api_key
        if name == "auto":
            if key:
                name = "openrouter" if key.startswith("sk-or-") else "typesafe"
            elif os.environ.get("OPENROUTER_API_KEY"):
                name = "openrouter"
            elif os.environ.get("TYPESAFE_API_KEY"):
                name = "typesafe"
            else:
                raise DeciderError("no Jev API key: set OPENROUTER_API_KEY or TYPESAFE_API_KEY")
        cfg = _TRANSPORTS[name]
        key = key or os.environ.get(cfg["env"])
        if not key:
            raise DeciderError(f"no Jev API key for transport {name}: set {cfg['env']}")
        url = (self.base_url or cfg["base_url"]).rstrip("/") + cfg["path"]
        return name, url, self.model or cfg["model"], key

    # -- decide ------------------------------------------------------------

    def decide(self, state: str, options: dict[str, OptionSpec]) -> ChoiceResult:
        start = time.perf_counter()
        if NONE_ID not in options:
            raise DeciderError(f"options must include {NONE_ID!r}")
        if len(options) > MAX_OPTIONS:
            raise DeciderError(f"{len(options)} options exceeds the maximum of {MAX_OPTIONS}")
        _, url, model, key = self._resolve()
        body = {
            "state": state,
            "model": model,
            "questions": {
                "route": {
                    "type": "choice",
                    "instructions": INSTRUCTIONS,
                    "criteria": criteria(options),
                }
            },
        }
        headers = {"Authorization": f"Bearer {key}"}
        try:
            if self._client is not None:
                resp = self._client.post(url, json=body, headers=headers, timeout=self.timeout)
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise DeciderError(f"Jev request failed: {type(exc).__name__}: {exc}") from exc
        if not resp.is_success:
            raise DeciderError(f"Jev returned HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            data = resp.json()
            answer = data["answers"]["route"]
            choice = answer["choice"]
            raw_probs = answer.get("probabilities") or {}
            raw_conf = answer.get("confidence")
        except (ValueError, KeyError, TypeError) as exc:
            raise DeciderError(f"malformed Jev response: {exc!r}") from exc
        if choice not in options:
            raise DeciderError(f"Jev chose {choice!r}, which is not one of the options")

        probs = _normalise(raw_probs, list(options), choice)
        confidence = _confidence(raw_conf, probs)
        served = data.get("model") if isinstance(data, dict) else None
        return ChoiceResult(
            choice=choice,
            probabilities=probs,
            confidence=confidence,
            backend=f"{self.name}:{served}" if served else self.name,
            latency_ms=(time.perf_counter() - start) * 1000.0,
        )


def _normalise(raw: Any, ids: list[str], choice: str) -> dict[str, float]:
    vals: dict[str, float] = {}
    for oid in ids:
        try:
            v = float(raw.get(oid, 0.0)) if isinstance(raw, dict) else 0.0
        except (TypeError, ValueError):
            v = 0.0
        vals[oid] = v if math.isfinite(v) and v > 0 else 0.0
    total = sum(vals.values())
    if total <= 0:
        return {oid: (1.0 if oid == choice else 0.0) for oid in ids}
    return {oid: v / total for oid, v in vals.items()}


def _confidence(raw: Any, probs: dict[str, float]) -> float:
    try:
        c = float(raw)
    except (TypeError, ValueError):
        c = math.nan
    if not math.isfinite(c):
        n = len(probs)
        if n <= 1:
            return 1.0
        entropy = -sum(p * math.log(p) for p in probs.values() if p > 0)
        c = 1.0 - entropy / math.log(n)
    return min(1.0, max(0.0, c))
