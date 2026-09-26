"""semantic-router decider: aurelio-labs/semantic-router routes scored into the Jev contract.

Each non-``none`` option becomes a ``semantic_router.Route`` whose utterances are the
option's ``what`` plus its ``examples``; ``none`` becomes a route of the native exemplars.
By default the encoder is semantic-router's own ``TfidfEncoder``, fitted locally on those
utterances (no network, no API key). A caller may pass any semantic-router encoder instead
(dense or sparse); fittable encoders are refitted whenever the option set changes.

Per-route scores: semantic-router's ``SemanticRouter`` needs a dense encoder and only
returns the best route that clears a threshold, with scores for its ``top_k`` utterances
only. To get a score for *every* option, this backend encodes the utterances and the state
with the encoder in one batch and computes, per route, ``max cosine(state, utterance)``
itself (the same ``max`` aggregation semantic-router offers). Then::

    score(none) = max(none_floor, max cosine(state, native exemplars))
    probabilities = softmax(scores / temperature)      # none_floor 0.35, temperature 0.07
    confidence = 1 - H(p) / log(n)
"""

from __future__ import annotations

import math
import time
from collections.abc import Iterable
from typing import Any

import numpy as np

from agent_router.core.types import NONE_ID, ChoiceResult, OptionSpec
from agent_router.deciders.base import MAX_OPTIONS, DeciderError

INSTALL_HINT = "pip install agent-router[semantic-router]"
NONE_FLOOR = 0.35
TEMPERATURE = 0.07


def _import_semantic_router() -> Any:
    try:
        import semantic_router
        from semantic_router.encoders import TfidfEncoder  # noqa: F401
    except ImportError as exc:
        raise DeciderError(INSTALL_HINT) from exc
    return semantic_router


class SemanticRouterDecider:
    name = "semantic-router"

    def __init__(
        self,
        encoder: Any = None,
        native_examples: Iterable[str] = (),
        none_floor: float = NONE_FLOOR,
        temperature: float = TEMPERATURE,
    ) -> None:
        self._sr = _import_semantic_router()
        self._default_encoder = encoder is None
        self.encoder = encoder
        self.native_examples = tuple(native_examples)
        self.none_floor = none_floor
        self.temperature = temperature
        self._fitted_for: tuple | None = None

    def _routes(self, options: dict[str, OptionSpec]) -> list[Any]:
        from semantic_router import Route

        routes = []
        for oid, spec in options.items():
            texts = [t for t in (spec.what, *spec.examples) if t and t.strip()]
            if oid == NONE_ID:
                texts = [*self.native_examples, *texts]
            texts = list(dict.fromkeys(texts))
            if texts:
                routes.append(Route(name=oid, utterances=texts))
        return routes

    def _fit(self, routes: list[Any]) -> None:
        from semantic_router.encoders import TfidfEncoder
        from semantic_router.encoders.base import FittableMixin

        key = tuple((r.name, tuple(r.utterances)) for r in routes)
        if key == self._fitted_for:
            return
        if self._default_encoder:
            self.encoder = TfidfEncoder()
        if isinstance(self.encoder, FittableMixin):
            self.encoder.fit(routes)
        self._fitted_for = key

    def _encode(self, docs: list[str]) -> np.ndarray:
        """Encode docs to a dense, row-L2-normalised matrix (sparse outputs densified)."""
        from semantic_router.schema import SparseEmbedding

        out = self.encoder(docs)
        if out and isinstance(out[0], SparseEmbedding):
            dicts = [emb.to_dict() for emb in out]
            dim = 1 + max((int(i) for d in dicts for i in d), default=0)
            mat = np.zeros((len(dicts), dim))
            for row, d in enumerate(dicts):
                for i, v in d.items():
                    mat[row, int(i)] = v
        else:
            mat = np.asarray(out, dtype=np.float64)
        mat = np.nan_to_num(mat, nan=0.0, posinf=0.0, neginf=0.0)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return mat / norms

    def decide(self, state: str, options: dict[str, OptionSpec]) -> ChoiceResult:
        start = time.perf_counter()
        if NONE_ID not in options:
            raise DeciderError(f"options must include {NONE_ID!r}")
        if len(options) > MAX_OPTIONS:
            raise DeciderError(f"{len(options)} options exceeds the maximum of {MAX_OPTIONS}")

        routes = self._routes(options)
        try:
            if routes:
                self._fit(routes)
                utterances = [u for r in routes for u in r.utterances]
                with np.errstate(invalid="ignore", divide="ignore"):
                    mat = self._encode([*utterances, state])
                sims = mat[:-1] @ mat[-1]
            else:
                sims = np.zeros(0)
        except DeciderError:
            raise
        except Exception as exc:
            raise DeciderError(f"semantic-router encoder failed: {exc}") from exc

        best: dict[str, float] = {}
        offset = 0
        for r in routes:
            n = len(r.utterances)
            best[r.name] = float(sims[offset : offset + n].max())
            offset += n

        ids = list(options)
        scores = np.array(
            [
                max(self.none_floor, best.get(oid, 0.0)) if oid == NONE_ID else best.get(oid, 0.0)
                for oid in ids
            ],
            dtype=np.float64,
        )
        z = scores / self.temperature
        e = np.exp(z - z.max())
        probs = e / e.sum()
        n = len(ids)
        if n == 1:
            confidence = 1.0
        else:
            nz = probs[probs > 0]
            entropy = float(-(nz * np.log(nz)).sum())
            confidence = min(1.0, max(0.0, 1.0 - entropy / math.log(n)))
        return ChoiceResult(
            choice=ids[int(np.argmax(probs))],
            probabilities={oid: float(p) for oid, p in zip(ids, probs, strict=True)},
            confidence=float(confidence),
            backend=self.name,
            latency_ms=(time.perf_counter() - start) * 1000.0,
        )
