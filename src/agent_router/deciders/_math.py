"""Small numeric helpers shared by deciders."""

from __future__ import annotations

import math
from collections.abc import Iterable


def entropy_confidence(probs: Iterable[float]) -> float:
    """``1 - H(p) / log(n)`` clamped to [0, 1]; 1.0 for a single option."""
    ps = [float(p) for p in probs]
    n = len(ps)
    if n <= 1:
        return 1.0
    entropy = -sum(p * math.log(p) for p in ps if p > 0)
    return min(1.0, max(0.0, 1.0 - entropy / math.log(n)))
