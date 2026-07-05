"""Assemble the final comparison graph (nodes + edges) from the Pareto run state."""

from __future__ import annotations

from typing import Any, Dict, List

from arena.pareto_agent.models import PairwiseComparison, RedFlagResult


def build_domination_graph(
    all_hypotheses: List[Dict[str, Any]],
    red_flagged: List[RedFlagResult],
    front: List[Dict[str, Any]],
    comparisons: List[PairwiseComparison],
) -> Dict[str, Any]:
    red_flagged_by_id = {r.hypothesis_id: r for r in red_flagged}
    front_ids = {h["id"] for h in front}

    nodes = []
    for h in all_hypotheses:
        hid = h["id"]
        if hid in red_flagged_by_id:
            status = "red_flagged"
        elif hid in front_ids:
            status = "front"
        else:
            status = "dominated"

        node: Dict[str, Any] = {"hypothesis_id": hid, "status": status}
        if hid in red_flagged_by_id:
            flag = red_flagged_by_id[hid]
            node["red_flag_detail"] = {
                "decision": flag.decision,
                "rationale": flag.rationale,
                "red_flags": [f.model_dump() for f in flag.red_flags],
            }
        nodes.append(node)

    edges = []
    for c in comparisons:
        if c.overall_relation == "A_dominates_B":
            dominator, dominated = c.hypothesis_A_id, c.hypothesis_B_id
        elif c.overall_relation == "B_dominates_A":
            dominator, dominated = c.hypothesis_B_id, c.hypothesis_A_id
        else:
            dominator, dominated = None, None

        edges.append(
            {
                "hypothesis_a": c.hypothesis_A_id,
                "hypothesis_b": c.hypothesis_B_id,
                "relation": c.overall_relation,
                "dominator": dominator,
                "dominated": dominated,
                "comparison_summary": c.comparison_summary,
                "axis_comparisons": {
                    axis: comparison.model_dump()
                    for axis, comparison in c.axis_comparisons.items()
                },
            }
        )

    return {"nodes": nodes, "edges": edges}
