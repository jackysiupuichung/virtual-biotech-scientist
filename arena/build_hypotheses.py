"""Build descriptive, report-style hypothesis cards for the arena (melanoma).

Each card is a target x disease x modality hypothesis with an evidence entry per
5R axis. Real Open Targets fields fill what OT genuinely supplies (Right Target,
Right Safety, Tractability, and the coarse parts of Tissue/Patient/Commercial);
the parts OT cannot reach (single-cell tau specificity, malignant fraction,
patient stratum, competitive whitespace) are synthesised and flagged
`data_origin: "synthetic"`. Cards carry findings/interpretations and a narrative
block so they read like a Virtual-Biotech division dossier, not bare scalars.

  python arena/build_hypotheses.py           # -> arena/fixtures/melanoma.hypotheses.json

Deterministic: targets are chosen from the frozen candidate pool by association
rank + phase labels (no RNG); synthetic axis values are derived from real signals
so they're stable and defensible, not random. Runs from any cwd (paths are anchored
to the repo root). Inputs (candidate pool + labels) live in eval/data/; the arena
fixture output lives in arena/fixtures/.
"""

from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)

from tools.opentargets import target_evidence, ground_truth, phase_rank  # noqa: E402

EFO = "MONDO_0005012"
DISEASE = "cutaneous melanoma"
CANDIDATES = os.path.join(_ROOT, "eval/data/melanoma.candidates.json")
LABELS = os.path.join(_ROOT, "eval/data/melanoma_anyclin.labels.json")
OUT = os.path.join(_ROOT, "arena/fixtures/melanoma.hypotheses.json")

N_HYPOTHESES = 15  # ~18% positive ratio -> ~3 known-clinical targets, matching the pool

AXES = ["right_target", "right_tissue", "right_safety",
        "right_patient", "right_commercial", "tractability"]

# Hand-set modality per target, grounded in real biology (intracellular kinase ->
# small_molecule; surface receptor / validated antigen -> antibody or ADC). ERBB2
# (HER2) and FGFR2/NTRK1 carry the ADC story (surface antigen + payload strategy).
MODALITY = {
    "BRAF": "small_molecule", "MAP2K1": "small_molecule", "MAP2K2": "small_molecule",
    "AKT1": "small_molecule", "MTOR": "small_molecule", "ATM": "small_molecule",
    "ATR": "small_molecule", "TERT": "small_molecule", "SETD2": "small_molecule",
    "SMARCA4": "small_molecule", "GRIN2A": "small_molecule", "FGFR1": "small_molecule",
    "ERBB2": "ADC",        # HER2 — validated ADC antigen (T-DXd etc.)
    "FGFR2": "ADC",        # surface RTK, ADC-plausible
    "NTRK1": "antibody",   # surface RTK
}

# Designed trade-offs on the otherwise-synthetic axes (right_tissue, and the
# synthesised parts of commercial/patient), so the Pareto front is deliberately
# non-trivial: some hypotheses dominate on tissue specificity but are tractability-
# weak, others the reverse. Keys are symbols; values override the synthetic priors.
# tissue_override in [0,1] (single-cell specificity prior); rationale is prose.
TRADEOFF = {
    # tissue-STRONG, tractability-weaker: the "specific but hard to drug" corner
    "NTRK1":   {"tissue": 0.88, "note": "highly lineage-restricted expression (strong specificity prior); "
                                        "but antibody-only tractability caps the modality options"},
    "FGFR2":   {"tissue": 0.82, "note": "focal amplification pattern implies tumour-cell-restricted expression"},
    "ERBB2":   {"tissue": 0.80, "note": "HER2-high sub-population is sharply demarcated — a clean ADC window"},
    "GRIN2A":  {"tissue": 0.78, "note": "neuronal-restricted; strong specificity but weak melanoma tractability"},
    # tissue-WEAK, broadly expressed: the "druggable but non-specific" corner
    "MTOR":    {"tissue": 0.20, "note": "ubiquitous essential kinase — poor tumour specificity, on-target-everywhere risk"},
    "AKT1":    {"tissue": 0.25, "note": "broadly expressed node; specificity relies entirely on context"},
    "ATM":     {"tissue": 0.28, "note": "housekeeping DNA-damage sensor; expressed everywhere"},
    "ATR":     {"tissue": 0.26, "note": "housekeeping replication-stress kinase; no tumour restriction"},
    # mid / driver-specific
    "BRAF":    {"tissue": 0.72, "note": "mutant-BRAF melanoma is the definitional driver context"},
    "MAP2K1":  {"tissue": 0.60, "note": "downstream of BRAF; specificity inherited from pathway context"},
    "MAP2K2":  {"tissue": 0.58, "note": "MEK2 — pathway-contextual specificity"},
}


