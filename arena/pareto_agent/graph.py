"""Assemble the final domination graph (nodes + edges) from the Pareto run state."""

from __future__ import annotations

from typing import Any, Dict, List

from arena.pareto_agent.models import DominationEdge, RedFlagResult


def build_domination_graph(
    all_hypotheses: List[Dict[str, Any]],
    red_flagged: List[RedFlagResult],
    front: List[Dict[str, Any]],
    domination_edges: List[DominationEdge],
) -> Dict[str, Any]:
    red_flagged_ids = {r.hypothesis_id for r in red_flagged}
    front_ids = {h["id"] for h in front}

    nodes = []
    for h in all_hypotheses:
        hid = h["id"]
        if hid in red_flagged_ids:
            status = "red_flagged"
        elif hid in front_ids:
            status = "front"
        else:
            status = "dominated"
        nodes.append({"hypothesis_id": hid, "status": status})

    edges = [
        {
            "dominator": edge.dominator,
            "dominated": edge.dominated,
            "comparison_summary": edge.comparison_summary,
            "axis_comparisons": {
                axis: comparison.model_dump()
                for axis, comparison in edge.axis_comparisons.items()
            },
        }
        for edge in domination_edges
    ]

    return {"nodes": nodes, "edges": edges}
