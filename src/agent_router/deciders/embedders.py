"""Text embedders for the local decider. Every ``encode`` returns L2-normalised rows.

- ``HashingEmbedder``: deterministic, numpy-only, offline. Used by unit tests and as the
  fallback when the model cannot be loaded.
- ``Model2VecEmbedder``: static ``minishlab/potion-base-8M`` embeddings (MIT, numpy-only).

``default_embedder()`` honours ``AGENT_ROUTER_EMBEDDER`` = ``model2vec`` (default) | ``hashing``.
"""

from __future__ import annotations

import logging
import math
import os
import re
import zlib
from collections import Counter
from typing import Any, Protocol

import numpy as np

log = logging.getLogger(__name__)

ENV_EMBEDDER = "AGENT_ROUTER_EMBEDDER"
DEFAULT_MODEL = "minishlab/potion-base-8M"

_WORD = re.compile(r"\w+")
_SPACE = re.compile(r"\s+")


class Embedder(Protocol):
    def encode(self, texts: list[str]) -> np.ndarray: ...


def l2_normalise(mat: np.ndarray) -> np.ndarray:
    """Normalise rows to unit length; all-zero rows stay zero (no NaN)."""
    mat = np.asarray(mat, dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    return np.divide(mat, norms, out=np.zeros_like(mat), where=norms > 0)


class HashingEmbedder:
    """Feature-hashing embedder: word unigrams + bigrams and char 3-5-grams.

    Features are hashed with ``crc32`` (stable across processes) into ``dim`` buckets with
    sublinear tf (1 + log tf). Each feature family is normalised on its own before they are
    summed, so the many char n-grams do not drown out the few word features.
    """

    def __init__(self, dim: int = 2**14, char_ngrams: tuple[int, int] = (3, 5)) -> None:
        self.dim = dim
        self.char_ngrams = char_ngrams

    @staticmethod
    def bucket(feature: str, dim: int = 2**14) -> int:
        return zlib.crc32(feature.encode("utf-8")) % dim

    def _families(self, text: str) -> list[Counter[str]]:
        text = _SPACE.sub(" ", text.lower()).strip()
        words = _WORD.findall(text)
        unigrams = Counter(f"w:{w}" for w in words)
        bigrams = Counter(f"b:{a} {b}" for a, b in zip(words, words[1:], strict=False))
        chars: Counter[str] = Counter()
        if text:
            padded = f" {text} "
            lo, hi = self.char_ngrams
            for n in range(lo, hi + 1):
                chars.update(f"c:{padded[i : i + n]}" for i in range(len(padded) - n + 1))
        return [unigrams, bigrams, chars]

    def _vector(self, text: str) -> np.ndarray:
        out = np.zeros(self.dim, dtype=np.float32)
        for counts in self._families(text):
            if not counts:
                continue
            fam = np.zeros(self.dim, dtype=np.float32)
            for feat, tf in counts.items():
                fam[self.bucket(feat, self.dim)] += 1.0 + math.log(tf)
            out += fam / np.linalg.norm(fam)
        return out

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return l2_normalise(np.stack([self._vector(t) for t in texts]))


class Model2VecEmbedder:
    """model2vec static embeddings, loaded lazily on first ``encode`` (or ``load``)."""

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model
        self._model: Any = None

    def load(self) -> None:
        if self._model is None:
            from model2vec import StaticModel

            self._model = StaticModel.from_pretrained(self.model)

    def encode(self, texts: list[str]) -> np.ndarray:
        self.load()
        return l2_normalise(np.asarray(self._model.encode(list(texts))))


def default_embedder() -> Embedder:
    """Embedder chosen by ``AGENT_ROUTER_EMBEDDER`` (``model2vec`` default, or ``hashing``).

    Model2Vec is loaded eagerly here so a load failure (no network, missing package) falls
    back to ``HashingEmbedder`` with a logged warning instead of failing at decide time.
    """
    choice = os.environ.get(ENV_EMBEDDER, "model2vec").strip().lower() or "model2vec"
    if choice == "hashing":
        return HashingEmbedder()
    if choice != "model2vec":
        raise ValueError(f"{ENV_EMBEDDER}={choice!r}: expected 'model2vec' or 'hashing'")
    emb = Model2VecEmbedder()
    try:
        emb.load()
    except Exception as exc:  # any load failure (network, package, files) falls back
        log.warning("model2vec load failed (%s); falling back to HashingEmbedder", exc)
        return HashingEmbedder()
    return emb
