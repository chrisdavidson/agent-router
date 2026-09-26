"""Local Jev-spec decider: an embedding classifier over catalog options with abstention.

Per non-``none`` option::

    dense   = max cos(state, [what, *examples])
    lexical = Jaccard(content tokens of state, of the exemplar that gave ``dense``)
    score   = alpha * dense + (1 - alpha) * lexical
    nf      = max cos(state, not_for);  if nf > dense: score -= not_for_penalty * (nf - dense)

``none`` scores ``max(none_floor, max cos(state, native exemplars))``, where the native
exemplars are the catalog-wide ``native_examples`` plus the none option's own
``what``/``examples``. ``probabilities = softmax(scores / temperature)``, ``choice`` is the
argmax and ``confidence = 1 - H(p) / log(n)``.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from agent_router.core.types import NONE_ID, ChoiceResult, OptionSpec
from agent_router.deciders.base import MAX_OPTIONS, DeciderError
from agent_router.deciders.embedders import Embedder, default_embedder

_WORD = re.compile(r"\w+")
_STOPWORDS_TEXT = """
a an the and or but if then else of to in on at by for from with without into onto over
under about as is are was were be been being am do does did done have has had i me my we
our you your he she it its they them their this that these those there here what which who
whom whose when where why how can could should would will shall may might must please just
so than too very all any some each no not only own same such out up down off again further
once also
"""
STOPWORDS = frozenset(_STOPWORDS_TEXT.split())


def content_tokens(text: str) -> frozenset[str]:
    return frozenset(w for w in _WORD.findall(text.lower()) if w not in STOPWORDS)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


@dataclass
class LocalParams:
    """Scoring knobs. Defaults are uncalibrated; ``agent-router calibrate`` tunes them."""

    alpha: float = 0.8  # weight of dense cosine vs lexical overlap
    none_floor: float = 0.35  # minimum score of the ``none`` option (abstention floor)
    temperature: float = 0.07  # softmax temperature
    not_for_penalty: float = 0.5  # scale of the penalty when state matches not_for best


class LocalJevDecider:
    name = "local"

    def __init__(
        self,
        embedder: Embedder | None = None,
        params: LocalParams | None = None,
        native_examples: Iterable[str] = (),
    ) -> None:
        self.embedder = embedder if embedder is not None else default_embedder()
        self.params = params if params is not None else LocalParams()
        self.native_examples = tuple(native_examples)
        self._cache: dict[tuple[str, str], np.ndarray] = {}

    # -- embeddings --------------------------------------------------------

    def _embed_exemplars(self, keys: list[tuple[str, str]]) -> None:
        missing = list(dict.fromkeys(k for k in keys if k not in self._cache))
        if not missing:
            return
        vecs = self.embedder.encode([text for _, text in missing])
        for key, vec in zip(missing, vecs, strict=True):
            self._cache[key] = vec

    def _cosines(self, state_vec: np.ndarray, key_id: str, texts: Iterable[str]) -> list[float]:
        return [float(self._cache[(key_id, t)] @ state_vec) for t in texts]

    # -- decide ------------------------------------------------------------

    def decide(self, state: str, options: dict[str, OptionSpec]) -> ChoiceResult:
        start = time.perf_counter()
        if NONE_ID not in options:
            raise DeciderError(f"options must include {NONE_ID!r}")
        if len(options) > MAX_OPTIONS:
            raise DeciderError(f"{len(options)} options exceeds the maximum of {MAX_OPTIONS}")

        ids = list(options)
        exemplars: dict[str, list[str]] = {}
        not_fors: dict[str, list[str]] = {}
        for oid, spec in options.items():
            texts = [t for t in (spec.what, *spec.examples) if t and t.strip()]
            if oid == NONE_ID:
                texts = list(dict.fromkeys([*self.native_examples, *texts]))
            exemplars[oid] = texts
            not_fors[oid] = [t for t in spec.not_for if t and t.strip()]

        try:
            self._embed_exemplars(
                [(oid, t) for oid in ids for t in (*exemplars[oid], *not_fors[oid])]
            )
            state_vec = np.asarray(self.embedder.encode([state])[0])
        except Exception as exc:
            raise DeciderError(f"embedder failed: {exc}") from exc

        p = self.params
        state_tokens = content_tokens(state)
        scores = np.empty(len(ids), dtype=np.float64)
        for i, oid in enumerate(ids):
            cos = self._cosines(state_vec, oid, exemplars[oid])
            if oid == NONE_ID:
                scores[i] = max([p.none_floor, *cos])
                continue
            if not cos:
                dense, lexical = 0.0, 0.0
            else:
                best = int(np.argmax(cos))
                dense = cos[best]
                lexical = jaccard(state_tokens, content_tokens(exemplars[oid][best]))
            score = p.alpha * dense + (1.0 - p.alpha) * lexical
            nf_cos = self._cosines(state_vec, oid, not_fors[oid])
            nf = max(nf_cos) if nf_cos else 0.0
            if nf > dense:
                score -= p.not_for_penalty * (nf - dense)
            scores[i] = score

        probs = _softmax(scores / p.temperature)
        n = len(ids)
        if n == 1:
            confidence = 1.0
        else:
            nz = probs[probs > 0]
            entropy = float(-(nz * np.log(nz)).sum())
            confidence = min(1.0, max(0.0, 1.0 - entropy / math.log(n)))
        best_i = int(np.argmax(probs))
        return ChoiceResult(
            choice=ids[best_i],
            probabilities={oid: float(pr) for oid, pr in zip(ids, probs, strict=True)},
            confidence=float(confidence),
            backend=self.name,
            latency_ms=(time.perf_counter() - start) * 1000.0,
        )


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max())
    return e / e.sum()
