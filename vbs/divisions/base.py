"""base.py — the scientist-division base: an evidence producer (DESIGN.md §2.1).

Divisions are *evidence producers*, not the axes themselves — each answers a
sub-question using ToolUniverse tools and emits ``Evidence`` records that populate
a hypothesis card's axes. The paper's org structure (Zhang 2026): Target ID,
Target Safety, Modality, Disease-biology/literature, Clinical. A hackathon build
runs a subset (Target ID + Safety + Modality + Clinical is plenty, DESIGN §2.1).

SCAFFOLD: the ``Division`` protocol + a registry of the concrete divisions and the
axes each is responsible for. Each division's ``investigate`` (call ToolUniverse,
adapt to Evidence) is the TODO — the tool calls go through vbs/tooluniverse and
the adapter, the frontier-model experiments through vbs/experiments.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..arena.card import Axis, HypothesisCard
from ..arena.hypothesis import Hypothesis


class Division(Protocol):
    name: str
    axes: list[Axis]  # which card axes this division populates

    def investigate(self, hypothesis: Hypothesis, card: HypothesisCard) -> HypothesisCard: ...


@dataclass
class DivisionSpec:
    """Static description of a division: its name, axes, and default tool set."""

    name: str
    axes: list[Axis]
    tools: list[str] = field(default_factory=list)  # ToolUniverse tool ids it calls


# The subset org (DESIGN §2.1). Extend to the full five if budget allows.
DIVISIONS: list[DivisionSpec] = [
    DivisionSpec("target_id", [Axis.TARGET, Axis.TISSUE],
                 ["OpenTargets_get_associated_diseases"]),
    DivisionSpec("target_safety", [Axis.SAFETY],
                 ["OpenTargets_get_target_factors", "OpenFDA_get_adverse_events"]),
    DivisionSpec("modality", [Axis.TRACTABILITY],
                 ["Boltz2_predict_binding_affinity"]),
    DivisionSpec("clinical", [Axis.PATIENT, Axis.COMMERCIAL],
                 ["ClinicalTrials_search"]),
]


def division_for_axis(axis: Axis) -> DivisionSpec | None:
    axis = Axis(axis)
    return next((d for d in DIVISIONS if axis in d.axes), None)
