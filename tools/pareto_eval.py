from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import augc as augc_module  # type: ignore
import plot_gain_curves as plot_module  # type: ignore

AXES = [
    "right_target",
    "right_tissue",
    "right_safety",
    "right_patient",
    "right_commercial",
    "tractability",
]

AXIS_TIEBREAK_WEIGHTS = {
    "right_target": 3.0,
    "right_patient": 1.8,
    "right_safety": 1.2,
    "right_commercial": 1.0,
    "right_tissue": 0.5,
    "tractability": 0.8,
}

MIN_AXIS_COVERAGE = 0.2
DEFAULT_LABEL = {"positive": False, "max_clinical_phase": None}
DEFAULT_EFO_ID = "MONDO_0005012"
DEFAULT_COST_TIER = 3


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_labels(path: Path) -> dict[str, dict[str, Any]]:
    rows = _read_json(path)["labels"]
    return {row["symbol"]: row for row in rows}


def _axis_summary(hypothesis: dict[str, Any], axis: str) -> dict[str, Any]:
    return hypothesis.get("axes", {}).get(axis, {})


def _raw_axis_value(hypothesis: dict[str, Any], axis: str) -> float | None:
    value = _axis_summary(hypothesis, axis).get("score")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _axis_confidence(hypothesis: dict[str, Any], axis: str) -> float:
    value = _axis_summary(hypothesis, axis).get("confidence")
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _axis_value(hypothesis: dict[str, Any], axis: str) -> float:
    raw = _raw_axis_value(hypothesis, axis)
    if raw is None:
        return 0.0

    confidence = _axis_confidence(hypothesis, axis)
    adjusted = 0.5 + (raw - 0.5) * confidence
    if axis == "right_tissue":
        adjusted = 0.5 + (adjusted - 0.5) * 0.5
    return max(0.0, min(1.0, adjusted))


def _axis_cost(hypothesis: dict[str, Any], axis: str) -> int:
    observations = {
        obs["observation_id"]: obs for obs in hypothesis.get("observations", [])
    }
    costs = []
    for support in _axis_summary(hypothesis, axis).get("supporting_observations", []):
        obs = observations.get(support.get("observation_id"))
        tier = ((obs or {}).get("cost") or {}).get("tier")
        if isinstance(tier, int):
            costs.append(tier)
    return max(costs) if costs else DEFAULT_COST_TIER


def _active_axes(hypotheses: list[dict[str, Any]]) -> list[str]:
    active = []
    n_hypotheses = max(len(hypotheses), 1)
    for axis in AXES:
        coverage = sum(
            1
            for hypothesis in hypotheses
            if _raw_axis_value(hypothesis.get("_raw", hypothesis), axis) is not None
        )
        if coverage / n_hypotheses >= MIN_AXIS_COVERAGE:
            active.append(axis)
    return active


def _direction(score: float) -> str:
    if score >= 0.67:
        return "supports"
    if score >= 0.34:
        return "neutral"
    return "refutes"


def _strength(score: float) -> str:
    if score >= 0.67:
        return "strong"
    if score >= 0.34:
        return "moderate"
    return "weak"


def _adapt_axis(hypothesis: dict[str, Any], axis: str) -> dict[str, Any]:
    axis_summary = _axis_summary(hypothesis, axis)
    score = _axis_value(hypothesis, axis)
    confidence = _axis_confidence(hypothesis, axis)

    supports = axis_summary.get("supporting_observations", [])
    layers = sorted(
        {
            item.get("evidence_layer")
            for item in supports
            if item.get("evidence_layer")
        }
    )
    backends = sorted(
        {
            item.get("backend_family")
            for item in supports
            if item.get("backend_family")
        }
    )
    missing_layers = axis_summary.get("missing_layers", [])

    parts = []
    if layers:
        parts.append(f"supported by {len(layers)} layer(s): {', '.join(layers)}")
    if missing_layers:
        parts.append(f"missing layers: {', '.join(missing_layers)}")

    return {
        "value": round(score, 4),
        "confidence": round(confidence, 4),
        "cost": _axis_cost(hypothesis, axis),
        "direction": _direction(score),
        "strength": _strength(score),
        "data_origin": "hybrid",
        "finding": "; ".join(parts) if parts else "no successful observations",
        "interpretation": (
            f"{axis} score={score:.3f}, confidence={confidence:.3f}. "
            "Derived from normalized batch evidence for this candidate."
        ),
        "source": {"db": "ToolUniverse", "fields": backends},
    }


