"""Post-front analysis: break ties among Pareto-front members, and recommend
which axis is most worth resolving next.

Both functions are pure aggregations over comparisons already computed during
`build_pareto_front` -- no new LLM calls. See `pareto_agent_design.md` (SS2.4,
SS3) for the reasoning behind each formula.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from arena.pareto_agent.models import AxisName, Confidence, PairwiseComparison

CONFIDENCE_WEIGHT: Dict[Confidence, float] = {"high": 1.0, "medium": 0.5, "low": 0.25}


def _front_vs_front_comparisons(
    front_ids: set, comparisons: List[PairwiseComparison]
) -> List[PairwiseComparison]:
    return [
        c
        for c in comparisons
        if c.hypothesis_A_id in front_ids and c.hypothesis_B_id in front_ids
    ]


def rank_front_by_confidence_weighted_axis_wins(
    front: List[Dict[str, Any]], comparisons: List[PairwiseComparison]
) -> List[Dict[str, Any]]:
    """Confidence-weighted Copeland-style tally over front-vs-front comparisons.

    For every axis in every front-vs-front comparison, the side the axis
    favors gets +weight(confidence) and the other side gets -weight
    (weight in {1.0, 0.5, 0.25} for high/medium/low); ties and unresolved
    axes contribute 0 to both. Every final front member has already been
    directly compared against every other final front member during
    incremental construction (a dominated member is only ever removed by a
    *later* candidate, so any pair still on the front at the end was
    compared at insertion time) -- so this needs no new LLM calls.

    This ranks a *tradeoff*, it does not resolve one: axes disagree by
    construction (that's why these hypotheses are on the front at all), so
    the score is a tie-break heuristic, not a dominance claim.
    """
    front_ids = {h["id"] for h in front}
    score: Dict[str, float] = {h["id"]: 0.0 for h in front}
    breakdown: Dict[str, Dict[AxisName, Dict[str, Any]]] = {
        h["id"]: defaultdict(lambda: {"wins": 0, "losses": 0, "net_weighted": 0.0})
        for h in front
    }

    for c in _front_vs_front_comparisons(front_ids, comparisons):
        for axis, axis_cmp in c.axis_comparisons.items():
            weight = CONFIDENCE_WEIGHT[axis_cmp.confidence]
            if axis_cmp.relation == "A_better":
                winner, loser = c.hypothesis_A_id, c.hypothesis_B_id
            elif axis_cmp.relation == "B_better":
                winner, loser = c.hypothesis_B_id, c.hypothesis_A_id
            else:
                continue  # tie / incomparable / insufficient_evidence: no swing

            score[winner] += weight
            score[loser] -= weight
            breakdown[winner][axis]["wins"] += 1
            breakdown[winner][axis]["net_weighted"] += weight
            breakdown[loser][axis]["losses"] += 1
            breakdown[loser][axis]["net_weighted"] -= weight

    ranking = [
        {
            "hypothesis_id": h["id"],
            "tie_break_score": round(score[h["id"]], 3),
            "axis_breakdown": {
                axis: dict(counts) for axis, counts in breakdown[h["id"]].items()
            },
        }
        for h in front
    ]
    ranking.sort(key=lambda r: r["tie_break_score"], reverse=True)
    return ranking


def compute_voi_recommendations(
    front: List[Dict[str, Any]], comparisons: List[PairwiseComparison]
) -> List[Dict[str, Any]]:
    """VoI(axis) = swing_pairs(axis) / cost(axis), per SS3 of pareto_agent_design.md.

    swing_pairs(axis): number of front-vs-front comparisons where `axis` is
    the *sole* entry in unresolved_axes and the reason is
    insufficient_evidence/incomparable_axes (not both_sides_have_advantages
    -- if a genuine tradeoff exists on another axis, resolving this one
    can't change that pair's outcome, so it isn't a swing axis for it).

    cost(axis): the axis's evidence `cost` tier (1/2/3) already on each
    hypothesis card; per swing pair we take the max of the two hypotheses'
    cost for that axis (the more expensive side gates how cheaply the pair
    can be resolved), then average across occurrences.
    """
    front_ids = {h["id"] for h in front}
    front_by_id = {h["id"]: h for h in front}
    swing_costs: Dict[AxisName, List[float]] = defaultdict(list)

    for c in _front_vs_front_comparisons(front_ids, comparisons):
        if c.overall_relation != "tradeoff_or_unresolved":
            continue
        summary = c.comparison_summary
        if summary.get("reason") == "both_sides_have_advantages":
            continue
        unresolved_axes = summary.get("unresolved_axes", [])
        if len(unresolved_axes) != 1:
            continue

        axis = unresolved_axes[0]
        hyp_a, hyp_b = front_by_id[c.hypothesis_A_id], front_by_id[c.hypothesis_B_id]
        costs = [
            hyp.get("axes", {}).get(axis, {}).get("cost")
            for hyp in (hyp_a, hyp_b)
        ]
        costs = [cost for cost in costs if cost is not None]
        swing_costs[axis].append(max(costs) if costs else 1)

    recommendations = []
    for axis, costs in swing_costs.items():
        avg_cost = sum(costs) / len(costs)
        recommendations.append(
            {
                "axis": axis,
                "swing_pairs": len(costs),
                "avg_cost": round(avg_cost, 2),
                "voi_score": round(len(costs) / avg_cost, 3),
            }
        )
    recommendations.sort(key=lambda r: r["voi_score"], reverse=True)
    return recommendations
