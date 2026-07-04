"""pareto.py — multi-objective Pareto-front ranking over hypothesis cards.

The weight-free PRIMARY view of the arena (ARENA.md §3). A hypothesis is on
front 1 (non-dominated) if nothing beats it on *all* axes; peel front 1 off and
repeat for fronts 2, 3, … This is honest about trade-offs — a target can be
highly specific but poorly tractable — and needs no arbitrary weights.

Fully implemented (pure functions, no dependencies): this is deterministic and
the eval harness can score the front-1 order directly. Weighted scalarisation is
provided as the secondary single-ranking view (weights are a defensible CSO
judgement, per ARENA.md §3).
"""
from __future__ import annotations

from .card import Axis, HypothesisCard


def dominates(a: HypothesisCard, b: HypothesisCard, axes: list[Axis] | None = None) -> bool:
    """True if ``a`` Pareto-dominates ``b``: >= on every axis and > on at least one."""
    order = axes or Axis.ranking_axes()
    va, vb = a.value_vector(order), b.value_vector(order)
    at_least_as_good = all(x >= y for x, y in zip(va, vb))
    strictly_better = any(x > y for x, y in zip(va, vb))
    return at_least_as_good and strictly_better


def fronts(cards: list[HypothesisCard], axes: list[Axis] | None = None) -> list[list[HypothesisCard]]:
    """Partition cards into Pareto fronts, best (non-dominated) first.

    Front 0 is the non-dominated set; front 1 is what becomes non-dominated once
    front 0 is removed; and so on. O(n²·|axes|) — fine for the 5–15 hypotheses an
    arena holds (ARENA.md §1).
    """
    order = axes or Axis.ranking_axes()
    remaining = list(cards)
    out: list[list[HypothesisCard]] = []
    while remaining:
        non_dominated = [
            c for c in remaining
            if not any(dominates(o, c, order) for o in remaining if o is not c)
        ]
        if not non_dominated:  # guard against a dominance cycle (shouldn't happen with >=/>)
            non_dominated = remaining
        out.append(non_dominated)
        nd_ids = {id(c) for c in non_dominated}
        remaining = [c for c in remaining if id(c) not in nd_ids]
    return out


def scalarise(card: HypothesisCard, weights: dict[Axis, float] | None = None,
              axes: list[Axis] | None = None) -> float:
    """Weighted-sum score — the secondary single-ranking view (ARENA.md §3).

    Default weights are uniform; the CSO can state explicit weights as a defensible
    judgement. Hides trade-offs if used alone, so it is a companion to ``fronts``,
    not a replacement.
    """
    order = axes or Axis.ranking_axes()
    w = weights or {a: 1.0 for a in order}
    total_w = sum(w.get(a, 0.0) for a in order) or 1.0
    return sum(w.get(a, 0.0) * v for a, v in zip(order, card.value_vector(order))) / total_w


def rank(cards: list[HypothesisCard], weights: dict[Axis, float] | None = None,
         axes: list[Axis] | None = None) -> list[str]:
    """A single best→worst ordering of ``hypothesis_id`` for the eval harness.

    Ordered by (Pareto front index asc, scalarised score desc) — the front is the
    primary key, scalarisation breaks ties *within* a front so a partial order
    becomes the total order the AUGC eval (eval/augc.py) needs.
    """
    order = axes or Axis.ranking_axes()
    front_index = {}
    for i, fr in enumerate(fronts(cards, order)):
        for c in fr:
            front_index[c.hypothesis_id] = i
    ranked = sorted(
        cards,
        key=lambda c: (front_index[c.hypothesis_id], -scalarise(c, weights, order)),
    )
    return [c.hypothesis_id for c in ranked]