def _narrative(hypothesis: dict[str, Any], symbol: str) -> dict[str, Any]:
    evidence_gaps = [
        failure.get("error", {}).get("message", "unknown failure")
        for failure in hypothesis.get("failures", [])
        if failure.get("error")
    ]
    return {
        "target_overview": f"{symbol} candidate adapted from normalized evidence chain.",
        "pathways": [],
        "liabilities": [],
        "evidence_gaps": evidence_gaps,
        "proposed_experiments": [],
    }


def adapt_hypotheses(hypotheses_path: Path, labels_path: Path) -> dict[str, Any]:
    payload = _read_json(hypotheses_path)
    labels = _load_labels(labels_path)
    adapted = []

    for hypothesis in payload["hypotheses"]:
        symbol = hypothesis["target"]["symbol"]
        label = labels.get(symbol, DEFAULT_LABEL)
        adapted.append(
            {
                "id": hypothesis.get("hypothesis_id", symbol),
                "target": hypothesis["target"],
                "disease": hypothesis["disease"],
                "modality": hypothesis.get("modality"),
                "mechanism": hypothesis.get("mechanism"),
                "direction": hypothesis.get("direction"),
                "context": hypothesis.get("context", {}),
                "ot_score": hypothesis.get("ot_score"),
                "narrative": _narrative(hypothesis, symbol),
                "axes": {axis: _adapt_axis(hypothesis, axis) for axis in AXES},
                "label": {
                    "positive": bool(label.get("positive")),
                    "max_clinical_phase": label.get("max_clinical_phase"),
                },
                "_raw": hypothesis,
            }
        )

    return {
        "meta": payload.get("fixture") or payload.get("meta") or {},
        "hypotheses": adapted,
    }


def _dominates(
    left: dict[str, Any],
    right: dict[str, Any],
    active_axes: list[str],
) -> bool:
    left_values = []
    right_values = []

    for axis in active_axes:
        left_raw = _raw_axis_value(left["_raw"], axis)
        right_raw = _raw_axis_value(right["_raw"], axis)
        if left_raw is None or right_raw is None:
            continue
        left_values.append(_axis_value(left["_raw"], axis))
        right_values.append(_axis_value(right["_raw"], axis))

    return bool(left_values) and all(
        a >= b for a, b in zip(left_values, right_values)
    ) and any(a > b for a, b in zip(left_values, right_values))


def _non_dominated_sort(
    hypotheses: list[dict[str, Any]],
    active_axes: list[str],
) -> tuple[list[list[dict[str, Any]]], list[tuple[str, str]]]:
    remaining = list(hypotheses)
    fronts: list[list[dict[str, Any]]] = []
    edges: list[tuple[str, str]] = []

    while remaining:
        front = []
        for candidate in remaining:
            dominated = any(
                _dominates(other, candidate, active_axes)
                for other in remaining
                if other is not candidate
            )
            if not dominated:
                front.append(candidate)

        front_ids = {item["id"] for item in front}
        for candidate in remaining:
            if candidate["id"] in front_ids:
                continue
            for incumbent in front:
                if _dominates(incumbent, candidate, active_axes):
                    edges.append((incumbent["id"], candidate["id"]))

        fronts.append(front)
        remaining = [item for item in remaining if item["id"] not in front_ids]

    return fronts, edges


def _tie_break(front: list[dict[str, Any]], active_axes: list[str]) -> list[dict[str, Any]]:
    ranking = []
    for item in front:
        weighted_value = 0.0
        axis_breakdown: dict[str, float | None] = {}
        for axis in active_axes:
            raw_value = _raw_axis_value(item["_raw"], axis)
            if raw_value is None:
                axis_breakdown[axis] = None
                continue
            contribution = AXIS_TIEBREAK_WEIGHTS[axis] * _axis_value(item["_raw"], axis)
            axis_breakdown[axis] = round(contribution, 4)
            weighted_value += contribution

        ranking.append(
            {
                "hypothesis_id": item["id"],
                "tie_break_score": round(weighted_value, 4),
                "weighted_axis_value": round(weighted_value, 4),
                "axis_breakdown": axis_breakdown,
            }
        )

    ranking.sort(key=lambda row: (row["tie_break_score"], row["hypothesis_id"]), reverse=True)
    return ranking