# --------------------------------------------------------------------------- #
# Target selection: 15 from the pool, preserving the pool's positive ratio
# --------------------------------------------------------------------------- #

def select_targets() -> list[dict]:
    cand = json.load(open(CANDIDATES))["candidates"]
    labels = {l["symbol"]: l for l in json.load(open(LABELS))["labels"]}
    pos = [c for c in cand if labels.get(c["symbol"], {}).get("positive")]
    neg = [c for c in cand if not labels.get(c["symbol"], {}).get("positive")]
    n_pos = round(N_HYPOTHESES * len(pos) / len(cand))  # preserve ratio
    # highest-association first within each group -> deterministic, sensible slate
    pos.sort(key=lambda c: c["ot_score"], reverse=True)
    neg.sort(key=lambda c: c["ot_score"], reverse=True)
    chosen = pos[:n_pos] + neg[: N_HYPOTHESES - n_pos]
    chosen.sort(key=lambda c: c["ot_score"], reverse=True)
    gt = ground_truth(EFO)
    for c in chosen:
        c["max_clinical_phase"] = gt.get(c["symbol"])
        c["positive"] = c["symbol"] in gt
    return chosen


# --------------------------------------------------------------------------- #
# Axis builders -- each returns a descriptive evidence entry.
# `data_origin`: "opentargets" (real), "hybrid" (real + judgment), "synthetic".
# --------------------------------------------------------------------------- #

def _loeuf(ev: dict) -> float | None:
    for g in ev["genetic_constraint"]:
        if g["constraintType"] == "lof":
            return g["oe"]
    return None


def _norm(x: float, lo: float, hi: float) -> float:
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


def axis_right_target(cand: dict, ev: dict) -> dict:
    score = cand["ot_score"]
    loeuf = _loeuf(ev)
    constraint = "" if loeuf is None else (
        f" Loss-of-function constraint LOEUF (o/e)={loeuf:.2f}, "
        f"{'in the constrained tail — the gene is intolerant to LoF, which raises both a mechanistic causality prior and an on-target-toxicity flag' if loeuf < 0.35 else 'in the tolerant range — LoF is well tolerated in population data, weakly arguing against essential-gene toxicity'}.")
    pw = ev["pathways"][:2]
    pw_txt = f" Sits on {', '.join(pw)}." if pw else ""
    return {
        "value": round(score, 3),
        "confidence": 0.9,
        "cost": 1,
        "direction": "supports" if score > 0.3 else "neutral",
        "strength": "strong" if score > 0.5 else "moderate" if score > 0.2 else "weak",
        "data_origin": "opentargets",
        "finding": f"Open Targets overall disease association with melanoma = {score:.3f} "
                   f"(aggregating genetic, somatic, literature and known-drug evidence).{constraint}",
        "interpretation": (
            f"Strong, multi-modal causal support: {cand['symbol']} is a well-credentialled melanoma "
            f"target and the association is unlikely to be literature-only noise.{pw_txt}"
            if score > 0.5 else
            f"Association is modest ({score:.3f}); the case rests more on mechanism/somatic biology "
            f"than on aggregate scoring, so the target-validity axis carries real uncertainty here.{pw_txt}"),
        "source": {"db": "OpenTargets", "fields": ["associationScore", "geneticConstraint", "pathways"]},
    }


