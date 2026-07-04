"""Score a ranked list of targets against the frozen clinical-outcome labels.

Primary metric: normalised Area Under the Gain Curve (AUGC) -- the same metric as
Adaszewski & Schindler (medRxiv 2025), so our numbers sit next to their ~0.72.

  AUGC = (A_actual - A_random) / (A_perfect - A_random)
    1.0  -> all positives ranked first (perfect early enrichment)
    0.0  -> no better than random
    <0   -> positives ranked worse than random

The gain curve plots (fraction of pool scanned) on x vs (fraction of positives
recovered) on y, walking the ranking top -> bottom.

--- Pipeline contract -------------------------------------------------------
Any ranker (the arena, the Claude Science baseline, or the raw OT association
score) feeds AUGC by emitting a RANKING file in this shape:

  {
    "meta": {
      "disease": "melanoma",
      "efo_id": "MONDO_0005012",
      "ranker": "arena",              # who produced this order
      "label_set": "melanoma_anyclin" # which labels.json to score against
    },
    "ranking": ["BRAF", "MAP2K1", ...] # target symbols, best -> worst
  }

`ranking` is an ordered list of target symbols (best first). It should cover the
candidate pool; any pool member missing from `ranking` is appended at the bottom
in arbitrary order (and a warning is printed), so a partial ranking still scores.
Symbols in `ranking` that aren't in the pool are ignored.

See eval/RANKING_FORMAT.md for the full spec and eval/README.md for the flow.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass


@dataclass
class Scored:
    disease: str
    ranker: str
    label_set: str
    n_pool: int
    n_positives: int
    augc: float
    gain_curve: list[tuple[float, float]]  # (x = frac scanned, y = frac positives found)
    hits_at: dict[int, int]                # k -> positives in top-k


def _load_labels(path: str) -> tuple[list[str], set[str]]:
    """Return (pool symbols in file order, set of positive symbols)."""
    data = json.load(open(path))
    rows = data["labels"]
    pool = [r["symbol"] for r in rows]
    positives = {r["symbol"] for r in rows if r["positive"]}
    return pool, positives


def _normalise_ranking(ranking: list[str], pool: list[str]) -> list[str]:
    """Order the pool by the ranking; append unranked pool members at the end."""
    pool_set = set(pool)
    seen = set()
    ordered = []
    for sym in ranking:
        if sym in pool_set and sym not in seen:
            ordered.append(sym)
            seen.add(sym)
    missing = [s for s in pool if s not in seen]
    if missing:
        print(f"  warning: {len(missing)} pool target(s) absent from ranking, "
              f"appended at bottom: {missing[:6]}{'...' if len(missing) > 6 else ''}")
    return ordered + missing


def augc(ranking: list[str], positives: set[str]) -> tuple[float, list[tuple[float, float]]]:
    """Normalised AUGC + the gain curve points for a ranking over its pool."""
    n = len(ranking)
    p = len(positives)
    if n == 0 or p == 0 or p == n:
        # Degenerate: no discrimination possible.
        return 0.0, [(0.0, 0.0), (1.0, 1.0 if p else 0.0)]

    # Gain curve: cumulative fraction of positives recovered vs fraction scanned.
    curve = [(0.0, 0.0)]
    found = 0
    for i, sym in enumerate(ranking, start=1):
        if sym in positives:
            found += 1
        curve.append((i / n, found / p))

    def area(points: list[tuple[float, float]]) -> float:
        # Trapezoidal integration over x in [0, 1].
        a = 0.0
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            a += (x1 - x0) * (y0 + y1) / 2
        return a

    a_actual = area(curve)
    a_random = 0.5  # diagonal
    # Perfect: all p positives first, then flat at y=1.
    perfect = [(0.0, 0.0), (p / n, 1.0), (1.0, 1.0)]
    a_perfect = area(perfect)

    norm = (a_actual - a_random) / (a_perfect - a_random)
    return norm, curve


def score(ranking_path: str, labels_path: str) -> Scored:
    rk = json.load(open(ranking_path))
    ranking_in = rk["ranking"]
    meta = rk.get("meta", {})
    pool, positives = _load_labels(labels_path)
    ranking = _normalise_ranking(ranking_in, pool)

    value, curve = augc(ranking, positives)
    hits = {}
    for k in (5, 10, 20):
        if k <= len(ranking):
            hits[k] = sum(1 for s in ranking[:k] if s in positives)
    return Scored(
        disease=meta.get("disease", "?"),
        ranker=meta.get("ranker", "?"),
        label_set=meta.get("label_set", labels_path),
        n_pool=len(pool),
        n_positives=len(positives),
        augc=round(value, 4),
        gain_curve=[(round(x, 4), round(y, 4)) for x, y in curve],
        hits_at=hits,
    )


def baseline_ot_score(candidates_path: str) -> list[str]:
    """The trivial reference ranker: order candidates by OT association score.

    Lets you compute the Open Targets benchmark AUGC (the paper's ~0.72 competitor)
    without running any model.
    """
    data = json.load(open(candidates_path))
    rows = sorted(data["candidates"], key=lambda c: c["ot_score"], reverse=True)
    return [c["symbol"] for c in rows]


def main() -> None:
    ap = argparse.ArgumentParser(description="Score a ranking against clinical-outcome labels (AUGC).")
    ap.add_argument("--ranking", help="ranking JSON (see eval/RANKING_FORMAT.md)")
    ap.add_argument("--labels", required=True, help="labels JSON, e.g. eval/data/melanoma_anyclin.labels.json")
    ap.add_argument("--ot-baseline", metavar="CANDIDATES_JSON",
                    help="instead of --ranking, score the OT-association-score ordering from this candidates file")
    ap.add_argument("--json", action="store_true", help="emit full result (incl. gain curve) as JSON")
    args = ap.parse_args()

    if args.ot_baseline:
        ranking = baseline_ot_score(args.ot_baseline)
        pool, positives = _load_labels(args.labels)
        value, curve = augc(_normalise_ranking(ranking, pool), positives)
        res = Scored("(OT baseline)", "opentargets_score", args.labels, len(pool),
                     len(positives), round(value, 4),
                     [(round(x, 4), round(y, 4)) for x, y in curve], {})
    elif args.ranking:
        res = score(args.ranking, args.labels)
    else:
        ap.error("provide --ranking or --ot-baseline")

    if args.json:
        print(json.dumps(res.__dict__, indent=2))
    else:
        print(f"disease={res.disease} ranker={res.ranker} labels={res.label_set}")
        print(f"pool={res.n_pool} positives={res.n_positives}")
        print(f"AUGC = {res.augc}")
        if res.hits_at:
            print("hits@k: " + ", ".join(f"@{k}={v}" for k, v in res.hits_at.items()))


if __name__ == "__main__":
    main()