def build_pareto_result(adapted: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    hypotheses = adapted["hypotheses"]
    active_axes = _active_axes(hypotheses)
    inactive_axes = [axis for axis in AXES if axis not in active_axes]
    fronts, edges = _non_dominated_sort(hypotheses, active_axes)

    front_one = fronts[0] if fronts else []
    tie_break_front = _tie_break(front_one, active_axes) if front_one else []
    tie_break_score = {
        row["hypothesis_id"]: row["tie_break_score"] for row in tie_break_front
    }

    ordered: list[dict[str, Any]] = []
    full_ranking = []
    pareto_front = []

    for rank, front in enumerate(fronts, start=1):
        tie_break = _tie_break(front, active_axes)
        tie_index = {row["hypothesis_id"]: row for row in tie_break}
        sorted_front = sorted(
            front,
            key=lambda item: (
                tie_index[item["id"]]["tie_break_score"],
                tie_index[item["id"]]["weighted_axis_value"],
                item["target"]["symbol"],
            ),
            reverse=True,
        )

        for position, item in enumerate(sorted_front, start=1):
            ordered.append(item)
            full_ranking.append(
                {
                    "hypothesis_id": item["id"],
                    "target": item["target"]["symbol"],
                    "pareto_rank": rank,
                    "front_position": position,
                    "tie_break_score": tie_index[item["id"]]["tie_break_score"],
                }
            )

        if rank == 1:
            for item in sorted_front:
                pareto_front.append(
                    {
                        "hypothesis_id": item["id"],
                        "target": item["target"]["symbol"],
                        "disease": item["disease"]["name"],
                        "modality": item.get("modality"),
                        "front_status": "non_dominated",
                        "tie_break_score": tie_break_score.get(item["id"], 0.0),
                    }
                )

    status_by_id = {item["id"]: "dominated" for item in hypotheses}
    for item in front_one:
        status_by_id[item["id"]] = "front"

    result = {
        "run_metadata": {
            "num_input_hypotheses": len(hypotheses),
            "num_front_hypotheses": len(front_one),
            "num_fronts": len(fronts),
            "num_domination_edges": len(edges),
            "pareto_method": "deterministic_numeric_adapter",
            "active_axes": active_axes,
            "inactive_axes": inactive_axes,
            "algorithm_note": (
                "Standard Pareto dominance over active evidence axes only. "
                "Low-coverage axes are excluded from dominance, missing values "
                "are skipped rather than treated as failures, and tissue is "
                "conservatively shrunk toward neutral until that layer has "
                "stronger calibration."
            ),
        },
        "red_flagged_hypotheses": [],
        "pareto_front": pareto_front,
        "domination_graph": {
            "nodes": [
                {
                    "hypothesis_id": item["id"],
                    "status": status_by_id[item["id"]],
                    "target": item["target"]["symbol"],
                }
                for item in hypotheses
            ],
            "edges": [
                {"source": left, "target": right, "relation": "dominates"}
                for left, right in edges
            ],
        },
        "tie_break_ranking": tie_break_front,
        "full_ranking": full_ranking,
    }
    return result, ordered


def _ranking_payload(
    ranked: list[dict[str, Any]],
    disease: str,
    efo_id: str,
    ranker: str,
    label_set: str,
) -> dict[str, Any]:
    return {
        "meta": {
            "disease": disease,
            "efo_id": efo_id,
            "ranker": ranker,
            "label_set": label_set,
        },
        "ranking": [item["target"]["symbol"] for item in ranked],
    }


def _score_summary(
    ranking_paths: list[Path],
    labels_specs: list[tuple[str, Path]],
) -> dict[str, Any]:
    summary: dict[str, Any] = {"tasks": {}}
    for label_name, labels_path in labels_specs:
        task_rows = []
        for ranking_path in ranking_paths:
            scored = augc_module.score(str(ranking_path), str(labels_path))
            task_rows.append(
                {
                    "ranker": scored.ranker,
                    "labels": label_name,
                    "augc": scored.augc,
                    "hits_at": scored.hits_at,
                    "n_pool": scored.n_pool,
                    "n_positives": scored.n_positives,
                }
            )
        summary["tasks"][label_name] = task_rows
    return summary


def _plot(
    rankings: list[Path],
    labels_specs: list[tuple[str, Path]],
    out_path: Path,
) -> None:
    panels = []
    for i, (label_name, labels_path) in enumerate(labels_specs):
        pool, positives = augc_module._load_labels(str(labels_path))
        perfect = plot_module._perfect_curve(len(pool), len(positives))
        rows = []
        for j, ranking_path in enumerate(rankings):
            label, value, curve = plot_module._curve_for(
                str(ranking_path),
                pool,
                positives,
            )
            rows.append(
                (
                    label,
                    value,
                    curve,
                    plot_module._PALETTE[j % len(plot_module._PALETTE)],
                )
            )
        panels.append((label_name, len(positives), len(pool), perfect, rows))
    plot_module.render_svg(panels, str(out_path), "melanoma_anyclin Pareto gain curves")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Adapt tools hypotheses -> Pareto ranking -> AUGC + gain curves."
    )
    parser.add_argument(
        "--hypotheses",
        default=str(ROOT / "tools/demo/melanoma_anyclin.hypotheses.json"),
    )
    parser.add_argument(
        "--labels-anyclin",
        default=str(ROOT / "eval/data/melanoma_anyclin.labels.json"),
    )
    parser.add_argument(
        "--labels-phase2",
        default=str(ROOT / "eval/data/melanoma.labels.json"),
    )
    parser.add_argument("--outdir", default=str(ROOT / "tools/demo/pareto_eval"))
    args = parser.parse_args()

    hypotheses_path = Path(args.hypotheses)
    labels_anyclin = Path(args.labels_anyclin)
    labels_phase2 = Path(args.labels_phase2)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    adapted = adapt_hypotheses(hypotheses_path, labels_anyclin)
    adapted_path = outdir / "melanoma_anyclin.arena_fixture.json"
    _write_json(
        adapted_path,
        {"hypotheses": [{k: v for k, v in h.items() if k != "_raw"} for h in adapted["hypotheses"]]},
    )

    pareto_result, ranked = build_pareto_result(adapted)
    pareto_path = outdir / "melanoma_anyclin.pareto_result.json"
    _write_json(pareto_path, pareto_result)

    disease_meta = _read_json(hypotheses_path).get("fixture", {}).get("disease", {})
    disease_name = disease_meta.get("name", "melanoma_anyclin")
    efo_id = disease_meta.get("efo_id", DEFAULT_EFO_ID)

    pareto_ranking = _ranking_payload(
        ranked,
        disease_name,
        efo_id,
        "pareto_numeric",
        "melanoma_anyclin",
    )
    pareto_ranking_path = ROOT / "eval/data/melanoma_anyclin.pareto_numeric_ranking.json"
    _write_json(pareto_ranking_path, pareto_ranking)
    _write_json(outdir / "melanoma_anyclin.pareto_numeric_ranking.json", pareto_ranking)

    ranking_paths = [pareto_ranking_path]
    for baseline_name in [
        "melanoma_anyclin.opentargets_ranking.json",
        "melanoma_anyclin.claude_priors_ranking.json",
    ]:
        baseline_path = ROOT / "eval/data" / baseline_name
        if baseline_path.exists():
            ranking_paths.append(baseline_path)

    labels_specs = [
        ("melanoma_anyclin", labels_anyclin),
        ("melanoma_phase2", labels_phase2),
    ]
    score_path = outdir / "melanoma_anyclin.augc_summary.json"
    _write_json(score_path, _score_summary(ranking_paths, labels_specs))

    plot_path = outdir / "melanoma_anyclin.gain_curves.svg"
    _plot(ranking_paths, labels_specs, plot_path)

    print(
        json.dumps(
            {
                "adapted_fixture": str(adapted_path),
                "pareto_result": str(pareto_path),
                "ranking": str(pareto_ranking_path),
                "augc_summary": str(score_path),
                "gain_curves": str(plot_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
