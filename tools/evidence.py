from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from dataclasses import dataclass
from typing import Any
import uuid


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import opentargets
from tools.schema import (
    AxisId,
    BackendCapability,
    BackendInfo,
    BackendStatus,
    CostInfo,
    EvidenceLayer,
    EvidenceRequest,
    Observation,
    ProvenanceInfo,
    ValueScale,
    TherapeuticHypothesis,
    schema_to_dict,
)

try:  # pragma: no cover
    from tooluniverse.mcp_tool_registry import register_mcp_tool, start_mcp_server
except Exception:  # pragma: no cover
    register_mcp_tool = None
    start_mcp_server = None


_TOOLUNIVERSE_WORKSPACE = REPO_ROOT / ".tooluniverse-workspace"
_TOOLUNIVERSE_CACHE_DIR = REPO_ROOT / ".tooluniverse"
_OBSERVATION_CACHE_DIR = Path(
    os.getenv(
        "VBS_CACHE_DIR",
        os.getenv("VBS_PREDICTIVE_CACHE_DIR", Path(__file__).resolve().parent / ".predictive_cache"),
    )
)
_TOOLUNIVERSE_READY = any(
    candidate.exists()
    for candidate in (
        REPO_ROOT / ".venv-tu131" / "bin" / "python",
        REPO_ROOT / ".venv" / "bin" / "python",
    )
)
DEFAULT_SERVER_NAME = "VBS Evidence Server"
DEFAULT_SERVER_PORT = int(os.getenv("VBS_MCP_PORT", os.getenv("VBS_PREDICTIVE_MCP_PORT", "8011")))

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "vbs_list_capabilities": {"type": "object", "properties": {}},
    "vbs_validate_hypothesis": {
        "type": "object",
        "properties": {
            "hypothesis": {"type": "object"},
            "evidence_layer": {"type": "string"},
            "axis_id": {"type": "string"},
            "objective": {"type": "string"},
            "backend_preference": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["hypothesis", "evidence_layer", "axis_id"],
    },
    "vbs_preview_observation": {
        "type": "object",
        "properties": {
            "hypothesis": {"type": "object"},
            "evidence_layer": {"type": "string"},
            "axis_id": {"type": "string"},
            "objective": {"type": "string"},
            "backend_preference": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["hypothesis", "evidence_layer", "axis_id"],
    },
    "vbs_run_observation": {
        "type": "object",
        "properties": {
            "hypothesis": {"type": "object"},
            "evidence_layer": {"type": "string"},
            "axis_id": {"type": "string"},
            "objective": {"type": "string"},
            "backend_preference": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["hypothesis", "evidence_layer", "axis_id"],
    },
    "vbs_get_observation": {
        "type": "object",
        "properties": {"observation_id": {"type": "string"}},
        "required": ["observation_id"],
    },
}


DEFAULT_STAGE_PLAN: list[dict[str, Any]] = [
    {
        "stage_id": "stage_1_foundation",
        "title": "Text And Knowledge Graph",
        "items": [
            ("text_knowledge", "right_target"),
            ("knowledge_graph", "right_target"),
        ],
    },
    {
        "stage_id": "stage_2_multi_omics",
        "title": "Multi-Omics",
        "items": [("omics", "right_tissue")],
    },
    {
        "stage_id": "stage_3_cellular_context",
        "title": "Single-Cell, Spatial Omics, And Computational Perturbation",
        "items": [
            ("single_cell", "right_tissue"),
            ("spatial_omics", "right_tissue"),
            ("perturbation_model", "right_target"),
        ],
    },
    {
        "stage_id": "stage_4_human_genetics",
        "title": "Human Genetic Causal Evidence",
        "items": [("genetics", "right_target")],
    },
    {
        "stage_id": "stage_5_experimental_perturbation",
        "title": "Experimental Perturbation",
        "items": [("perturbation_experiment", "right_target")],
    },
    {
        "stage_id": "stage_6_pharmacology_structure",
        "title": "Pharmacological Validation And Structure",
        "items": [("structure_pharmacology", "tractability")],
    },
    {
        "stage_id": "stage_7_clinical",
        "title": "Clinical",
        "items": [("clinical", "right_patient")],
    },
]

DEFAULT_LAYER_PLAN: list[tuple[str, str]] = [
    item
    for stage in DEFAULT_STAGE_PLAN
    for item in stage["items"]
]


LAYER_AXIS_MATRIX: dict[str, dict[str, float]] = {
    "text_knowledge": {
        "right_target": 1.0,
        "right_patient": 0.5,
        "right_commercial": 0.25,
    },
    "knowledge_graph": {
        "right_target": 1.0,
        "right_patient": 0.5,
    },
    "omics": {
        "right_tissue": 1.0,
        "right_target": 0.5,
        "right_safety": 0.25,
    },
    "single_cell": {
        "right_tissue": 1.0,
        "right_safety": 0.5,
        "right_target": 0.5,
    },
    "spatial_omics": {
        "right_tissue": 1.0,
        "right_safety": 0.5,
        "right_target": 0.5,
    },
    "perturbation_model": {
        "right_target": 1.0,
        "right_patient": 0.5,
        "right_safety": 0.25,
    },
    "genetics": {
        "right_target": 1.0,
        "right_patient": 0.5,
    },
    "perturbation_experiment": {
        "right_target": 1.0,
        "right_safety": 0.5,
        "right_patient": 0.5,
    },
    "structure_pharmacology": {
        "tractability": 1.0,
        "right_target": 0.5,
        "right_safety": 0.25,
    },
    "clinical": {
        "right_patient": 1.0,
        "right_commercial": 0.5,
        "right_safety": 0.5,
        "right_target": 0.25,
    },
}


TARGET_PRESETS: dict[str, dict[str, Any]] = {
    "EGFR": {
        "hypothesis_id": "hyp_egfr_luad_demo_v3",
        "disease_name": "lung adenocarcinoma",
        "disease_efo_id": "MONDO_0005061",
        "ensembl_id": "ENSG00000146648",
        "uniprot_id": "P00533",
        "tissue_type": "lung",
        "hpa_disease_name": "lung_cancer",
        "perturbagen": "gefitinib",
        "cell_line": "A549",
        "demo_run_id": "v3",
    },
    "CFTR": {
        "hypothesis_id": "hyp_cftr_cf_demo_v3",
        "disease_name": "cystic fibrosis",
        "disease_efo_id": "MONDO_0009061",
        "ensembl_id": "ENSG00000001626",
        "uniprot_id": "P13569",
        "tissue_type": "lung",
        "demo_run_id": "v3",
    },
    "EPCAM": {
        "hypothesis_id": "hyp_epcam_luad_demo_v3",
        "disease_name": "lung adenocarcinoma",
        "disease_efo_id": "MONDO_0005061",
        "ensembl_id": "ENSG00000119888",
        "tissue_type": "lung",
        "hpa_disease_name": "lung_cancer",
        "demo_run_id": "v3",
    },
}


CAPABILITIES: list[BackendCapability] = [
    BackendCapability(
        backend_family="opentargets_genetics_mcp",
        evidence_layer=EvidenceLayer.GENETICS,
        status=BackendStatus.LIVE,
        axes=[AxisId.RIGHT_TARGET],
        required_hypothesis_fields=["target.symbol", "disease.efo_id"],
        default_cost_tier=1,
        transport="mcp",
        description="Genetic and disease-association evidence via ToolUniverse/Open Targets.",
        configured=_TOOLUNIVERSE_READY,
    ),
    BackendCapability(
        backend_family="cellxgene_single_cell_mcp",
        evidence_layer=EvidenceLayer.SINGLE_CELL,
        status=BackendStatus.LIVE,
        axes=[AxisId.RIGHT_TISSUE],
        required_hypothesis_fields=["target.symbol"],
        default_cost_tier=3,
        transport="mcp",
        description="Single-cell tissue specificity and malignant-localisation evidence.",
        configured=_TOOLUNIVERSE_READY or bool(os.getenv("VBS_SINGLE_CELL_MCP_TOOL")),
    ),
    BackendCapability(
        backend_family="spatial_omics_stub",
        evidence_layer=EvidenceLayer.SPATIAL_OMICS,
        status=BackendStatus.STUB,
        axes=[AxisId.RIGHT_TISSUE],
        required_hypothesis_fields=["target.symbol"],
        default_cost_tier=2,
        transport="stub",
        description="Placeholder spatial-omics layer for staged evidence-chain construction.",
        configured=True,
    ),
    BackendCapability(
        backend_family="alphafold_tooluniverse_mcp",
        evidence_layer=EvidenceLayer.STRUCTURE_PHARMACOLOGY,
        status=BackendStatus.LIVE,
        axes=[AxisId.TRACTABILITY],
        required_hypothesis_fields=["target.symbol", "modality"],
        default_cost_tier=3,
        transport="mcp",
        description="AlphaFold summary-backed structure/pharmacology evidence via ToolUniverse.",
        configured=_TOOLUNIVERSE_READY,
    ),
    BackendCapability(
        backend_family="literature_text_mcp",
        evidence_layer=EvidenceLayer.TEXT_KNOWLEDGE,
        status=BackendStatus.RETRIEVAL_BACKED,
        axes=[AxisId.RIGHT_TARGET, AxisId.RIGHT_PATIENT, AxisId.RIGHT_COMMERCIAL],
        required_hypothesis_fields=["target.symbol", "disease.name"],
        default_cost_tier=1,
        transport="mcp",
        description="Literature-backed evidence retrieval and summarization.",
        configured=_TOOLUNIVERSE_READY or bool(os.getenv("VBS_TEXT_MCP_TOOL")),
    ),
    BackendCapability(
        backend_family="kg_reasoning_mcp",
        evidence_layer=EvidenceLayer.KNOWLEDGE_GRAPH,
        status=BackendStatus.RETRIEVAL_BACKED,
        axes=[AxisId.RIGHT_TARGET, AxisId.RIGHT_PATIENT],
        required_hypothesis_fields=["target.symbol", "disease.name"],
        default_cost_tier=1,
        transport="mcp",
        description="Knowledge-graph and ontology-backed evidence retrieval.",
        configured=_TOOLUNIVERSE_READY or bool(os.getenv("VBS_KG_MCP_TOOL")),
    ),
    BackendCapability(
        backend_family="clinical_trials_mcp",
        evidence_layer=EvidenceLayer.CLINICAL,
        status=BackendStatus.RETRIEVAL_BACKED,
        axes=[AxisId.RIGHT_PATIENT, AxisId.RIGHT_COMMERCIAL],
        required_hypothesis_fields=["target.symbol", "disease.name"],
        default_cost_tier=1,
        transport="mcp",
        description="Clinical precedent and trial evidence.",
        configured=_TOOLUNIVERSE_READY or bool(os.getenv("VBS_CLINICAL_MCP_TOOL")),
    ),
    BackendCapability(
        backend_family="hpa_omics_mcp",
        evidence_layer=EvidenceLayer.OMICS,
        status=BackendStatus.RETRIEVAL_BACKED,
        axes=[AxisId.RIGHT_TARGET, AxisId.RIGHT_TISSUE],
        required_hypothesis_fields=["target.symbol", "disease.name"],
        default_cost_tier=2,
        transport="mcp",
        description="Bulk-expression and disease-vs-normal omics evidence via Human Protein Atlas.",
        configured=_TOOLUNIVERSE_READY,
    ),
    BackendCapability(
        backend_family="lincs_perturbation_model_mcp",
        evidence_layer=EvidenceLayer.PERTURBATION_MODEL,
        status=BackendStatus.LIVE,
        axes=[AxisId.RIGHT_TARGET, AxisId.RIGHT_PATIENT],
        required_hypothesis_fields=["target.symbol"],
        default_cost_tier=3,
        transport="mcp",
        description="Perturbation-model proxy evidence via ToolUniverse LINCS signature search.",
        configured=_TOOLUNIVERSE_READY,
    ),
    BackendCapability(
        backend_family="lincs_perturbation_experiment_mcp",
        evidence_layer=EvidenceLayer.PERTURBATION_EXPERIMENT,
        status=BackendStatus.LIVE,
        axes=[AxisId.RIGHT_TARGET, AxisId.RIGHT_SAFETY],
        required_hypothesis_fields=["target.symbol", "disease.name"],
        default_cost_tier=3,
        transport="mcp",
        description="Perturbation-experiment evidence via ToolUniverse LINCS signature search.",
        configured=_TOOLUNIVERSE_READY,
    ),
]


@dataclass
class BackendResult:
    ok: bool
    payload: dict[str, Any] = None  # type: ignore[assignment]
    error: dict[str, Any] | None = None


def get_capabilities() -> list[BackendCapability]:
    return list(CAPABILITIES)


def find_capabilities(evidence_layer: EvidenceLayer, axis_id: AxisId) -> list[BackendCapability]:
    matches = [
        capability
        for capability in CAPABILITIES
        if capability.evidence_layer == evidence_layer and axis_id in capability.axes
    ]
    return sorted(
        matches,
        key=lambda item: (
            item.status != BackendStatus.RETRIEVAL_BACKED,
            item.status != BackendStatus.LIVE,
            item.backend_family,
        ),
    )


def capabilities_by_layer() -> dict[str, list[BackendCapability]]:
    grouped: dict[str, list[BackendCapability]] = {}
    for capability in CAPABILITIES:
        grouped.setdefault(capability.evidence_layer.value, []).append(capability)
    return grouped


def _cache_paths(backend_family: str, cache_key: str) -> tuple[Path, Path]:
    family_dir = _OBSERVATION_CACHE_DIR / backend_family
    by_id_dir = _OBSERVATION_CACHE_DIR / "by_id"
    family_dir.mkdir(parents=True, exist_ok=True)
    by_id_dir.mkdir(parents=True, exist_ok=True)
    return family_dir / f"{cache_key}.json", by_id_dir


def _request_payload(request: EvidenceRequest) -> dict[str, Any]:
    return {
        "hypothesis": schema_to_dict(request.hypothesis),
        "evidence_layer": request.evidence_layer.value,
        "axis_id": request.axis_id.value,
        "objective": request.objective,
        "backend_preference": request.backend_preference,
    }


def _cache_key(backend_family: str, request: EvidenceRequest) -> str:
    payload = {"backend_family": backend_family, "request": _request_payload(request)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _legacy_cache_paths(backend_family: str, request: EvidenceRequest) -> list[Path]:
    if backend_family != "alphafold_tooluniverse_mcp":
        return []
    legacy_key = _cache_key("boltz2_tooluniverse_mcp", request)
    return [_OBSERVATION_CACHE_DIR / "boltz2_tooluniverse_mcp" / f"{legacy_key}.json"]


def _normalize_cached_observation(observation: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(observation)
    normalized.pop("uncertainty", None)
    backend = normalized.get("backend")
    if isinstance(backend, dict):
        normalized_backend = dict(backend)
        if (
            normalized_backend.get("family") == "boltz2_tooluniverse_mcp"
            and normalized_backend.get("model_name") == "alphafold_get_summary"
        ):
            normalized_backend["family"] = "alphafold_tooluniverse_mcp"
        normalized["backend"] = normalized_backend
        backend = normalized_backend
    provenance = normalized.get("provenance")
    if isinstance(provenance, dict) and isinstance(backend, dict):
        notes = provenance.get("notes")
        if isinstance(notes, list) and backend.get("family") == "alphafold_tooluniverse_mcp":
            provenance = dict(provenance)
            provenance["notes"] = [
                "Derived from alphafold_tooluniverse_mcp."
                if note == "Derived from boltz2_tooluniverse_mcp."
                else note
                for note in notes
            ]
            normalized["provenance"] = provenance
    return normalized


def _write_cached_observation(observation: dict[str, Any]) -> None:
    cache_path, by_id_dir = _cache_paths(
        observation["backend"]["family"],
        observation["provenance"]["input_hash"],
    )
    payload = json.dumps(observation, indent=2)
    cache_path.write_text(payload, encoding="utf-8")
    (by_id_dir / f"{observation['observation_id']}.json").write_text(payload, encoding="utf-8")


def _load_cached_observation(capability: BackendCapability, request: EvidenceRequest) -> dict[str, Any] | None:
    cache_path, _ = _cache_paths(capability.backend_family, _cache_key(capability.backend_family, request))
    for candidate in [cache_path, *_legacy_cache_paths(capability.backend_family, request)]:
        if candidate.exists():
            return _normalize_cached_observation(json.loads(candidate.read_text(encoding="utf-8")))
    return None


def _read_observation_by_id(observation_id: str) -> dict[str, Any] | None:
    path = _OBSERVATION_CACHE_DIR / "by_id" / f"{observation_id}.json"
    if not path.exists():
        return None
    return _normalize_cached_observation(json.loads(path.read_text(encoding="utf-8")))


def _get_field(hypothesis: TherapeuticHypothesis, dotted_path: str) -> Any:
    value: Any = hypothesis
    for part in dotted_path.split("."):
        if hasattr(value, part):
            value = getattr(value, part)
        elif isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def _missing_fields(hypothesis: TherapeuticHypothesis, capability: BackendCapability) -> list[str]:
    return [
        field_path
        for field_path in capability.required_hypothesis_fields
        if _get_field(hypothesis, field_path) in (None, "", [], {})
    ]


def _candidate_order(request: EvidenceRequest) -> list[BackendCapability]:
    preferred = set(request.backend_preference)

    def sort_key(item: BackendCapability) -> tuple[int, int, str]:
        return (
            0 if item.backend_family in preferred else 1,
            {BackendStatus.RETRIEVAL_BACKED: 0, BackendStatus.LIVE: 1, BackendStatus.STUB: 2}[item.status],
            item.backend_family,
        )

    return sorted(find_capabilities(request.evidence_layer, request.axis_id), key=sort_key)


def clamp_score(value: float | int | None, default: float = 0.0) -> float:
    if value is None:
        return default
    numeric = float(value)
    if numeric < 0.0:
        return 0.0
    if numeric > 1.0:
        return 1.0
    return numeric


def confidence_from_payload(raw_payload: dict[str, Any]) -> float:
    if "confidence" in raw_payload:
        return clamp_score(raw_payload["confidence"], default=0.5)
    if "uncertainty" in raw_payload:
        return clamp_score(1.0 - float(raw_payload["uncertainty"]), default=0.5)
    return 0.5


def normalized_value(
    *,
    evidence_layer: EvidenceLayer,
    raw_payload: dict[str, Any],
) -> float:
    if "normalized_value" in raw_payload:
        return clamp_score(raw_payload["normalized_value"])
    if evidence_layer == EvidenceLayer.GENETICS:
        return clamp_score(raw_payload.get("association_score"))
    if evidence_layer in {EvidenceLayer.SINGLE_CELL, EvidenceLayer.SPATIAL_OMICS}:
        return clamp_score(raw_payload.get("specificity_score"))
    if evidence_layer == EvidenceLayer.STRUCTURE_PHARMACOLOGY:
        if "affinity_probability_binary" in raw_payload:
            return clamp_score(raw_payload.get("affinity_probability_binary"))
        return clamp_score(raw_payload.get("score"))
    if evidence_layer in {
        EvidenceLayer.TEXT_KNOWLEDGE,
        EvidenceLayer.KNOWLEDGE_GRAPH,
        EvidenceLayer.CLINICAL,
    }:
        return clamp_score(raw_payload.get("support_score"))
    return clamp_score(raw_payload.get("score"), default=0.0)


def build_observation(
    *,
    observation_id: str,
    hypothesis_id: str,
    evidence_layer: EvidenceLayer,
    axis_id: AxisId,
    capability: BackendCapability,
    raw_payload: dict[str, Any],
    input_hash: str,
    used_cache: bool,
    raw_artifact_path: str | None = None,
    notes: list[str] | None = None,
) -> Observation:
    return Observation(
        observation_id=observation_id,
        hypothesis_id=hypothesis_id,
        evidence_layer=evidence_layer,
        axis_id=axis_id,
        value=normalized_value(evidence_layer=evidence_layer, raw_payload=raw_payload),
        value_scale=ValueScale(),
        confidence=confidence_from_payload(raw_payload),
        cost=CostInfo(
            tier=capability.default_cost_tier,
            expected_runtime_sec=raw_payload.get("expected_runtime_sec"),
            used_cache=used_cache,
        ),
        backend=BackendInfo(
            family=capability.backend_family,
            status=BackendStatus(capability.status),
            transport=capability.transport,
            model_name=raw_payload.get("model_name"),
        ),
        provenance=ProvenanceInfo.now(
            input_hash=input_hash,
            raw_payload=raw_payload,
            raw_artifact_path=raw_artifact_path,
            notes=notes,
        ),
        status="completed",
        rationale=raw_payload.get("rationale"),
    )


def _axis_entry(axis_id: AxisId) -> dict[str, Any]:
    return {
        "axis_id": axis_id.value,
        "score": None,
        "confidence": None,
        "supporting_observations": [],
        "missing_layers": [],
        "contribution_weight_sum": 0.0,
    }


def synthesize_axes(
    *,
    observations: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    axis_results = {axis.value: _axis_entry(axis) for axis in AxisId}
    observed_layers = {item["evidence_layer"] for item in observations}
    failed_layers = {item["evidence_layer"] for item in failures}

    for observation in observations:
        layer = observation["evidence_layer"]
        contributions = LAYER_AXIS_MATRIX.get(layer, {})
        for axis_id, weight in contributions.items():
            axis_result = axis_results[axis_id]
            axis_result["supporting_observations"].append(
                {
                    "observation_id": observation["observation_id"],
                    "evidence_layer": layer,
                    "source_axis": observation["axis_id"],
                    "value": observation["value"],
                    "confidence": observation["confidence"],
                    "weight": weight,
                    "backend_family": observation["backend"]["family"],
                }
            )

    for axis_id, axis_result in axis_results.items():
        supports = axis_result["supporting_observations"]
        if supports:
            total_weight = sum(item["weight"] for item in supports)
            weighted_value = sum(item["value"] * item["weight"] for item in supports)
            weighted_confidence = sum(item["confidence"] * item["weight"] for item in supports)
            axis_result["contribution_weight_sum"] = total_weight
            axis_result["score"] = weighted_value / total_weight if total_weight else None
            axis_result["confidence"] = weighted_confidence / total_weight if total_weight else None
        axis_result["missing_layers"] = sorted(
            layer
            for layer, contributions in LAYER_AXIS_MATRIX.items()
            if axis_id in contributions and layer not in observed_layers and layer in failed_layers
        )

    return axis_results


def _tooluniverse_python() -> str | None:
    for candidate in (
        REPO_ROOT / ".venv-tu131" / "bin" / "python",
        REPO_ROOT / ".venv" / "bin" / "python",
    ):
        if candidate.exists():
            return str(candidate)
    return None


def _tooluniverse_env() -> dict[str, str]:
    _TOOLUNIVERSE_WORKSPACE.mkdir(parents=True, exist_ok=True)
    _TOOLUNIVERSE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["HOME"] = str(REPO_ROOT)
    env["TOOLUNIVERSE_CACHE_DIR"] = str(_TOOLUNIVERSE_CACHE_DIR)
    env["TOOLUNIVERSE_HOME"] = str(_TOOLUNIVERSE_WORKSPACE)
    return env


def _hpa_disease_name(disease_name: str) -> str:
    name = disease_name.lower()
    mappings = [
        ("lung", "lung_cancer"),
        ("breast", "breast_cancer"),
        ("colon", "colon_cancer"),
        ("colorectal", "colon_cancer"),
        ("brain", "brain_cancer"),
        ("glioma", "brain_cancer"),
        ("liver", "liver_cancer"),
        ("hepat", "liver_cancer"),
        ("prostate", "prostate_cancer"),
        ("kidney", "kidney_cancer"),
        ("renal", "kidney_cancer"),
        ("pancre", "pancreatic_cancer"),
        ("stomach", "stomach_cancer"),
        ("gastric", "stomach_cancer"),
        ("ovar", "ovarian_cancer"),
    ]
    for needle, mapped in mappings:
        if needle in name:
            return mapped
    return "lung_cancer"


def _tissue_type(disease_name: str, context: dict[str, Any]) -> str:
    if context.get("tissue_type"):
        return str(context["tissue_type"])
    name = disease_name.lower()
    mappings = [
        ("lung", "lung"),
        ("breast", "breast"),
        ("colon", "colon"),
        ("colorectal", "colon"),
        ("brain", "brain"),
        ("glioma", "brain"),
        ("liver", "liver"),
        ("hepat", "liver"),
        ("prostate", "prostate"),
        ("kidney", "kidney"),
        ("renal", "kidney"),
        ("pancre", "pancreas"),
        ("stomach", "stomach"),
        ("gastric", "stomach"),
        ("ovar", "ovary"),
    ]
    for needle, mapped in mappings:
        if needle in name:
            return mapped
    return "lung"


def _mock_payload(request: EvidenceRequest, backend_family: str) -> dict[str, Any] | None:
    payload = request.hypothesis.context.get("mock_backend_payloads", {}).get(backend_family)
    return dict(payload) if payload is not None else None


def _decode_tooluniverse_subprocess_output(
    *,
    completed: subprocess.CompletedProcess[str],
    not_found_message: str,
) -> BackendResult:
    if completed.returncode != 0:
        return BackendResult(
            ok=False,
            error={
                "type": "backend_unavailable",
                "message": completed.stderr.strip() or "ToolUniverse subprocess failed.",
            },
        )
    stdout = completed.stdout.strip().splitlines()
    if not stdout:
        return BackendResult(
            ok=False,
            error={
                "type": "backend_unavailable",
                "message": "ToolUniverse produced no JSON output.",
            },
        )
    try:
        payload = json.loads(stdout[-1])
    except json.JSONDecodeError:
        return BackendResult(
            ok=False,
            error={
                "type": "backend_unavailable",
                "message": "ToolUniverse output was not valid JSON.",
            },
        )
    if payload.get("not_found"):
        return BackendResult(ok=False, error={"type": "not_found", "message": not_found_message})
    if payload.get("error"):
        return BackendResult(
            ok=False,
            error={
                "type": "backend_unavailable",
                "message": f"ToolUniverse error: {payload['error']}",
            },
        )
    return BackendResult(ok=True, payload=payload)


def _run_genetics_with_tooluniverse(*, request: EvidenceRequest, python_bin: str) -> BackendResult:
    script = """
import json
import sys
from tooluniverse import ToolUniverse

efo_id = sys.argv[1]
target_symbol = sys.argv[2]
workspace = sys.argv[3]
tu = ToolUniverse(workspace=workspace, use_global=False)
tu.load_tools(categories=['opentarget'])
result = tu.run_one_function({
    'name': 'OpenTargets_get_associated_targets_by_disease_efoId',
    'arguments': {'efoId': efo_id}
})

if isinstance(result, dict) and result.get('status') == 'error':
    print(json.dumps({'error': result.get('error')}))
    raise SystemExit(0)

if not isinstance(result, dict):
    print(json.dumps({'error': 'unexpected_result_type'}))
    raise SystemExit(0)

rows = (
    result.get('data', {})
    .get('disease', {})
    .get('associatedTargets', {})
    .get('rows', [])
)
match = None
for row in rows:
    target = row.get('target', {})
    if target.get('approvedSymbol') == target_symbol:
        match = row
        break

if match is None:
    print(json.dumps({'not_found': True}))
else:
    print(json.dumps({
        'association_score': match.get('score'),
        'confidence': 0.8,
        'rationale': 'Normalized from ToolUniverse Open Targets associatedTargets result.',
        'backend_source': 'tooluniverse',
        'raw_target': match.get('target', {}),
    }))
"""
    try:
        completed = subprocess.run(
            [
                python_bin,
                "-c",
                script,
                request.hypothesis.disease.efo_id or "",
                request.hypothesis.target.symbol,
                str(_TOOLUNIVERSE_WORKSPACE),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=_tooluniverse_env(),
        )
    except Exception as exc:
        return BackendResult(
            ok=False,
            error={"type": "backend_unavailable", "message": f"ToolUniverse execution failed locally: {exc}"},
        )
    return _decode_tooluniverse_subprocess_output(
        completed=completed,
        not_found_message=f"No ToolUniverse/Open Targets association found for {request.hypothesis.target.symbol}.",
    )


def _run_genetics(request: EvidenceRequest) -> BackendResult:
    mock = _mock_payload(request, "opentargets_genetics_mcp")
    if mock is not None:
        return BackendResult(ok=True, payload=mock)
    if not request.hypothesis.disease.efo_id or not request.hypothesis.target.symbol:
        return BackendResult(
            ok=False,
            error={
                "type": "hypothesis_invalid",
                "message": "Genetics backend requires disease.efo_id and target.symbol.",
            },
        )
    python_bin = _tooluniverse_python()
    if python_bin is not None:
        result = _run_genetics_with_tooluniverse(request=request, python_bin=python_bin)
        if result.ok:
            return result
    try:
        candidates = opentargets.candidates(
            request.hypothesis.disease.efo_id,
            size=int(request.hypothesis.context.get("opentargets_scan_size", 500)),
            probe_filter=False,
        )
    except Exception as exc:
        return BackendResult(
            ok=False,
            error={"type": "remote_inference_failed", "message": f"Open Targets query failed: {exc}"},
        )
    match = next(
        (item for item in candidates if item.symbol == request.hypothesis.target.symbol),
        None,
    )
    if match is None:
        return BackendResult(
            ok=False,
            error={
                "type": "not_found",
                "message": f"No Open Targets association found for {request.hypothesis.target.symbol}.",
            },
        )
    return BackendResult(
        ok=True,
        payload={
            "association_score": match.ot_score,
            "confidence": 0.8,
            "rationale": "Normalized from Open Targets disease-target association.",
            "backend_source": "local_opentargets_client",
        },
    )


def _run_single_cell_with_tooluniverse(*, request: EvidenceRequest, python_bin: str) -> BackendResult:
    script = """
import json
import sys
from tooluniverse import ToolUniverse

target_symbol = sys.argv[1]
workspace = sys.argv[2]
tu = ToolUniverse(workspace=workspace, use_global=False)
tu.load_tools(categories=['panglaodb'])
result = tu.run_one_function({
    'name': 'PanglaoDB_cell_types_for_gene',
    'arguments': {'gene': target_symbol, 'species': 'human', 'limit': 10}
})

if isinstance(result, dict) and result.get('status') == 'error':
    print(json.dumps({'error': result.get('error')}))
    raise SystemExit(0)

records = []
if isinstance(result, dict):
    if isinstance(result.get('records'), list):
        records = result.get('records', [])
    elif isinstance(result.get('data'), list):
        records = result.get('data', [])
    elif isinstance(result.get('results'), list):
        records = result.get('results', [])

score = 0.0
if records:
    top = records[0]
    for key in ('score', 'sensitivity_human', 'sensitivity_mouse'):
        value = top.get(key)
        if isinstance(value, (int, float)):
            score = max(0.0, min(1.0, float(value)))
            break
    if not score:
        score = min(1.0, max(0.2, len(records) / 10.0))

print(json.dumps({
    'specificity_score': score,
    'confidence': 0.65 if records else 0.35,
    'rationale': 'Normalized from ToolUniverse PanglaoDB cell-type marker lookup.',
    'backend_source': 'tooluniverse',
    'matched_records': records[:5],
}))
"""
    try:
        completed = subprocess.run(
            [python_bin, "-c", script, request.hypothesis.target.symbol, str(_TOOLUNIVERSE_WORKSPACE)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=_tooluniverse_env(),
        )
    except Exception as exc:
        return BackendResult(
            ok=False,
            error={"type": "backend_unavailable", "message": f"ToolUniverse single-cell execution failed locally: {exc}"},
        )
    return _decode_tooluniverse_subprocess_output(
        completed=completed,
        not_found_message=f"No ToolUniverse PanglaoDB records found for {request.hypothesis.target.symbol}.",
    )


def _run_single_cell(request: EvidenceRequest) -> BackendResult:
    mock = _mock_payload(request, "cellxgene_single_cell_mcp")
    if mock is not None:
        return BackendResult(ok=True, payload=mock)
    python_bin = _tooluniverse_python()
    if python_bin is not None:
        result = _run_single_cell_with_tooluniverse(request=request, python_bin=python_bin)
        if result.ok:
            return result
    return BackendResult(
        ok=False,
        error={
            "type": "backend_unavailable",
            "message": "Single-cell ToolUniverse backend did not produce a usable result.",
        },
    )


def _run_alphafold_with_tooluniverse(*, request: EvidenceRequest, python_bin: str) -> BackendResult:
    uniprot_id = request.hypothesis.context.get("uniprot_id") or request.hypothesis.context.get("uniprot_accession")
    if not uniprot_id:
        return BackendResult(
            ok=False,
            error={
                "type": "hypothesis_invalid",
                "message": "Structure ToolUniverse backend requires context.uniprot_id or context.uniprot_accession.",
            },
        )
    script = """
import json
import sys
from tooluniverse import ToolUniverse

uniprot_id = sys.argv[1]
workspace = sys.argv[2]
tu = ToolUniverse(workspace=workspace, use_global=False)
tu.load_tools(categories=['alphafold'])
result = tu.run_one_function({
    'name': 'alphafold_get_summary',
    'arguments': {'qualifier': uniprot_id}
})

if isinstance(result, dict) and result.get('status') == 'error':
    print(json.dumps({'error': result.get('error')}))
    raise SystemExit(0)

score = 0.5
payload = result if isinstance(result, dict) else {'raw_response': result}
for key in ('mean_plddt', 'plddt', 'confidence_score'):
    value = payload.get(key)
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 1.0:
            numeric = numeric / 100.0
        score = max(0.0, min(1.0, numeric))
        break

print(json.dumps({
    'score': score,
    'confidence': 0.7,
    'rationale': 'Normalized from ToolUniverse AlphaFold summary metadata.',
    'backend_source': 'tooluniverse',
    'model_name': 'alphafold_get_summary',
    'alphafold_summary': payload,
}))
"""
    try:
        completed = subprocess.run(
            [python_bin, "-c", script, uniprot_id, str(_TOOLUNIVERSE_WORKSPACE)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=_tooluniverse_env(),
        )
    except Exception as exc:
        return BackendResult(
            ok=False,
            error={"type": "backend_unavailable", "message": f"ToolUniverse structure execution failed locally: {exc}"},
        )
    return _decode_tooluniverse_subprocess_output(
        completed=completed,
        not_found_message=f"No ToolUniverse AlphaFold summary found for {uniprot_id}.",
    )


def _run_alphafold_structure(request: EvidenceRequest) -> BackendResult:
    mock = _mock_payload(request, "alphafold_tooluniverse_mcp")
    if mock is not None:
        return BackendResult(ok=True, payload=mock)
    python_bin = _tooluniverse_python()
    if python_bin is not None:
        return _run_alphafold_with_tooluniverse(request=request, python_bin=python_bin)
    return BackendResult(
        ok=False,
        error={
            "type": "backend_unavailable",
            "message": "AlphaFold ToolUniverse backend did not produce a usable result.",
        },
    )


def _run_text_knowledge_with_tooluniverse(*, request: EvidenceRequest, python_bin: str) -> BackendResult:
    script = """
import json
import sys
from tooluniverse import ToolUniverse

target_symbol = sys.argv[1]
disease_name = sys.argv[2]
workspace = sys.argv[3]
query = f'"{target_symbol}" AND "{disease_name}"'
tu = ToolUniverse(workspace=workspace, use_global=False)
tu.load_tools(categories=['EuropePMC'])
result = tu.run_one_function({
    'name': 'EuropePMC_search_articles',
    'arguments': {'query': query, 'limit': 5}
})

if isinstance(result, dict) and result.get('status') == 'error':
    print(json.dumps({'error': result.get('error')}))
    raise SystemExit(0)

articles = []
if isinstance(result, dict):
    if isinstance(result.get('articles'), list):
        articles = result['articles']
    elif isinstance(result.get('results'), list):
        articles = result['results']
    elif isinstance(result.get('data'), list):
        articles = result['data']
    else:
        result_list = result.get('resultList', {})
        if isinstance(result_list, dict) and isinstance(result_list.get('result'), list):
            articles = result_list['result']

hit_count = result.get('hitCount') if isinstance(result, dict) else None
if hit_count is None:
    hit_count = len(articles)
score = min(1.0, float(hit_count) / 20.0) if hit_count else 0.0
print(json.dumps({
    'support_score': score,
    'confidence': 0.7 if articles else 0.35,
    'rationale': 'Normalized from ToolUniverse EuropePMC article search hit count.',
    'backend_source': 'tooluniverse',
    'hit_count': hit_count,
    'top_articles': articles[:3],
}))
"""
    completed = subprocess.run(
        [python_bin, "-c", script, request.hypothesis.target.symbol, request.hypothesis.disease.name, str(_TOOLUNIVERSE_WORKSPACE)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=_tooluniverse_env(),
    )
    return _decode_tooluniverse_subprocess_output(
        completed=completed,
        not_found_message="No ToolUniverse EuropePMC articles found for the hypothesis query.",
    )


def _run_knowledge_graph_with_tooluniverse(*, request: EvidenceRequest, python_bin: str) -> BackendResult:
    script = """
import json
import sys
from tooluniverse import ToolUniverse

target_symbol = sys.argv[1]
disease_name = sys.argv[2].lower()
workspace = sys.argv[3]
tu = ToolUniverse(workspace=workspace, use_global=False)
tu.load_tools(categories=['monarch'])
gene_result = tu.run_one_function({
    'name': 'Monarch_search_gene',
    'arguments': {'query': target_symbol, 'limit': 5}
})

if isinstance(gene_result, dict) and gene_result.get('status') == 'error':
    print(json.dumps({'error': gene_result.get('error')}))
    raise SystemExit(0)

records = []
if isinstance(gene_result, dict):
    for key in ('results', 'items'):
        if isinstance(gene_result.get(key), list):
            records = gene_result[key]
            break
    if not records:
        data = gene_result.get('data', {})
        if isinstance(data, dict):
            for key in ('items', 'results'):
                if isinstance(data.get(key), list):
                    records = data[key]
                    break
subject = None
for row in records:
    identifier = row.get('id') or row.get('subject') or row.get('curie')
    if isinstance(identifier, str) and identifier.startswith('HGNC:'):
        subject = identifier
        break

if not subject:
    print(json.dumps({'not_found': True}))
    raise SystemExit(0)

result = tu.run_one_function({
    'name': 'Monarch_get_gene_diseases',
    'arguments': {'subject': subject, 'limit': 25}
})

if isinstance(result, dict) and result.get('status') == 'error':
    print(json.dumps({'error': result.get('error')}))
    raise SystemExit(0)

associations = []
if isinstance(result, dict):
    for key in ('associations', 'items', 'results'):
        if isinstance(result.get(key), list):
            associations = result[key]
            break
    if not associations:
        data = result.get('data', {})
        if isinstance(data, dict):
            for key in ('items', 'associations', 'results'):
                if isinstance(data.get(key), list):
                    associations = data[key]
                    break

matched = []
for row in associations:
    if disease_name in json.dumps(row).lower():
        matched.append(row)

score = 0.0
if matched:
    score = 0.9
elif associations:
    score = min(0.6, len(associations) / 50.0)

print(json.dumps({
    'support_score': score,
    'confidence': 0.75 if associations else 0.4,
    'rationale': 'Normalized from ToolUniverse Monarch gene-to-disease associations.',
    'backend_source': 'tooluniverse',
    'subject_id': subject,
    'matched_associations': matched[:3],
    'association_count': len(associations),
}))
"""
    completed = subprocess.run(
        [python_bin, "-c", script, request.hypothesis.target.symbol, request.hypothesis.disease.name, str(_TOOLUNIVERSE_WORKSPACE)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=_tooluniverse_env(),
    )
    return _decode_tooluniverse_subprocess_output(
        completed=completed,
        not_found_message="No ToolUniverse Monarch association was found for the hypothesis.",
    )


def _run_omics_with_tooluniverse(*, request: EvidenceRequest, python_bin: str) -> BackendResult:
    script = """
import json
import sys
from tooluniverse import ToolUniverse

target_symbol = sys.argv[1]
tissue_type = sys.argv[2]
disease_name = sys.argv[3]
workspace = sys.argv[4]
tu = ToolUniverse(workspace=workspace, use_global=False)
tu.load_tools(categories=['hpa'])
result = tu.run_one_function({
    'name': 'HPA_get_disease_expression_by_gene_tissue_disease',
    'arguments': {
        'gene_name': target_symbol,
        'tissue_type': tissue_type,
        'disease_name': disease_name,
    }
})

if isinstance(result, dict) and result.get('status') == 'error':
    print(json.dumps({'error': result.get('error')}))
    raise SystemExit(0)

payload = result if isinstance(result, dict) else {'raw_response': result}
text_blob = json.dumps(payload).lower()
score = 0.4
for high_keyword in ('high', 'elevated', 'upregulated', 'increased', 'overexpressed'):
    if high_keyword in text_blob:
        score = 0.8
        break
for low_keyword in ('low', 'decreased', 'downregulated', 'not detected'):
    if low_keyword in text_blob:
        score = min(score, 0.3)
        break

print(json.dumps({
    'score': score,
    'confidence': 0.65,
    'rationale': 'Normalized from ToolUniverse Human Protein Atlas disease-vs-normal expression output.',
    'backend_source': 'tooluniverse',
    'tissue_type': tissue_type,
    'disease_name': disease_name,
    'omics_payload': payload,
}))
"""
    completed = subprocess.run(
        [
            python_bin,
            "-c",
            script,
            request.hypothesis.target.symbol,
            _tissue_type(request.hypothesis.disease.name, request.hypothesis.context),
            request.hypothesis.context.get("hpa_disease_name") or _hpa_disease_name(request.hypothesis.disease.name),
            str(_TOOLUNIVERSE_WORKSPACE),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=_tooluniverse_env(),
    )
    return _decode_tooluniverse_subprocess_output(
        completed=completed,
        not_found_message="No ToolUniverse HPA omics evidence was found for the hypothesis.",
    )


def _run_clinical_with_tooluniverse(*, request: EvidenceRequest, python_bin: str) -> BackendResult:
    script = """
import json
import sys
from tooluniverse import ToolUniverse

target_symbol = sys.argv[1]
disease_name = sys.argv[2]
workspace = sys.argv[3]
tu = ToolUniverse(workspace=workspace, use_global=False)
tu.load_tools(categories=['clinical_trials'])
result = tu.run_one_function({
    'name': 'ClinicalTrials_search_studies',
    'arguments': {'query_cond': disease_name, 'query_term': target_symbol, 'page_size': 5}
})

if isinstance(result, dict) and result.get('status') == 'error':
    print(json.dumps({'error': result.get('error')}))
    raise SystemExit(0)

studies = []
if isinstance(result, dict):
    if isinstance(result.get('studies'), list):
        studies = result['studies']
    elif isinstance(result.get('results'), list):
        studies = result['results']
    elif isinstance(result.get('data'), list):
        studies = result['data']
    else:
        data = result.get('data', {})
        if isinstance(data, dict) and isinstance(data.get('studies'), list):
            studies = data['studies']

score = min(1.0, len(studies) / 5.0) if studies else 0.0
print(json.dumps({
    'support_score': score,
    'confidence': 0.7 if studies else 0.35,
    'rationale': 'Normalized from ToolUniverse ClinicalTrials study search.',
    'backend_source': 'tooluniverse',
    'study_count': len(studies),
    'top_studies': studies[:3],
}))
"""
    completed = subprocess.run(
        [python_bin, "-c", script, request.hypothesis.target.symbol, request.hypothesis.disease.name, str(_TOOLUNIVERSE_WORKSPACE)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=_tooluniverse_env(),
    )
    return _decode_tooluniverse_subprocess_output(
        completed=completed,
        not_found_message="No ToolUniverse ClinicalTrials studies were found for the hypothesis.",
    )


def _run_perturbation_model_with_tooluniverse(*, request: EvidenceRequest, python_bin: str) -> BackendResult:
    script = """
import json
import sys
from tooluniverse import ToolUniverse

drug_name = sys.argv[1]
cell_line = sys.argv[2]
workspace = sys.argv[3]
tu = ToolUniverse(workspace=workspace, use_global=False)
tu.load_tools(categories=['lincs'])
result = tu.run_one_function({
    'name': 'LINCS_search_signatures',
    'arguments': {
        'drug_name': drug_name,
        'cell_line': cell_line,
        'limit': 5,
    }
})

if isinstance(result, dict) and result.get('status') == 'error':
    print(json.dumps({'error': result.get('error')}))
    raise SystemExit(0)

payload = result if isinstance(result, dict) else {'raw_response': result}
signatures = []
if isinstance(payload.get('data'), list):
    signatures = payload['data']
metadata = payload.get('metadata', {})
total = metadata.get('total_results', len(signatures))
score = min(1.0, float(total) / 5.0) if total else 0.0

print(json.dumps({
    'score': score,
    'confidence': 0.7 if signatures else 0.35,
    'rationale': 'Normalized from ToolUniverse LINCS signature availability as a perturbation-model proxy.',
    'backend_source': 'tooluniverse',
    'model_name': 'LINCS_search_signatures',
    'matched_signatures': signatures[:3],
    'total_results': total,
}))
"""
    completed = subprocess.run(
        [
            python_bin,
            "-c",
            script,
            request.hypothesis.context.get("perturbagen", "gefitinib"),
            request.hypothesis.context.get("cell_line", "A549"),
            str(_TOOLUNIVERSE_WORKSPACE),
        ],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
        env=_tooluniverse_env(),
    )
    return _decode_tooluniverse_subprocess_output(
        completed=completed,
        not_found_message="No ToolUniverse LINCS perturbation-model proxy evidence was produced for the hypothesis.",
    )


def _run_perturbation_experiment_with_tooluniverse(*, request: EvidenceRequest, python_bin: str) -> BackendResult:
    script = """
import json
import sys
from tooluniverse import ToolUniverse

drug_name = sys.argv[1]
cell_line = sys.argv[2]
workspace = sys.argv[3]
tu = ToolUniverse(workspace=workspace, use_global=False)
tu.load_tools(categories=['lincs'])
result = tu.run_one_function({
    'name': 'LINCS_search_signatures',
    'arguments': {'drug_name': drug_name, 'cell_line': cell_line, 'limit': 10}
})

if isinstance(result, dict) and result.get('status') == 'error':
    print(json.dumps({'error': result.get('error')}))
    raise SystemExit(0)

payload = result if isinstance(result, dict) else {'raw_response': result}
signatures = []
if isinstance(payload.get('data'), list):
    signatures = payload['data']
metadata = payload.get('metadata', {})
total = metadata.get('total_results', len(signatures))
score = min(1.0, float(total) / 10.0) if total else 0.0

print(json.dumps({
    'score': score,
    'confidence': 0.75 if signatures else 0.35,
    'rationale': 'Normalized from ToolUniverse LINCS perturbation signatures.',
    'backend_source': 'tooluniverse',
    'signature_count': total,
    'matched_signatures': signatures[:5],
}))
"""
    completed = subprocess.run(
        [
            python_bin,
            "-c",
            script,
            request.hypothesis.context.get("perturbagen", "gefitinib"),
            request.hypothesis.context.get("cell_line", "A549"),
            str(_TOOLUNIVERSE_WORKSPACE),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=_tooluniverse_env(),
    )
    return _decode_tooluniverse_subprocess_output(
        completed=completed,
        not_found_message="No ToolUniverse LINCS perturbation experiment evidence was found for the hypothesis.",
    )


def _run_retrieval_layer(request: EvidenceRequest, backend_family: str) -> BackendResult:
    mock = _mock_payload(request, backend_family)
    if mock is not None:
        return BackendResult(ok=True, payload=mock)
    python_bin = _tooluniverse_python()
    if python_bin is None:
        return BackendResult(
            ok=False,
            error={
                "type": "backend_unavailable",
                "message": f"{backend_family} requires ToolUniverse 1.3.1 or a mocked payload.",
            },
        )
    runners = {
        "literature_text_mcp": _run_text_knowledge_with_tooluniverse,
        "kg_reasoning_mcp": _run_knowledge_graph_with_tooluniverse,
        "clinical_trials_mcp": _run_clinical_with_tooluniverse,
        "hpa_omics_mcp": _run_omics_with_tooluniverse,
        "lincs_perturbation_model_mcp": _run_perturbation_model_with_tooluniverse,
        "lincs_perturbation_experiment_mcp": _run_perturbation_experiment_with_tooluniverse,
    }
    runner = runners.get(backend_family)
    if runner is None:
        return BackendResult(
            ok=False,
            error={
                "type": "backend_unavailable",
                "message": f"No ToolUniverse adapter is registered for {backend_family}.",
            },
        )
    return runner(request=request, python_bin=python_bin)


def execute_backend(capability: BackendCapability, request: EvidenceRequest) -> BackendResult:
    if capability.status == BackendStatus.STUB:
        return BackendResult(
            ok=False,
            error={
                "type": "backend_unavailable",
                "message": f"{capability.backend_family} is currently a staged placeholder without a live backend.",
            },
        )
    if capability.backend_family == "opentargets_genetics_mcp":
        return _run_genetics(request)
    if capability.backend_family == "cellxgene_single_cell_mcp":
        return _run_single_cell(request)
    if capability.backend_family == "alphafold_tooluniverse_mcp":
        return _run_alphafold_structure(request)
    return _run_retrieval_layer(request, capability.backend_family)


def list_capabilities(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    del arguments
    return {
        "capabilities": {
            layer: [schema_to_dict(item) for item in items]
            for layer, items in capabilities_by_layer().items()
        },
        "cache_dir": str(_OBSERVATION_CACHE_DIR),
        "schema_version": "0.1.0",
    }


def validate_hypothesis(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    request = EvidenceRequest.from_dict(arguments or {})
    candidates = find_capabilities(request.evidence_layer, request.axis_id)
    if not candidates:
        return {
            "is_runnable": False,
            "error": {
                "type": "unsupported_layer_axis",
                "message": "No backend supports the requested evidence_layer/axis_id pair.",
            },
        }
    candidate_backends = []
    runnable = False
    for capability in candidates:
        missing = _missing_fields(request.hypothesis, capability)
        item = {
            "backend_family": capability.backend_family,
            "status": capability.status.value,
            "configured": capability.configured,
            "missing_fields": missing,
            "runnable": not missing and capability.status != BackendStatus.STUB,
        }
        candidate_backends.append(item)
        runnable = runnable or item["runnable"]
    return {
        "is_runnable": runnable,
        "hypothesis_id": request.hypothesis.hypothesis_id,
        "evidence_layer": request.evidence_layer.value,
        "axis_id": request.axis_id.value,
        "candidate_backends": candidate_backends,
        "default_patient_stratum": request.hypothesis.patient_stratum.label,
    }


def preview_observation(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    request = EvidenceRequest.from_dict(arguments or {})
    validation = validate_hypothesis(arguments)
    if "error" in validation:
        return validation
    candidate_backends = []
    for capability in find_capabilities(request.evidence_layer, request.axis_id):
        cache_key = _cache_key(capability.backend_family, request)
        cache_path, _ = _cache_paths(capability.backend_family, cache_key)
        candidate_backends.append(
            {
                "backend_family": capability.backend_family,
                "status": capability.status.value,
                "configured": capability.configured,
                "cache": {
                    "key": cache_key,
                    "hit": cache_path.exists(),
                    "path": str(cache_path),
                },
                "expected_cost_tier": capability.default_cost_tier,
                "expected_output": {
                    "value_scale": "bounded_0_1",
                    "supports_confidence": True,
                    "transport": capability.transport,
                },
            }
        )
    return {
        "hypothesis_id": request.hypothesis.hypothesis_id,
        "evidence_layer": request.evidence_layer.value,
        "axis_id": request.axis_id.value,
        "candidate_backends": candidate_backends,
    }


def run_observation(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    request = EvidenceRequest.from_dict(arguments or {})
    validation = validate_hypothesis(arguments)
    if not validation.get("is_runnable"):
        return {"status": "error", "validation": validation}
    failures = []
    for capability in _candidate_order(request):
        cached = _load_cached_observation(capability, request)
        if cached is not None:
            return {"status": "completed", "observation": cached, "used_cache": True}
        backend_result = execute_backend(capability, request)
        if not backend_result.ok:
            failures.append({"backend_family": capability.backend_family, "error": backend_result.error})
            continue
        observation = schema_to_dict(
            build_observation(
                observation_id=f"obs_{uuid.uuid4().hex}",
                hypothesis_id=request.hypothesis.hypothesis_id,
                evidence_layer=request.evidence_layer,
                axis_id=request.axis_id,
                capability=capability,
                raw_payload=backend_result.payload,
                input_hash=_cache_key(capability.backend_family, request),
                used_cache=False,
                notes=[f"Derived from {capability.backend_family}."],
            )
        )
        _write_cached_observation(observation)
        return {"status": "completed", "observation": observation, "used_cache": False}
    return {
        "status": "error",
        "error": {"type": "no_backend_succeeded", "message": "No backend produced an observation."},
        "failures": failures,
    }


def get_observation(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    observation_id = (arguments or {}).get("observation_id")
    if not observation_id:
        return {
            "status": "error",
            "error": {
                "type": "invalid_request",
                "message": "The 'observation_id' parameter is required.",
            },
        }
    observation = _read_observation_by_id(observation_id)
    if observation is None:
        return {
            "status": "error",
            "error": {
                "type": "not_found",
                "message": f"Observation '{observation_id}' was not found in cache.",
            },
        }
    return {"status": "completed", "observation": observation}


def _tool_description(tool_name: str, description: str) -> dict[str, Any]:
    return {"description": description, "parameter_schema": TOOL_SCHEMAS[tool_name]}


if register_mcp_tool is not None:  # pragma: no cover
    @register_mcp_tool(
        tool_type_name="vbs_list_capabilities",
        config=_tool_description(
            "vbs_list_capabilities",
            "List evidence-layer capabilities for the VBS evidence server.",
        ),
        mcp_config={"server_name": DEFAULT_SERVER_NAME, "port": DEFAULT_SERVER_PORT},
    )
    class VbsListCapabilities:
        def run(self, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
            return list_capabilities(arguments)


    @register_mcp_tool(
        tool_type_name="vbs_validate_hypothesis",
        config=_tool_description(
            "vbs_validate_hypothesis",
            "Validate whether a therapeutic hypothesis can support a requested evidence action.",
        ),
        mcp_config={"server_name": DEFAULT_SERVER_NAME, "port": DEFAULT_SERVER_PORT},
    )
    class VbsValidateHypothesis:
        def run(self, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
            return validate_hypothesis(arguments)


    @register_mcp_tool(
        tool_type_name="vbs_preview_observation",
        config=_tool_description(
            "vbs_preview_observation",
            "Preview candidate backends, cache state, and expected cost for a requested observation.",
        ),
        mcp_config={"server_name": DEFAULT_SERVER_NAME, "port": DEFAULT_SERVER_PORT},
    )
    class VbsPreviewObservation:
        def run(self, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
            return preview_observation(arguments)


    @register_mcp_tool(
        tool_type_name="vbs_run_observation",
        config=_tool_description(
            "vbs_run_observation",
            "Run one normalized evidence acquisition step and return a standard observation.",
        ),
        mcp_config={"server_name": DEFAULT_SERVER_NAME, "port": DEFAULT_SERVER_PORT},
    )
    class VbsRunObservation:
        def run(self, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
            return run_observation(arguments)


    @register_mcp_tool(
        tool_type_name="vbs_get_observation",
        config=_tool_description(
            "vbs_get_observation",
            "Fetch a cached observation by its observation_id.",
        ),
        mcp_config={"server_name": DEFAULT_SERVER_NAME, "port": DEFAULT_SERVER_PORT},
    )
    class VbsGetObservation:
        def run(self, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
            return get_observation(arguments)


def serve(port: int | None = None) -> None:
    if start_mcp_server is None:
        raise RuntimeError(
            "ToolUniverse MCP runtime is unavailable. Install tooluniverse==1.3.1 in a local virtualenv first."
        )
    start_mcp_server(port=port or DEFAULT_SERVER_PORT)


def build_hypothesis(
    *,
    gene: str,
    disease: str | None = None,
    disease_efo_id: str | None = None,
    ensembl_id: str | None = None,
    uniprot_id: str | None = None,
    modality: str = "small_molecule",
    mechanism: str = "inhibit",
    direction: str = "inhibit",
    perturbagen: str | None = None,
    cell_line: str | None = None,
    tissue_type: str | None = None,
    hpa_disease_name: str | None = None,
    context: dict[str, Any] | None = None,
    hypothesis_id: str | None = None,
) -> dict[str, Any]:
    symbol = gene.upper()
    preset = TARGET_PRESETS.get(symbol, {})
    hypothesis_context = dict(context or {})
    for key, value in (
        ("uniprot_id", uniprot_id or preset.get("uniprot_id")),
        ("perturbagen", perturbagen or preset.get("perturbagen")),
        ("cell_line", cell_line or preset.get("cell_line")),
        ("tissue_type", tissue_type or preset.get("tissue_type")),
        ("hpa_disease_name", hpa_disease_name or preset.get("hpa_disease_name")),
    ):
        if value:
            hypothesis_context[key] = value
    if preset.get("demo_run_id"):
        hypothesis_context.setdefault("demo_run_id", preset["demo_run_id"])
    stable_disease = disease or preset.get("disease_name", "unknown_disease")
    stable_slug = stable_disease.lower().replace(" ", "_").replace("-", "_")
    return {
        "hypothesis_id": hypothesis_id or preset.get("hypothesis_id") or f"hyp_{symbol.lower()}_{stable_slug}",
        "target": {"symbol": symbol, "ensembl_id": ensembl_id or preset.get("ensembl_id")},
        "disease": {
            "name": disease or preset.get("disease_name", ""),
            "efo_id": disease_efo_id or preset.get("disease_efo_id"),
        },
        "modality": modality,
        "mechanism": mechanism,
        "direction": direction,
        "context": hypothesis_context,
    }


def _slugify(value: str) -> str:
    return (
        value.strip().lower().replace(" ", "_").replace("-", "_").replace("/", "_")
        or "unknown"
    )


def build_eval_hypothesis(
    *,
    candidate: dict[str, Any],
    dataset_meta: dict[str, Any],
    modality: str = "small_molecule",
    mechanism: str = "inhibit",
    direction: str = "inhibit",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    disease_name = str(dataset_meta.get("disease_name", "") or "")
    disease_efo_id = dataset_meta.get("efo_id")
    symbol = str(candidate.get("symbol", "") or "").upper()
    hypothesis_id = f"hyp_{_slugify(disease_name)}_{symbol.lower() or 'unknown'}"
    return build_hypothesis(
        gene=symbol,
        disease=disease_name,
        disease_efo_id=str(disease_efo_id) if disease_efo_id else None,
        ensembl_id=candidate.get("ensembl_id"),
        modality=modality,
        mechanism=mechanism,
        direction=direction,
        context=context,
        hypothesis_id=hypothesis_id,
    )


def run_gene_evidence_chain(
    *,
    gene: str,
    disease: str | None = None,
    disease_efo_id: str | None = None,
    ensembl_id: str | None = None,
    uniprot_id: str | None = None,
    modality: str = "small_molecule",
    mechanism: str = "inhibit",
    direction: str = "inhibit",
    perturbagen: str | None = None,
    cell_line: str | None = None,
    tissue_type: str | None = None,
    hpa_disease_name: str | None = None,
    context: dict[str, Any] | None = None,
    hypothesis_id: str | None = None,
    layer_plan: list[tuple[str, str]] | None = None,
    structure_backend: str | None = None,
) -> dict[str, Any]:
    del structure_backend
    hypothesis = build_hypothesis(
        gene=gene,
        disease=disease,
        disease_efo_id=disease_efo_id,
        ensembl_id=ensembl_id,
        uniprot_id=uniprot_id,
        modality=modality,
        mechanism=mechanism,
        direction=direction,
        perturbagen=perturbagen,
        cell_line=cell_line,
        tissue_type=tissue_type,
        hpa_disease_name=hpa_disease_name,
        context=context,
        hypothesis_id=hypothesis_id,
    )
    observations: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    previews: list[dict[str, Any]] = []
    stages: list[dict[str, Any]] = []
    requested_plan = layer_plan or DEFAULT_LAYER_PLAN
    stage_plan = DEFAULT_STAGE_PLAN if requested_plan == DEFAULT_LAYER_PLAN else [
        {
            "stage_id": f"stage_{index + 1}",
            "title": evidence_layer,
            "items": [(evidence_layer, axis_id)],
        }
        for index, (evidence_layer, axis_id) in enumerate(requested_plan)
    ]

    for stage in stage_plan:
        stage_observations: list[dict[str, Any]] = []
        stage_failures: list[dict[str, Any]] = []
        stage_previews: list[dict[str, Any]] = []
        for evidence_layer, axis_id in stage["items"]:
            request = {
                "hypothesis": hypothesis,
                "evidence_layer": evidence_layer,
                "axis_id": axis_id,
            }
            preview = preview_observation(request)
            result = run_observation(request)
            previews.append(preview)
            stage_previews.append(preview)
            if result.get("status") == "completed":
                observations.append(result["observation"])
                stage_observations.append(result["observation"])
                continue
            failure = {
                "evidence_layer": evidence_layer,
                "axis_id": axis_id,
                "error": result.get("error"),
                "failures": result.get("failures", []),
            }
            failures.append(failure)
            stage_failures.append(failure)

        stages.append(
            {
                "stage_id": stage["stage_id"],
                "title": stage["title"],
                "input": {
                    "target": hypothesis["target"],
                    "disease": hypothesis["disease"],
                },
                "observations": stage_observations,
                "failures": stage_failures,
                "previews": stage_previews,
            }
        )
    axis_summaries = synthesize_axes(observations=observations, failures=failures)
    return {
        "input": {
            "target": hypothesis["target"],
            "disease": hypothesis["disease"],
        },
        "query": {
            "gene": gene.upper(),
            "disease": hypothesis["disease"]["name"],
            "disease_efo_id": hypothesis["disease"]["efo_id"],
        },
        "hypothesis": hypothesis,
        "stages": stages,
        "axes": axis_summaries,
        "observations": observations,
        "failures": failures,
        "previews": previews,
        "summary": {
            "requested_layers": len(requested_plan),
            "requested_stages": len(stage_plan),
            "scored_axes": sum(1 for item in axis_summaries.values() if item["score"] is not None),
            "completed_layers": len(observations),
            "failed_layers": len(failures),
        },
    }


def build_fixture_hypothesis(
    *,
    candidate: dict[str, Any],
    chain_result: dict[str, Any],
) -> dict[str, Any]:
    hypothesis = dict(chain_result["hypothesis"])
    hypothesis["ot_score"] = candidate.get("ot_score")
    hypothesis["axes"] = chain_result["axes"]
    hypothesis["observations"] = chain_result["observations"]
    hypothesis["failures"] = chain_result["failures"]
    hypothesis["summary"] = chain_result["summary"]
    return {
        **hypothesis,
        "target": {
            **hypothesis["target"],
            "symbol": candidate.get("symbol") or hypothesis["target"].get("symbol"),
            "ensembl_id": candidate.get("ensembl_id") or hypothesis["target"].get("ensembl_id"),
        },
    }


def run_eval_hypotheses(
    *,
    candidates_payload: dict[str, Any],
    source_candidates_file: str | None = None,
    modality: str = "small_molecule",
    mechanism: str = "inhibit",
    direction: str = "inhibit",
    layer_plan: list[tuple[str, str]] | None = None,
    structure_backend: str | None = None,
) -> dict[str, Any]:
    dataset_meta = dict(candidates_payload.get("meta", {}))
    candidates = list(candidates_payload.get("candidates", []))
    hypotheses: list[dict[str, Any]] = []

    for candidate in candidates:
        candidate = dict(candidate)
        symbol = str(candidate.get("symbol", "") or "").upper()
        chain_result: dict[str, Any]
        try:
            chain_result = run_gene_evidence_chain(
                gene=symbol,
                disease=str(dataset_meta.get("disease_name", "") or "") or None,
                disease_efo_id=str(dataset_meta.get("efo_id", "") or "") or None,
                ensembl_id=candidate.get("ensembl_id"),
                modality=modality,
                mechanism=mechanism,
                direction=direction,
                hypothesis_id=f"hyp_{_slugify(str(dataset_meta.get('disease_name', '') or 'unknown_disease'))}_{symbol.lower() or 'unknown'}",
                layer_plan=layer_plan,
                structure_backend=structure_backend,
            )
        except Exception as exc:
            chain_result = {
                "hypothesis": build_eval_hypothesis(
                    candidate=candidate,
                    dataset_meta=dataset_meta,
                    modality=modality,
                    mechanism=mechanism,
                    direction=direction,
                ),
                "axes": synthesize_axes(observations=[], failures=[]),
                "observations": [],
                "failures": [
                    {
                        "evidence_layer": None,
                        "axis_id": None,
                        "error": {
                            "type": "candidate_processing_failed",
                            "message": str(exc),
                        },
                        "failures": [],
                    }
                ],
                "summary": {
                    "requested_layers": len(layer_plan or DEFAULT_LAYER_PLAN),
                    "requested_stages": len(DEFAULT_STAGE_PLAN if not layer_plan else layer_plan),
                    "scored_axes": 0,
                    "completed_layers": 0,
                    "failed_layers": 1,
                },
            }
        hypotheses.append(build_fixture_hypothesis(candidate=candidate, chain_result=chain_result))

    return {
        "fixture": {
            "disease": {
                "name": dataset_meta.get("disease_name"),
                "efo_id": dataset_meta.get("efo_id"),
            },
            "schema_version": "0.1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_candidates_file": source_candidates_file,
        },
        "hypotheses": hypotheses,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a multi-layer evidence chain for one gene or a batch of arena-style hypotheses.",
    )
    parser.add_argument("--gene", help="Gene symbol, for example EGFR.")
    parser.add_argument(
        "--candidates-json",
        help="Path to an eval candidates JSON snapshot such as eval/data/melanoma.candidates.json.",
    )
    parser.add_argument("--disease", help="Disease name. Optional if the gene has a built-in preset.")
    parser.add_argument("--disease-efo-id", help="Disease ontology id, for example MONDO_0005061.")
    parser.add_argument("--ensembl-id", help="Optional Ensembl gene id.")
    parser.add_argument("--uniprot-id", help="Optional UniProt accession for structure evidence.")
    parser.add_argument("--modality", default="small_molecule")
    parser.add_argument("--mechanism", default="inhibit")
    parser.add_argument("--direction", default="inhibit")
    parser.add_argument("--perturbagen", help="Optional perturbagen name for LINCS-backed layers.")
    parser.add_argument("--cell-line", help="Optional cell line for LINCS-backed layers.")
    parser.add_argument("--tissue-type", help="Optional tissue override for HPA-backed omics.")
    parser.add_argument("--hpa-disease-name", help="Optional HPA disease code such as lung_cancer.")
    parser.add_argument("--output", help="Optional path to write the full JSON result.")
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print only the observations list instead of the full envelope.",
    )
    parser.add_argument(
        "--layers",
        help="Optional comma-separated evidence layers to run, for example genetics,omics,clinical.",
    )
    parser.add_argument(
        "--structure-backend",
        choices=["alphafold"],
        help="Optional structure backend preference for the structure_pharmacology layer.",
    )
    return parser


def _layer_plan_from_cli(value: str | None) -> list[tuple[str, str]] | None:
    if not value:
        return None
    axis_by_layer = dict(DEFAULT_LAYER_PLAN)
    plan = []
    for layer in [item.strip() for item in value.split(",") if item.strip()]:
        if layer not in axis_by_layer:
            raise SystemExit(f"Unknown layer '{layer}'. Valid layers: {', '.join(axis_by_layer)}")
        plan.append((layer, axis_by_layer[layer]))
    return plan


def main() -> None:
    args = build_parser().parse_args()
    layer_plan = _layer_plan_from_cli(args.layers)
    if bool(args.gene) == bool(args.candidates_json):
        raise SystemExit("Provide exactly one of --gene or --candidates-json.")
    if args.candidates_json:
        candidates_path = Path(args.candidates_json)
        candidates_payload = json.loads(candidates_path.read_text(encoding="utf-8"))
        result = run_eval_hypotheses(
            candidates_payload=candidates_payload,
            source_candidates_file=str(candidates_path),
            modality=args.modality,
            mechanism=args.mechanism,
            direction=args.direction,
            layer_plan=layer_plan,
            structure_backend=args.structure_backend,
        )
        output_path = args.output
        if not output_path:
            input_name = candidates_path.name
            if input_name.endswith(".candidates.json"):
                output_path = str(candidates_path.with_name(input_name.replace(".candidates.json", ".hypotheses.json")))
            else:
                output_path = str(candidates_path.with_suffix(".hypotheses.json"))
        if output_path:
            Path(output_path).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return
    result = run_gene_evidence_chain(
        gene=args.gene,
        disease=args.disease,
        disease_efo_id=args.disease_efo_id,
        ensembl_id=args.ensembl_id,
        uniprot_id=args.uniprot_id,
        modality=args.modality,
        mechanism=args.mechanism,
        direction=args.direction,
        perturbagen=args.perturbagen,
        cell_line=args.cell_line,
        tissue_type=args.tissue_type,
        hpa_disease_name=args.hpa_disease_name,
        layer_plan=layer_plan,
        structure_backend=args.structure_backend,
    )
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result["observations"] if args.compact else result, indent=2))


if __name__ == "__main__":
    main()
