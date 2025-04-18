
"""Fast Monte‑Carlo Shapley value estimator with optional clue *weights*."""
from __future__ import annotations

import math
import random
from typing import Dict, FrozenSet, List


def shapley_sample(
    v: Dict[FrozenSet[int], int],
    n_players: int,
    weights: List[int] | None = None,
    samples: int = 5000,
) -> List[float]:
    """Return list φᵢ for *n_players* using *samples* random permutations."""
    if weights is None:
        weights = [1] * n_players
    φ = [0.0] * n_players
    order = list(range(n_players))

    for _ in range(samples):
        random.shuffle(order)
        S: FrozenSet[int] = frozenset()
        for i in order:
            marginal = (v.get(S | {i}, 0) - v.get(S, 0)) * weights[i]
            φ[i] += marginal
            S |= {i}

    factor = 1.0 / samples
    return [x * factor for x in φ]
