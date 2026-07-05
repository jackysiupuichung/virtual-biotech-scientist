"""Run the conservative, comparison-based Pareto agent over a hypothesis fixture.

    # arena fixture format (numeric-scored hypotheses):
    python arena/pareto_agent/run.py --hypotheses arena/fixtures/melanoma.hypotheses.json

    # virtual-biotech-cso 5R cards (qualitative findings, one JSON per target):
    python arena/pareto_agent/run.py --hypotheses skills/virtual-biotech-cso/eval/arena_set/cards

Two input formats are accepted (see _load_hypotheses): the arena's own fixture, and
a directory (or list) of CSO 5R cards. The judge dumps each hypothesis verbatim into
its prompt, so a card's qualitative per-axis findings are compared directly — the CSO
cards carry no numeric value/confidence, and none is required.

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
from arena.pareto_agent.tiebreak import (  # noqa: E402
    compute_voi_recommendations,
    rank_front_by_confidence_weighted_axis_wins,
)

DEFAULT_INPUT = os.path.join(_ROOT, "arena/fixtures/melanoma.hypotheses.json")

ALGORITHM_NOTE = (
    "Incremental Pareto construction is input-order sensitive in this first "
    "version because dominated non-front hypotheses are not compared against "
    "future candidates."
)


async def run_analysis(
    hypotheses: List[Dict[str, Any]], *, skip_red_flags: bool = False
) -> ParetoResult:
    if skip_red_flags:
        red_flagged, survivors = [], hypotheses
    else:
        red_flagged, survivors = await red_flag_filter(hypotheses)
    front, comparisons = await build_pareto_front(survivors)
    graph = build_domination_graph(hypotheses, red_flagged, front, comparisons)

    num_domination_edges = sum(
        1 for c in comparisons if c.overall_relation != "tradeoff_or_unresolved"
    )
    num_tradeoff_comparisons = len(comparisons) - num_domination_edges

    # Front membership is a dominance verdict; the two below are post-front,
    # tie-break-only analyses over comparisons already computed above (no new
    # LLM calls) -- see pareto_agent_design.md SS2.4 / SS3.
    tie_break_ranking = rank_front_by_confidence_weighted_axis_wins(front, comparisons)
    voi_recommendations = compute_voi_recommendations(front, comparisons)

    tie_break_score_by_id = {r["hypothesis_id"]: r["tie_break_score"] for r in tie_break_ranking}

    return ParetoResult(
        run_metadata={
            "num_input_hypotheses": len(hypotheses),
            "num_removed_by_red_flags": len(red_flagged),
            "num_surviving_hypotheses": len(survivors),
            "num_front_hypotheses": len(front),
            "num_domination_edges": num_domination_edges,
            "num_tradeoff_comparisons": num_tradeoff_comparisons,
            "num_comparisons_total": len(comparisons),
            "red_flag_filter_enabled": not skip_red_flags,
            "algorithm_note": ALGORITHM_NOTE,
            "tie_break_note": (
                "pareto_front is ordered by tie_break_score (confidence-weighted "
                "axis-win tally over front-vs-front comparisons); it is a "
                "presentational tie-break, not a dominance claim -- front members "
                "remain mutually non-dominated. See tie_break_ranking for the "
                "per-axis breakdown and voi_recommendations for which axis is "
                "most worth resolving next."
            ),
        },
        red_flagged_hypotheses=red_flagged,
        pareto_front=sorted(
            (
                {
                    "hypothesis_id": h["id"],
                    "target": h.get("target", {}).get("symbol"),
                    "disease": h.get("disease", {}).get("name"),
                    "modality": h.get("modality"),
                    "front_status": "non_dominated",
                    "tie_break_score": tie_break_score_by_id[h["id"]],
                }
                for h in front
            ),
            key=lambda entry: entry["tie_break_score"],
            reverse=True,
        ),
        domination_graph=graph,
        tie_break_ranking=tie_break_ranking,
        voi_recommendations=voi_recommendations,
    )


def _adapt_cso_card(card: Dict[str, Any], idx: int,
                    label: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Adapt a virtual-biotech-cso 5R card into an arena hypothesis dict.

    A CSO card is ``{target, disease, per_axis: {<axis>: {finding, grade, provenance}}}``.
    The arena only *requires* an ``id`` by name (graph/pareto/red_flag key on it); the
    rest of the hypothesis body is dumped verbatim into the judge prompt, so the card's
    qualitative per-axis findings are read directly — no numeric value/confidence needed.
    We map ``per_axis`` → ``axes`` (the key the fixture uses, for prompt familiarity),
    keep each axis's ``finding``/``grade``/``provenance``, and attach the label if given.
    """
    sym = card.get("target", f"H{idx}")
    return {
        "id": f"H{idx}_{sym}",
        "target": {"symbol": sym},
        "disease": {"name": card.get("disease", "")},
        "source": "virtual-biotech-cso",
        "axes": {axis: {"finding": body.get("finding", ""),
                        "strength": body.get("grade", ""),
                        "provenance": body.get("provenance", "")}
                 for axis, body in (card.get("per_axis") or {}).items()},
        **({"label": label} if label else {}),
    }


