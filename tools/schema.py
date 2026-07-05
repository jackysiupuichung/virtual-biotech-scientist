"""Core schemas for the evidence MCP server."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EvidenceLayer(str, Enum):
    TEXT_KNOWLEDGE = "text_knowledge"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    GENETICS = "genetics"
    OMICS = "omics"
    SINGLE_CELL = "single_cell"
    SPATIAL_OMICS = "spatial_omics"
    PERTURBATION_MODEL = "perturbation_model"
    PERTURBATION_EXPERIMENT = "perturbation_experiment"
    STRUCTURE_PHARMACOLOGY = "structure_pharmacology"
    CLINICAL = "clinical"


class AxisId(str, Enum):
    RIGHT_TARGET = "right_target"
    RIGHT_TISSUE = "right_tissue"
    RIGHT_SAFETY = "right_safety"
    RIGHT_PATIENT = "right_patient"
    RIGHT_COMMERCIAL = "right_commercial"
    TRACTABILITY = "tractability"


class BackendStatus(str, Enum):
    LIVE = "live"
    RETRIEVAL_BACKED = "retrieval_backed"
    STUB = "stub"


@dataclass
class TargetRef:
    symbol: str
    ensembl_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TargetRef":
        return cls(symbol=data.get("symbol", ""), ensembl_id=data.get("ensembl_id"))


@dataclass
class DiseaseRef:
    name: str
    efo_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DiseaseRef":
        return cls(name=data.get("name", ""), efo_id=data.get("efo_id"))


@dataclass
class PatientStratum:
    label: str = "all_comers"
    biomarkers: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PatientStratum":
        if not data:
            return cls()
        return cls(
            label=data.get("label", "all_comers"),
            biomarkers=list(data.get("biomarkers", [])),
        )


@dataclass
class HypothesisAssets:
    ligands: list[dict[str, Any]] = field(default_factory=list)
    antibodies: list[dict[str, Any]] = field(default_factory=list)
    structures: list[dict[str, Any]] = field(default_factory=list)
    datasets: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "HypothesisAssets":
        if not data:
            return cls()
        return cls(
            ligands=list(data.get("ligands", [])),
            antibodies=list(data.get("antibodies", [])),
            structures=list(data.get("structures", [])),
            datasets=list(data.get("datasets", [])),
        )


@dataclass
class TherapeuticHypothesis:
    hypothesis_id: str
    target: TargetRef
    disease: DiseaseRef
    modality: str
    mechanism: str
    direction: str
    patient_stratum: PatientStratum = field(default_factory=PatientStratum)
    assets: HypothesisAssets = field(default_factory=HypothesisAssets)
    context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TherapeuticHypothesis":
        return cls(
            hypothesis_id=data.get("hypothesis_id", ""),
            target=TargetRef.from_dict(data.get("target", {})),
            disease=DiseaseRef.from_dict(data.get("disease", {})),
            modality=data.get("modality", ""),
            mechanism=data.get("mechanism", ""),
            direction=data.get("direction", ""),
            patient_stratum=PatientStratum.from_dict(data.get("patient_stratum")),
            assets=HypothesisAssets.from_dict(data.get("assets")),
            context=dict(data.get("context", {})),
        )


@dataclass
class EvidenceRequest:
    hypothesis: TherapeuticHypothesis
    evidence_layer: EvidenceLayer
    axis_id: AxisId
    objective: str | None = None
    backend_preference: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceRequest":
        return cls(
            hypothesis=TherapeuticHypothesis.from_dict(data.get("hypothesis", {})),
            evidence_layer=EvidenceLayer(data.get("evidence_layer")),
            axis_id=AxisId(data.get("axis_id")),
            objective=data.get("objective"),
            backend_preference=list(data.get("backend_preference", [])),
        )


@dataclass
class ValueScale:
    type: str = "bounded"
    min: float = 0.0
    max: float = 1.0
    higher_is_better: bool = True


@dataclass
class CostInfo:
    tier: int
    expected_runtime_sec: int | None = None
    used_cache: bool = False


@dataclass
class BackendInfo:
    family: str
    status: BackendStatus
    transport: str
    model_name: str | None = None


@dataclass
class ProvenanceInfo:
    input_hash: str
    created_at: str
    raw_payload: dict[str, Any] = field(default_factory=dict)
    raw_artifact_path: str | None = None
    notes: list[str] = field(default_factory=list)

    @classmethod
    def now(
        cls,
        *,
        input_hash: str,
        raw_payload: dict[str, Any] | None = None,
        raw_artifact_path: str | None = None,
        notes: list[str] | None = None,
    ) -> "ProvenanceInfo":
        return cls(
            input_hash=input_hash,
            created_at=datetime.now(timezone.utc).isoformat(),
            raw_payload=raw_payload or {},
            raw_artifact_path=raw_artifact_path,
            notes=notes or [],
        )


@dataclass
class Observation:
    observation_id: str
    hypothesis_id: str
    evidence_layer: EvidenceLayer
    axis_id: AxisId
    value: float
    value_scale: ValueScale
    confidence: float
    cost: CostInfo
    backend: BackendInfo
    provenance: ProvenanceInfo
    status: str
    rationale: str | None = None


@dataclass
class BackendCapability:
    backend_family: str
    evidence_layer: EvidenceLayer
    status: BackendStatus
    axes: list[AxisId]
    required_hypothesis_fields: list[str]
    default_cost_tier: int
    transport: str
    description: str
    supports_cache: bool = True
    configured: bool = False


def schema_to_dict(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            item.name: schema_to_dict(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, dict):
        return {key: schema_to_dict(item) for key, item in value.items()}
    if isinstance(value, list):
        return [schema_to_dict(item) for item in value]
    return value
