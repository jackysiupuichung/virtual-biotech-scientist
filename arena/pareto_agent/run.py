"""Run the conservative, comparison-based Pareto agent over a hypothesis fixture.

    python arena/pareto_agent/run.py --hypotheses arena/fixtures/melanoma.hypotheses.json

Workflow: red-flag filter -> incremental Pareto-front construction (six
axis-specific comparison agents per pairwise match, run concurrently) ->
domination graph. No step assigns a numeric LLM score; every Pareto decision
is derived from qualitative pairwise axis comparisons.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any, Dict, List

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from arena.pareto_agent.graph import build_domination_graph  # noqa: E402
from arena.pareto_agent.models import ParetoResult  # noqa: E402
from arena.pareto_agent.pareto import build_pareto_front  # noqa: E402
from arena.pareto_agent.red_flags import red_flag_filter  # noqa: E402

DEFAULT_INPUT = os.path.join(_ROOT, "arena/fixtures/melanoma.hypotheses.json")

ALGORITHM_NOTE = (
    "Incremental Pareto construction is input-order sensitive in this first "
    "version because dominated non-front hypotheses are not compared against "
    "future candidates."
)


async def run_analysis(hypotheses: List[Dict[str, Any]]) -> ParetoResult:
    red_flagged, survivors = await red_flag_filter(hypotheses)
    front, comparisons = await build_pareto_front(survivors)
    graph = build_domination_graph(hypotheses, red_flagged, front, comparisons)

    num_domination_edges = sum(
        1 for c in comparisons if c.overall_relation != "tradeoff_or_unresolved"
    )
    num_tradeoff_comparisons = len(comparisons) - num_domination_edges

    return ParetoResult(
        run_metadata={
            "num_input_hypotheses": len(hypotheses),
            "num_removed_by_red_flags": len(red_flagged),
            "num_surviving_hypotheses": len(survivors),
            "num_front_hypotheses": len(front),
            "num_domination_edges": num_domination_edges,
            "num_tradeoff_comparisons": num_tradeoff_comparisons,
            "num_comparisons_total": len(comparisons),
            "algorithm_note": ALGORITHM_NOTE,
        },
        red_flagged_hypotheses=red_flagged,
        pareto_front=[
            {
                "hypothesis_id": h["id"],
                "target": h.get("target", {}).get("symbol"),
                "disease": h.get("disease", {}).get("name"),
                "modality": h.get("modality"),
                "front_status": "non_dominated",
            }
            for h in front
        ],
        domination_graph=graph,
    )


def _load_hypotheses(path: str) -> List[Dict[str, Any]]:
    with open(path) as f:
        doc = json.load(f)
    return doc["hypotheses"] if isinstance(doc, dict) and "hypotheses" in doc else doc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hypotheses", default=DEFAULT_INPUT)
    parser.add_argument("--out", default=None, help="write JSON here instead of stdout")
    args = parser.parse_args()

    hypotheses = _load_hypotheses(args.hypotheses)
    result = asyncio.run(run_analysis(hypotheses))
    out = result.model_dump_json(indent=2)

    if args.out:
        with open(args.out, "w") as f:
            f.write(out)
        print(f"wrote {args.out}")
    else:
        print(out)


if __name__ == "__main__":
    main()
