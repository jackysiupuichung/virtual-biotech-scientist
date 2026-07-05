from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.evidence import run_observation, synthesize_axes


OUTPUT_DIR = Path(__file__).resolve().parent
LEGACY_HYPOTHESES_PATH = OUTPUT_DIR / "cutaneous_melanoma_braf.hypotheses.json"
FINAL_HYPOTHESES_PATH = OUTPUT_DIR / "demo_hypotheses.json"

AXIS_ORDER = [
    "right_target",
    "right_tissue",
    "right_safety",
    "right_patient",
    "right_commercial",
    "tractability",
]

CARD_CONTRACT = "per-axis {value[0,1], confidence, cost, direction, strength, data_origin, finding, interpretation, source}"

DATA_ORIGIN_LEGEND = {
    "opentargets": "real OT field",
    "hybrid": "real OT + synthesised judgment",
    "synthetic": "not available in OT; placeholder prior (flag for VoI/run_experiment)",
}


def _build_hypothesis(
    *,
    hypothesis_id: str,
    target_symbol: str,
    disease_name: str,
    disease_efo_id: str,
    modality: str = "small_molecule",
    mechanism: str = "inhibit",
    direction: str = "inhibit",
    ensembl_id: str | None = None,
    context: dict | None = None,
) -> dict:
    return {
        "hypothesis_id": hypothesis_id,
        "target": {"symbol": target_symbol, "ensembl_id": ensembl_id},
        "disease": {"name": disease_name, "efo_id": disease_efo_id},
        "modality": modality,
        "mechanism": mechanism,
        "direction": direction,
        "context": context or {},
    }


def _requests() -> list[dict]:
    braf_melanoma = _build_hypothesis(
        hypothesis_id="hyp_cutaneous_melanoma_braf_demo_v1",
        target_symbol="BRAF",
        ensembl_id="ENSG00000157764",
        disease_name="cutaneous melanoma",
        disease_efo_id="MONDO_0005012",
        context={
            "uniprot_id": "P15056",
            "tissue_type": "skin",
            "hpa_disease_name": "skin_cancer",
            "perturbagen": "vemurafenib",
            "cell_line": "A375",
            "demo_run_id": "v1",
        },
    )
    return [
        {"name": "text_knowledge", "request": {"hypothesis": braf_melanoma, "evidence_layer": "text_knowledge", "axis_id": "right_target"}},
        {"name": "knowledge_graph", "request": {"hypothesis": braf_melanoma, "evidence_layer": "knowledge_graph", "axis_id": "right_target"}},
        {"name": "genetics", "request": {"hypothesis": braf_melanoma, "evidence_layer": "genetics", "axis_id": "right_target"}},
        {"name": "omics", "request": {"hypothesis": braf_melanoma, "evidence_layer": "omics", "axis_id": "right_tissue"}},
        {"name": "single_cell", "request": {"hypothesis": braf_melanoma, "evidence_layer": "single_cell", "axis_id": "right_tissue"}},
        {"name": "perturbation_model", "request": {"hypothesis": braf_melanoma, "evidence_layer": "perturbation_model", "axis_id": "right_target"}},
        {"name": "perturbation_experiment", "request": {"hypothesis": braf_melanoma, "evidence_layer": "perturbation_experiment", "axis_id": "right_target"}},
        {"name": "structure_pharmacology", "request": {"hypothesis": braf_melanoma, "evidence_layer": "structure_pharmacology", "axis_id": "tractability"}},
        {"name": "clinical", "request": {"hypothesis": braf_melanoma, "evidence_layer": "clinical", "axis_id": "right_patient"}},
    ]


def _load_label(symbol: str) -> dict:
    labels = json.loads((REPO_ROOT / "eval" / "data" / "melanoma.labels.json").read_text())["labels"]
    for item in labels:
        if item["symbol"] == symbol:
            return {
                "positive": item["positive"],
                "max_clinical_phase": item["max_clinical_phase"],
            }
    return {"positive": False, "max_clinical_phase": None}


def _direction(score: float) -> str:
    if score >= 0.67:
        return "supports"
    if score >= 0.34:
        return "neutral"
    return "opposes"


def _strength(score: float) -> str:
    if score >= 0.67:
        return "strong"
    if score >= 0.34:
        return "moderate"
    return "weak"


def _source_fields(observations: list[dict]) -> list[str]:
    families = {item["backend"]["family"] for item in observations}
    fields = []
    mapping = {
        "opentargets_genetics_mcp": "association_score",
        "literature_text_mcp": "support_score",
        "kg_reasoning_mcp": "support_score",
        "clinical_trials_mcp": "support_score",
        "cellxgene_single_cell_mcp": "specificity_score",
        "lincs_perturbation_model_mcp": "score",
        "lincs_perturbation_experiment_mcp": "score",
        "alphafold_tooluniverse_mcp": "score",
    }
    for family in sorted(families):
        field = mapping.get(family)
        if field and field not in fields:
            fields.append(field)
    return fields


def _source_db(observations: list[dict]) -> str:
    families = {item["backend"]["family"] for item in observations}
    if families == {"opentargets_genetics_mcp"}:
        return "OpenTargets"
    if families == {"alphafold_tooluniverse_mcp"}:
        return "AlphaFold DB via ToolUniverse"
    if families == {"clinical_trials_mcp"}:
        return "ClinicalTrials.gov via ToolUniverse"
    if families == {"kg_reasoning_mcp"}:
        return "Monarch via ToolUniverse"
    if families == {"literature_text_mcp"}:
        return "Europe PMC via ToolUniverse"
    if families == {"cellxgene_single_cell_mcp"}:
        return "PanglaoDB via ToolUniverse"
    if families:
        return "ToolUniverse"
    return "Unknown"


