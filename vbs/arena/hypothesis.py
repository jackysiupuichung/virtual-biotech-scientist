"""hypothesis.py — the therapeutic hypothesis, the unit that competes in the arena.

The "player" is NOT a bare gene (ARENA.md §1). It is a fully-framed hypothesis:

    target × disease × modality × mechanism/direction × patient stratum
    e.g. "B7-H3, antagonised via an ADC, in LUAD, exploiting stromal
          overexpression, with a selection biomarker for high-antigen patients."

The dataclass is implemented (it is the stable unit every layer references). The
*generation* of a competing set (5–15 per disease) is scaffolded: framing an
initial slate is an LLM/CSO job and a place the pipeline plugs into ToolUniverse
candidate pulls (tools/opentargets.py already produces disease-associated targets).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Modality(str, Enum):
    SMALL_MOLECULE = "small_molecule"
    ANTIBODY = "antibody"
    ADC = "adc"                 # antibody-drug conjugate
    BISPECIFIC = "bispecific"
    CAR_T = "car_t"
    PROTAC = "protac"           # degrader
    OTHER = "other"


class Direction(str, Enum):
    """Mechanism/direction — how the hypothesis proposes to act on the target."""

    ANTAGONISE = "antagonise"
    AGONISE = "agonise"
    DEGRADE = "degrade"
    BLOCK = "block"


@dataclass
class Hypothesis:
    """A framed (target × disease × modality × mechanism × stratum) candidate."""

    hypothesis_id: str
    target: str                 # gene symbol, e.g. "B7-H3" (CD276)
    disease: str                # disease name / EFO label, e.g. "LUAD"
    modality: Modality
    direction: Direction = Direction.ANTAGONISE
    patient_stratum: str = "all-comers"  # e.g. "antigen-high", "stromal-high"
    biomarker: str = ""         # selection biomarker, if any
    parent_id: str | None = None  # set when produced by mutating another (see mutate.py)
    notes: str = ""

    def label(self) -> str:
        """The compact human string shown on the card and leaderboard."""
        bits = [self.target, self.modality.value, self.disease]
        if self.patient_stratum and self.patient_stratum != "all-comers":
            bits.append(self.patient_stratum)
        return " · ".join(bits)

    def to_record(self) -> dict:
        return {
            "hypothesis_id": self.hypothesis_id,
            "target": self.target,
            "disease": self.disease,
            "modality": self.modality.value,
            "direction": self.direction.value,
            "patient_stratum": self.patient_stratum,
            "biomarker": self.biomarker,
            "parent_id": self.parent_id,
        }


@dataclass
class HypothesisSlate:
    """The competing set for one disease question (5–15 hypotheses, ARENA.md §1)."""

    disease: str
    hypotheses: list[Hypothesis] = field(default_factory=list)

    def add(self, h: Hypothesis) -> "HypothesisSlate":
        self.hypotheses.append(h)
        return self

    def ids(self) -> list[str]:
        return [h.hypothesis_id for h in self.hypotheses]


# --------------------------------------------------------------------------- #
# Generation — SCAFFOLD. Fill with CSO/LLM framing + ToolUniverse candidate pull.
# --------------------------------------------------------------------------- #

def frame_slate(disease: str, targets: list[str], *, runner=None) -> HypothesisSlate:
    """Turn a disease + a candidate target pool into a competing hypothesis slate.

    TODO(B2): for each candidate target, have the CSO/LLM (``runner`` from
    vbs.runners) propose the most plausible (modality × mechanism × stratum) — the
    paper *outputs* these (B7-H3→ADC, OSMRβ→mAb). Seed the pool from
    ``tools.opentargets.candidates(efo)`` and cap at 5–15 by OT association score.

    For now: a deterministic one-hypothesis-per-target slate so downstream code
    (cards, pareto, tournament) has real objects to run against in the demo.
    """
    slate = HypothesisSlate(disease=disease)
    for i, tgt in enumerate(targets):
        slate.add(Hypothesis(
            hypothesis_id=f"H{i:02d}",
            target=tgt,
            disease=disease,
            modality=Modality.ANTIBODY,  # TODO: LLM-chosen per target
        ))
    return slate