def axis_tractability(cand: dict, ev: dict, modality: str) -> dict:
    tr = ev["tractability"]
    bucket = {"small_molecule": "SM", "antibody": "AB", "ADC": "AB", "PROTAC": "PR"}.get(modality, "SM")
    mine = [t for t in tr if t["modality"] == bucket and t["value"]]
    labels = [t["label"] for t in mine]
    approved = any("Approved Drug" in t["label"] for t in mine)
    pocket = any("Pocket" in t["label"] for t in mine)
    val = 0.9 if approved else 0.6 if pocket or labels else 0.3
    return {
        "value": val,
        "confidence": 0.9,
        "cost": 1,
        "direction": "supports" if val >= 0.6 else "refutes",
        "strength": "strong" if approved else "moderate" if val >= 0.6 else "weak",
        "data_origin": "opentargets",
        "finding": f"Open Targets {bucket}-modality tractability buckets satisfied: "
                   f"{', '.join(labels[:5]) or 'none'}.",
        "interpretation": (
            f"De-risked modality: {cand['symbol']} already has an approved {modality} drug, so "
            f"chemistry/biologics feasibility is proven and the programme starts from precedent rather "
            f"than discovery risk." if approved else
            f"Tractable by {modality}: a druggable pocket / structural handle is present, so the "
            f"modality is credible though not yet clinically validated for this target." if val >= 0.6 else
            f"Tractability is the weak axis here — {cand['symbol']} lacks a good {modality} handle, so "
            f"this hypothesis pays a real feasibility penalty and may be Pareto-dominated on cost-to-drug."),
        "source": {"db": "OpenTargets", "fields": ["tractability"]},
    }


def axis_right_safety(cand: dict, ev: dict) -> dict:
    liab = ev["safety_liabilities"]
    n_mouse = len(ev["mouse_phenotypes"])
    # More liabilities / broader KO phenotype -> narrower safety window -> lower value.
    val = round(_norm(1.0 - min(len(liab), 3) / 3 * 0.5 - _norm(n_mouse, 0, 120) * 0.5, 0, 1), 3)
    mp = ev["mouse_phenotypes"][:3]
    mp_txt = f" Representative mouse-KO phenotypes: {', '.join(mp)}." if mp else ""
    return {
        "value": val,
        "confidence": 0.6,
        "cost": 1,
        "direction": "refutes" if val < 0.4 else "neutral",
        "strength": "moderate" if liab or n_mouse else "weak",
        "data_origin": "opentargets",
        "finding": (
            f"{len(liab)} curated safety liability(ies)"
            + (f" ({', '.join(liab[:3])})" if liab else "")
            + f" and {n_mouse} distinct mouse-knockout phenotypes on record.{mp_txt}"),
        "interpretation": (
            f"Safety is a headwind: the breadth of knockout phenotypes ({n_mouse}) and the curated "
            f"liability signal point to a broad developmental/essential role, so systemic inhibition "
            f"risks on-target toxicity in normal tissue — the therapeutic window is narrow and must be "
            f"bought back with tumour-selective delivery or dosing."
            if n_mouse > 60 or len(liab) >= 2 else
            f"No dominant safety liability surfaced and the knockout footprint is modest, so the "
            f"safety window is plausibly open — this axis is a relative strength for {cand['symbol']}."),
        "source": {"db": "OpenTargets", "fields": ["safetyLiabilities", "mousePhenotypes"]},
    }