def _axis_card(axis_id: str, axis_summary: dict, successful_observations: list[dict]) -> dict | None:
    score = axis_summary.get("score")
    confidence = axis_summary.get("confidence")
    if score is None or confidence is None:
        return None
    observations = [
        item for item in successful_observations if item["observation_id"] in {
            support["observation_id"] for support in axis_summary.get("supporting_observations", [])
        }
    ]
    rounded_score = round(float(score), 3)
    rounded_confidence = round(float(confidence), 3)
    source_db = _source_db(observations)
    finding = (
        f"{axis_id} aggregated from {len(observations)} successful evidence layer(s): "
        + ", ".join(sorted({item['evidence_layer'] for item in observations}))
        + f". Normalized score={rounded_score}, confidence={rounded_confidence}."
    )
    interpretation = (
        f"This axis currently trends {_direction(rounded_score)} with {_strength(rounded_score)} strength "
        f"based on returned ToolUniverse evidence."
    )
    return {
        "value": rounded_score,
        "confidence": rounded_confidence,
        "cost": max((item["cost"]["tier"] for item in observations), default=1),
        "direction": _direction(rounded_score),
        "strength": _strength(rounded_score),
        "data_origin": "hybrid",
        "finding": finding,
        "interpretation": interpretation,
        "source": {
            "db": source_db,
            "fields": _source_fields(observations),
        },
    }


def _build_narrative(hypothesis: dict, successful_observations: list[dict], failed_payloads: list[dict]) -> dict:
    top_article = None
    for item in successful_observations:
        if item["evidence_layer"] == "text_knowledge":
            articles = item["provenance"]["raw_payload"].get("top_articles", [])
            if articles:
                top_article = articles[0]
                break
    target_overview = (
        top_article["title"]
        if top_article and top_article.get("title")
        else f"{hypothesis['target']['symbol']} evidence dossier assembled from ToolUniverse live layers."
    )
    pathways = []
    for item in successful_observations:
        if item["evidence_layer"] == "knowledge_graph":
            for assoc in item["provenance"]["raw_payload"].get("matched_associations", [])[:5]:
                predicate = assoc.get("predicate")
                obj = assoc.get("object")
                snippet = " ".join(part for part in [predicate, obj] if part)
                if snippet:
                    pathways.append(snippet)
    liabilities = []
    single_cell_obs = next((item for item in successful_observations if item["evidence_layer"] == "single_cell"), None)
    if single_cell_obs:
        records = single_cell_obs["provenance"]["raw_payload"].get("matched_records", [])[:3]
        if records:
            liabilities.append(
                "Top cell-type contexts: " + ", ".join(
                    f"{row.get('cell_type')} ({row.get('organ')})" for row in records if row.get("cell_type")
                )
            )
    evidence_gaps = []
    for failure in failed_payloads:
        message = (failure.get("error") or {}).get("message")
        if message:
            evidence_gaps.append(f"{failure['name']} failed: {message}")
    proposed_experiments = []
    if any(item["name"] == "omics" for item in failed_payloads):
        proposed_experiments.append(
            {
                "experiment": "replace HPA skin-cancer lookup with a melanoma-compatible expression source",
                "axis": "right_tissue",
                "cost_tier": 2,
                "rationale": "current HPA disease mapping does not support skin cancer in ToolUniverse",
            }
        )
    return {
        "target_overview": target_overview,
        "pathways": pathways,
        "liabilities": liabilities,
        "evidence_gaps": evidence_gaps,
        "proposed_experiments": proposed_experiments,
    }


def _build_template_output(hypothesis: dict, successful_observations: list[dict], failed_payloads: list[dict]) -> dict:
    label = _load_label(hypothesis["target"]["symbol"])
    axis_summaries = synthesize_axes(observations=successful_observations, failures=[])
    axes = {}
    for axis_id in AXIS_ORDER:
        card = _axis_card(axis_id, axis_summaries[axis_id], successful_observations)
        if card is not None:
            axes[axis_id] = card
    positives = 1 if label["positive"] else 0
    return {
        "meta": {
            "disease": hypothesis["disease"]["name"],
            "efo_id": hypothesis["disease"]["efo_id"],
            "n_hypotheses": 1,
            "n_positive": positives,
            "positive_ratio": float(positives),
            "axes": AXIS_ORDER,
            "card_contract": CARD_CONTRACT,
            "data_origin_legend": DATA_ORIGIN_LEGEND,
            "note": "Live ToolUniverse-backed demo card. Failed layers are omitted from axes and documented under narrative evidence_gaps.",
        },
        "hypotheses": [
            {
                "id": "H1",
                "target": hypothesis["target"],
                "disease": hypothesis["disease"],
                "modality": hypothesis["modality"],
                "narrative": _build_narrative(hypothesis, successful_observations, failed_payloads),
                "axes": axes,
                "label": label,
            }
        ],
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_HYPOTHESES_PATH.unlink(missing_ok=True)
    LEGACY_HYPOTHESES_PATH.unlink(missing_ok=True)
    final_hypothesis = None
    successful_observations: list[dict] = []
    failed_payloads: list[dict] = []

    for item in _requests():
        request = item["request"]
        if final_hypothesis is None:
            final_hypothesis = request["hypothesis"]
        result = run_observation(request)
        status = result.get("status", "unknown")
        if status == "completed":
            successful_observations.append(result["observation"])
            continue
        failed_payloads.append(
            {
                "name": request["evidence_layer"],
                "axis": request["axis_id"],
                "error": result.get("error"),
                "failures": result.get("failures", []),
            }
        )
    if final_hypothesis is None:
        return
    final_result = _build_template_output(
        final_hypothesis,
        successful_observations,
        failed_payloads,
    )
    FINAL_HYPOTHESES_PATH.write_text(json.dumps(final_result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