def _is_cso_card(doc: Any) -> bool:
    """A CSO card (or list of them) is identified by the ``per_axis`` key."""
    if isinstance(doc, dict) and "per_axis" in doc:
        return True
    if isinstance(doc, list) and doc and isinstance(doc[0], dict) and "per_axis" in doc[0]:
        return True
    return False


def _load_hypotheses(path: str) -> List[Dict[str, Any]]:
    """Load arena hypotheses from either input format:

      * **arena fixture** — ``{"hypotheses": [...]}`` or a bare list of hypothesis dicts.
      * **CSO cards** — a single ``per_axis`` card, a list of them, OR a directory of
        ``*.json`` cards (the virtual-biotech-cso ``eval/arena_set/cards/`` layout).
        Labels are pulled from a sibling ``melanoma_10.json`` (``targets[]``) if present.
    """
    # Directory of CSO cards → load each, attach labels from the set manifest if present.
    if os.path.isdir(path):
        labels: Dict[str, Dict[str, Any]] = {}
        manifest = os.path.join(os.path.dirname(path.rstrip("/")), "melanoma_10.json")
        if os.path.exists(manifest):
            with open(manifest) as f:
                for t in (json.load(f).get("targets") or []):
                    labels[t["symbol"]] = {"positive": t.get("ground_truth", False)}
        cards = []
        for name in sorted(os.listdir(path)):
            if name.endswith(".json"):
                with open(os.path.join(path, name)) as f:
                    cards.append(json.load(f))
        return [_adapt_cso_card(c, i, labels.get(c.get("target")))
                for i, c in enumerate(cards, 1)]

    with open(path) as f:
        doc = json.load(f)
    if _is_cso_card(doc):
        cards = doc if isinstance(doc, list) else [doc]
        return [_adapt_cso_card(c, i) for i, c in enumerate(cards, 1)]
    return doc["hypotheses"] if isinstance(doc, dict) and "hypotheses" in doc else doc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hypotheses", default=DEFAULT_INPUT)
    parser.add_argument("--out", default=None, help="write JSON here instead of stdout")
    parser.add_argument(
        "--skip-red-flags",
        action="store_true",
        help="compare every loaded hypothesis directly, without pre-Pareto red-flag removal",
    )
    args = parser.parse_args()

    hypotheses = _load_hypotheses(args.hypotheses)
    result = asyncio.run(run_analysis(hypotheses, skip_red_flags=args.skip_red_flags))
    out = result.model_dump_json(indent=2)

    if args.out:
        with open(args.out, "w") as f:
            f.write(out)
        print(f"wrote {args.out}")
    else:
        print(out)


if __name__ == "__main__":
    main()
