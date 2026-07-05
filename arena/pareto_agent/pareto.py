"""Incremental, comparison-based Pareto-front construction.

Candidates are compared only against the current front (not against every
survivor, and never re-compared once discarded) -- see the `algorithm_note` in
run.py's run_metadata for the input-order-sensitivity this implies in this
first version.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Tuple

from arena.pareto_agent.axis_agents import compare_all_axes
from arena.pareto_agent.models import (
    AxisComparison,
    AxisName,
    OverallRelation,
    PairwiseComparison,
)


def _build_comparison_summary(
    axis_comparisons: Dict[AxisName, AxisComparison], overall_relation: OverallRelation
) -> Dict[str, Any]:
    strictly_better_for_A = [
        axis for axis, c in axis_comparisons.items() if c.relation == "A_better"
    ]
    strictly_better_for_B = [
        axis for axis, c in axis_comparisons.items() if c.relation == "B_better"
    ]
    tied = [axis for axis, c in axis_comparisons.items() if c.relation == "tie"]
    unresolved = [
        axis
        for axis, c in axis_comparisons.items()
        if c.relation in {"incomparable", "insufficient_evidence"}
    ]

    if overall_relation == "A_dominates_B":
        return {
            "overall_relation": overall_relation,
            "strictly_better_axes": strictly_better_for_A,
            "tied_axes": tied,
            "worse_axes": strictly_better_for_B,
            "unresolved_axes": unresolved,
        }

    if overall_relation == "B_dominates_A":
        return {
            "overall_relation": overall_relation,
            "strictly_better_axes": strictly_better_for_B,
            "tied_axes": tied,
            "worse_axes": strictly_better_for_A,
            "unresolved_axes": unresolved,
        }

    # tradeoff_or_unresolved: distinguish a genuine tradeoff from an unresolved axis.
    if strictly_better_for_A and strictly_better_for_B:
        reason = "both_sides_have_advantages"
    elif any(c.relation == "insufficient_evidence" for c in axis_comparisons.values()):
        reason = "insufficient_evidence"
    elif any(c.relation == "incomparable" for c in axis_comparisons.values()):
        reason = "incomparable_axes"
    else:
        reason = "both_sides_have_advantages"

    return {
        "overall_relation": overall_relation,
        "strictly_better_axes_for_A": strictly_better_for_A,
        "strictly_better_axes_for_B": strictly_better_for_B,
        "tied_axes": tied,
        "unresolved_axes": unresolved,
        "reason": reason,
    }


def aggregate_axis_comparisons(
    hypothesis_A_id: str,
    hypothesis_B_id: str,
    axis_comparisons: Dict[AxisName, AxisComparison],
) -> PairwiseComparison:
    """Conservative dominance rule: unanimity across axes, no unresolved axis."""
    relations = [c.relation for c in axis_comparisons.values()]

    a_has_better = any(r == "A_better" for r in relations)
    b_has_better = any(r == "B_better" for r in relations)
    has_unresolved = any(r in {"incomparable", "insufficient_evidence"} for r in relations)

    overall_relation: OverallRelation
    if a_has_better and not b_has_better and not has_unresolved:
        overall_relation = "A_dominates_B"
    elif b_has_better and not a_has_better and not has_unresolved:
        overall_relation = "B_dominates_A"
    else:
        overall_relation = "tradeoff_or_unresolved"

    return PairwiseComparison(
        hypothesis_A_id=hypothesis_A_id,
        hypothesis_B_id=hypothesis_B_id,
        overall_relation=overall_relation,
        comparison_summary=_build_comparison_summary(axis_comparisons, overall_relation),
        axis_comparisons=axis_comparisons,
    )


async def compare_hypotheses(
    candidate: Dict[str, Any], incumbent: Dict[str, Any]
) -> PairwiseComparison:
    axis_comparisons = await compare_all_axes(candidate, incumbent)
    return aggregate_axis_comparisons(
        hypothesis_A_id=candidate["id"],
        hypothesis_B_id=incumbent["id"],
        axis_comparisons=axis_comparisons,
    )


async def build_pareto_front(
    survivors: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[PairwiseComparison]]:
    """Returns (front, all_comparisons). all_comparisons records every pairwise
    comparison performed -- including tradeoff_or_unresolved ones -- not just
    the ones that produced a domination edge, so no LLM judgement is discarded.

    Each candidate compares against the current front in a freshly shuffled
    order, so which incumbent is checked first (and thus can short-circuit
    the rest via the early break below) isn't biased by front insertion order."""
    front: List[Dict[str, Any]] = []
    all_comparisons: List[PairwiseComparison] = []

    for candidate in survivors:
        candidate_is_dominated = False
        front_members_to_remove: List[Dict[str, Any]] = []

        shuffled_front = list(front)
        random.shuffle(shuffled_front)

        for incumbent in shuffled_front:
            comparison = await compare_hypotheses(candidate, incumbent)
            all_comparisons.append(comparison)

            if comparison.overall_relation == "B_dominates_A":
                candidate_is_dominated = True
                break

            if comparison.overall_relation == "A_dominates_B":
                front_members_to_remove.append(incumbent)

            # else: tradeoff_or_unresolved -- no front mutation, but the
            # comparison is still recorded in all_comparisons above.

        if not candidate_is_dominated:
            for dominated_front_member in front_members_to_remove:
                if dominated_front_member in front:
                    front.remove(dominated_front_member)
            front.append(candidate)

    return front, all_comparisons