def axis_right_patient(cand: dict, ev: dict) -> dict:
    phase = cand.get("max_clinical_phase")
    has_trial = phase is not None
    val = 0.85 if phase and phase_rank(phase) <= phase_rank("PHASE_2") else 0.6 if has_trial else 0.35
    return {
        "value": val,
        "confidence": 0.7 if has_trial else 0.4,
        "cost": 1,
        "direction": "supports" if has_trial else "neutral",
        "strength": "strong" if val >= 0.8 else "moderate" if has_trial else "weak",
        "data_origin": "hybrid",  # trial existence real; stratum/biomarker synthesised
        "finding": (
            f"Real clinical precedent: a drug against {cand['symbol']} has reached "
            f"{phase} in melanoma (from Open Targets drugAndClinicalCandidates), so a treatable "
            f"patient population is already defined. The specific biomarker stratum is a synthetic placeholder."
            if has_trial else
            f"No melanoma clinical precedent for {cand['symbol']} in Open Targets, so both the patient "
            f"population and its enrichment biomarker would have to be established de novo (synthetic)."),
        "interpretation": (
            f"Patient axis is a strength: an existing {phase} programme means the stratification and "
            f"endpoint risk is largely retired — the open question is only which biomarker sub-population "
            f"to enrich, not whether one exists."
            if has_trial else
            f"Patient axis is unproven: with no clinical footprint, {cand['symbol']} carries first-in-class "
            f"stratification risk, and the arena should discount confidence here accordingly."),
        "source": {"db": "OpenTargets", "fields": ["drugAndClinicalCandidates"],
                   "synthetic_parts": ["biomarker_stratum"]},
    }


def axis_right_tissue(cand: dict, ev: dict) -> dict:
    # OT has no single-cell tau / malignant fraction. Value is a DESIGNED synthetic
    # prior (TRADEOFF) so the Pareto front is deliberately non-trivial; if no override,
    # fall back to a weak association proxy.
    td = TRADEOFF.get(cand["symbol"], {})
    val = td.get("tissue", round(0.4 + _norm(cand["ot_score"], 0, 0.7) * 0.3, 3))
    note = td.get("note", "no designed prior; weak association-derived placeholder")
    spec = ("sharply tumour-restricted" if val >= 0.75 else
            "moderately specific" if val >= 0.5 else "broadly expressed / non-specific")
    return {
        "value": round(val, 3),
        "confidence": 0.4,
        "cost": 3,  # a real run_experiment (single-cell tau) would resolve this
        "direction": "supports" if val >= 0.6 else "refutes" if val < 0.4 else "neutral",
        "strength": "strong" if val >= 0.75 else "moderate" if val >= 0.5 else "weak",
        "data_origin": "synthetic",
        "finding": "Single-cell tissue specificity (tau) and malignant-vs-stromal fraction are NOT "
                   "available from Open Targets. Value shown is a designed prior "
                   f"({spec}): {note}.",
        "interpretation": (
            f"UNMEASURED axis — this is the highest-value action for the VoI loop to resolve via a "
            f"tier-3 run_experiment (single-cell profiling). The prior says {cand['symbol']} is "
            f"{spec}; if it holds, tissue specificity is "
            f"{'a decisive strength that can offset a weaker tractability or safety axis' if val >= 0.75 else 'a liability that a tumour-selective modality would have to compensate for' if val < 0.4 else 'neutral — unlikely to decide the ranking alone'}. "
            f"Until measured, treat this value as a hypothesis, not evidence."),
        "source": {"db": None, "synthetic_parts": ["tau_specificity", "malignant_fraction"],
                   "designed_tradeoff": bool(td)},
    }


def axis_right_commercial(cand: dict, ev: dict) -> dict:
    # Competitor count is derivable; whitespace read is judgment -> hybrid.
    val = round(0.3 + _norm(0.6 - cand["ot_score"], 0, 0.6) * 0.4, 3)  # crowded top targets -> lower
    return {
        "value": val,
        "confidence": 0.5,
        "cost": 1,
        "direction": "neutral",
        "strength": "weak",
        "data_origin": "hybrid",
        "finding": (
            f"Competitive intensity is approximated from {cand['symbol']}'s prominence as a melanoma "
            f"target (high-association targets tend to be crowded); the explicit competitor count and "
            f"whitespace read are synthesised."),
        "interpretation": (
            f"Crowded field: {cand['symbol']} is a well-trodden target, so commercial differentiation "
            f"must come from a novel modality, payload, or indication niche rather than the target itself."
            if val < 0.4 else
            f"Relative whitespace (synthetic estimate): fewer active programmes leave room to be "
            f"first/best-in-class, though this is the least evidence-backed axis and should not by itself swing the rank."),
        "source": {"db": "OpenTargets", "synthetic_parts": ["competitor_count", "whitespace"]},
    }


