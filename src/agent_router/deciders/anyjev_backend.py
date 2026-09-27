"""AnyJev adapter: a thin decider over the ``anyjev`` package.

NON-MIT OPTIONAL PLUGIN. ``anyjev`` (https://github.com/MorrisZJ/AnyJev, PyPI ``anyjev``)
is licensed Apache-2.0, not MIT, and pulls in torch + transformers. It is never imported
unless this backend is selected: ``pip install agent-router[anyjev]``. This module holds
only MIT adapter code; it does not vendor or derive from anyjev's source.

AnyJev turns a causal LM into a Jev-style ``choice`` model by reading option-letter logits
in one prefill, with L0 debiasing (cyclic-shift marginalisation + optional label-prior
correction). The adapter asks one ``Question.choice`` whose options are the catalog
``what`` descriptions (``none`` last), maps ``Decision.probs`` back to option ids by index,
and recomputes ``confidence = 1 - H(p)/log(n)`` (anyjev's own ``confidence`` is max-prob).

``prior`` defaults to ``"none"``: anyjev's ``"batch"`` prior keeps a running mean over every
decision it has seen and, after ``min_prior_n`` calls, divides it out, which makes a
long-lived router's answers depend on its history.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from agent_router.core.types import NONE_ID, ChoiceResult, OptionSpec
from agent_router.deciders._math import entropy_confidence
from agent_router.deciders.base import DeciderError
from agent_router.deciders.logprob import QUESTION, describe_option, letter_order

ANYJEV_HINT = "anyjev backend needs anyjev (Apache-2.0): pip install agent-router[anyjev]"


class AnyJevDecider:
    name = "anyjev"

    def __init__(
        self,
        model: str = "Qwen/Qwen3-0.6B",
        device: str = "cpu",
        level: str = "L0",
        prior: str = "none",
        max_permutations: int | None = None,
    ) -> None:
        self.model = model
        self.device = device
        self.level = level
        self.prior = prior
        self.max_permutations = max_permutations
        self._decider: Any = None
        self._question_cls: Any = None

    def _load(self) -> None:
        if self._decider is not None:
            return
        try:
            from anyjev import Decider, Question
            from anyjev.backends.hf import HFBackend
        except ImportError as exc:
            raise DeciderError(ANYJEV_HINT) from exc
        try:
            backend = HFBackend(self.model, device=self.device)
            self._decider = Decider(
                backend,
                level=self.level,
                prior=self.prior,
                max_permutations=self.max_permutations,
            )
        except Exception as exc:
            raise DeciderError(f"could not load anyjev model {self.model}: {exc}") from exc
        self._question_cls = Question

    def decide(self, state: str, options: dict[str, OptionSpec]) -> ChoiceResult:
        start = time.perf_counter()
        if NONE_ID not in options:
            raise DeciderError(f"options must include {NONE_ID!r}")
        order = letter_order(options)
        labels = [describe_option(oid, options[oid]) for oid in order]
        if len(set(labels)) != len(labels):
            labels = [f"{oid}: {label}" for oid, label in zip(order, labels, strict=True)]
        self._load()
        try:
            question = self._question_cls.choice(QUESTION, labels, name="route")
            decision = self._decider.decide(state, [question])["route"]
            probs = np.asarray(decision.probs, dtype=np.float64)
            level = str(decision.level)
        except Exception as exc:
            raise DeciderError(f"anyjev failed: {type(exc).__name__}: {exc}") from exc
        if probs.shape != (len(order),) or not np.all(np.isfinite(probs)) or probs.sum() <= 0:
            raise DeciderError(f"anyjev returned an unusable distribution: {probs!r}")
        probs = np.clip(probs, 0.0, None)
        probs = probs / probs.sum()
        probabilities = {oid: float(p) for oid, p in zip(order, probs, strict=True)}
        return ChoiceResult(
            choice=order[int(np.argmax(probs))],
            probabilities=probabilities,
            confidence=entropy_confidence(probabilities.values()),
            backend=f"{self.name}:{level}:{self.model}",
            latency_ms=(time.perf_counter() - start) * 1000.0,
        )
