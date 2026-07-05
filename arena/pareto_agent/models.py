"""Typed contracts for the comparison-based Pareto agent.

Every LLM-facing judgement is qualitative (a relation + confidence + rationale),
never a numeric score. These models are the schema the LLM calls are validated
against, and the schema the final run output is built from.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field

AxisName = Literal[
    "right_target",
    "right_tissue",
    "right_safety",
    "right_patient",
    "right_commercial",
    "tractability",
]

AXIS_NAMES: List[AxisName] = [
    "right_target",
    "right_tissue",
    "right_safety",
    "right_patient",
    "right_commercial",
    "tractability",
]

AxisRelation = Literal[
    "A_better",
    "B_better",
    "tie",
    "incomparable",
    "insufficient_evidence",
]

Confidence = Literal["high", "medium", "low"]

OverallRelation = Literal[
    "A_dominates_B",
    "B_dominates_A",
    "tradeoff_or_unresolved",
]

RedFlagSeverity = Literal["minor", "major", "critical"]

RedFlagCategory = Literal[
    "safety",
    "biology",
    "tissue",
    "patient",
    "commercial",
    "tractability",
    "schema",
    "evidence_quality",
]


class RedFlag(BaseModel):
    severity: RedFlagSeverity
    category: RedFlagCategory
    reason: str


class RedFlagResult(BaseModel):
    hypothesis_id: str
    decision: Literal["keep", "remove"]
    red_flags: List[RedFlag] = Field(default_factory=list)
    rationale: str = ""


class AxisComparison(BaseModel):
    axis: AxisName
    relation: AxisRelation
    confidence: Confidence
    rationale: str
    decisive_evidence: List[str] = Field(default_factory=list)
    missing_evidence: List[str] = Field(default_factory=list)


class PairwiseComparison(BaseModel):
    hypothesis_A_id: str
    hypothesis_B_id: str
    overall_relation: OverallRelation
    comparison_summary: Dict[str, Any]
    axis_comparisons: Dict[AxisName, AxisComparison]


class ParetoResult(BaseModel):
    run_metadata: Dict[str, Any]
    red_flagged_hypotheses: List[RedFlagResult]
    pareto_front: List[Dict[str, Any]]
    domination_graph: Dict[str, Any]