# --------------------------------------------------------------------------- #
# Assemble a full report-style card
# --------------------------------------------------------------------------- #

def pick_modality(symbol: str, ev: dict) -> str:
    if symbol in MODALITY:
        return MODALITY[symbol]
    # fallback for any target not in the hand-set map
    tr = ev["tractability"]
    sm = any(t["modality"] == "SM" and t["value"] and "Pocket" in t["label"] for t in tr)
    return "small_molecule" if sm else "antibody"


def build_card(idx: int, cand: dict) -> dict:
    ev = target_evidence(cand["ensembl_id"])
    modality = pick_modality(cand["symbol"], ev)
    axes = {
        "right_target": axis_right_target(cand, ev),
        "right_tissue": axis_right_tissue(cand, ev),
        "right_safety": axis_right_safety(cand, ev),
        "right_patient": axis_right_patient(cand, ev),
        "right_commercial": axis_right_commercial(cand, ev),
        "tractability": axis_tractability(cand, ev, modality),
    }
    unresolved = [a for a, e in axes.items() if e["data_origin"] == "synthetic"]
    return {
        "id": f"H{idx+1}",
        "target": {"symbol": cand["symbol"], "ensembl_id": cand["ensembl_id"]},
        "disease": {"name": DISEASE, "efo_id": EFO},
        "modality": modality,
        "narrative": {
            "target_overview": f"{cand['symbol']} — {ev.get('name') or ''}. "
                               f"{(ev.get('function') or '')[:220]}",
            "pathways": ev["pathways"][:5],
            "liabilities": [axes["right_safety"]["finding"]],
            "evidence_gaps": [axes[a]["finding"] for a in unresolved],
            "proposed_experiments": (
                [{"experiment": "single-cell tau + malignant-fraction profiling",
                  "axis": "right_tissue", "cost_tier": 3,
                  "rationale": "resolves the only unmeasured axis; likely the highest-VoI action"}]
                if "right_tissue" in unresolved else []),
        },
        "axes": axes,
        "label": {"positive": cand["positive"], "max_clinical_phase": cand.get("max_clinical_phase")},
    }


def main() -> None:
    chosen = select_targets()
    cards = [build_card(i, c) for i, c in enumerate(chosen)]
    n_pos = sum(1 for c in cards if c["label"]["positive"])
    real_axes = sum(1 for c in cards for a in c["axes"].values() if a["data_origin"] == "opentargets")
    doc = {
        "meta": {
            "disease": DISEASE, "efo_id": EFO,
            "n_hypotheses": len(cards),
            "n_positive": n_pos,
            "positive_ratio": round(n_pos / len(cards), 3),
            "axes": AXES,
            "card_contract": "per-axis {value[0,1], confidence, cost, direction, strength, "
                             "data_origin, finding, interpretation, source}",
            "data_origin_legend": {
                "opentargets": "real OT field", "hybrid": "real OT + synthesised judgment",
                "synthetic": "not available in OT; placeholder prior (flag for VoI/run_experiment)"},
            "note": "Descriptive report-style cards resembling a Virtual-Biotech division dossier. "
                    "Real where OT reaches; synthetic axes explicitly flagged. No matches faked — "
                    "the arena produces matches from these cards.",
        },
        "hypotheses": cards,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(doc, open(OUT, "w"), indent=2)
    print(f"wrote {OUT}: {len(cards)} hypotheses, {n_pos} positive "
          f"({doc['meta']['positive_ratio']:.0%}), {real_axes} real OT axis-entries")


if __name__ == "__main__":
    main()
