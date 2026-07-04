"""Build a frozen prioritisation-eval dataset for one disease from Open Targets.

Produces two JSON snapshots the arena ranks against (and that can't drift under us):
  - candidates.json : probe-filtered candidate targets + OT association score
  - labels.json     : target -> max clinical phase, and the positive flag per candidate

Usage:
  python eval/build_dataset.py --efo MONDO_0005012 --name melanoma \
      --size 500 --min-phase PHASE_2 --outdir eval/data

Ground truth is retrospective (drug-in-clinic for the disease); see
eval/OPENTARGETS_HARNESS.md and eval/CLAUDE_SCIENCE_BASELINE.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.opentargets import candidates, ground_truth, phase_rank  # noqa: E402


def build(efo: str, name: str, size: int, min_phase: str, probe_filter: bool) -> dict:
    pool = candidates(efo, size=size, probe_filter=probe_filter)
    gt = ground_truth(efo)
    threshold = phase_rank(min_phase)

    cand_records = []
    labelled = []
    for c in pool:
        phase = gt.get(c.symbol)  # None if no clinical drug for this disease
        is_positive = phase is not None and phase_rank(phase) <= threshold
        cand_records.append(
            {
                "ensembl_id": c.ensembl_id,
                "symbol": c.symbol,
                "ot_score": round(c.ot_score, 6),
                "high_quality_probe": c.high_quality_probe,
            }
        )
        labelled.append(
            {"symbol": c.symbol, "max_clinical_phase": phase, "positive": is_positive}
        )

    n_pos = sum(1 for r in labelled if r["positive"])
    meta = {
        "disease_name": name,
        "efo_id": efo,
        "candidate_pool_size": len(pool),
        "candidate_filter": "hasHighQualityChemicalProbes" if probe_filter else "top-N-association",
        "association_size_scanned": size,
        "ground_truth": "OpenTargets drugAndClinicalCandidates (drug-in-clinic -> MoA target)",
        "positive_threshold_phase": min_phase,
        "n_positives": n_pos,
        "positive_rate": round(n_pos / len(pool), 4) if pool else 0.0,
        "note": "Snapshot; retrospective clinical-phase ground truth. Not future prediction. "
        "Candidate filter mirrors Adaszewski & Schindler; GT source differs (OT, not curated list).",
    }
    return {"meta": meta, "candidates": cand_records, "labels": labelled}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--efo", required=True, help="disease id, e.g. MONDO_0005012")
    ap.add_argument("--name", required=True, help="short disease name for the filenames/meta")
    ap.add_argument("--size", type=int, default=500, help="top-N associations to scan before filtering")
    ap.add_argument("--min-phase", default="PHASE_2", help="min phase counted as a positive")
    ap.add_argument("--no-probe-filter", action="store_true", help="skip the chemical-probe filter")
    ap.add_argument("--outdir", default="eval/data")
    args = ap.parse_args()

    ds = build(
        args.efo,
        args.name,
        size=args.size,
        min_phase=args.min_phase,
        probe_filter=not args.no_probe_filter,
    )

    os.makedirs(args.outdir, exist_ok=True)
    base = os.path.join(args.outdir, args.name)
    with open(f"{base}.candidates.json", "w") as f:
        json.dump({"meta": ds["meta"], "candidates": ds["candidates"]}, f, indent=2)
    with open(f"{base}.labels.json", "w") as f:
        json.dump({"meta": ds["meta"], "labels": ds["labels"]}, f, indent=2)

    m = ds["meta"]
    print(
        f"{m['disease_name']}: pool={m['candidate_pool_size']} "
        f"positives(>={m['positive_threshold_phase']})={m['n_positives']} "
        f"rate={m['positive_rate']:.0%}\n"
        f"wrote {base}.candidates.json and {base}.labels.json"
    )


if __name__ == "__main__":
    main()
