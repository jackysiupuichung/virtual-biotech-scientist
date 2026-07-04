"""card.py — the hypothesis card and the per-axis evidence record.

THE KEYSTONE (DESIGN.md §3.2). The arena and the VoI loop only compose if every
evidence source — a cheap Open Targets lookup *and* an expensive Boltz-2 run —
returns the SAME record shape so they are comparable on one yardstick.

The card contract follows **jcaky's fixture schema** (virtual-biotech-scientist
PR #1, ``arena/fixtures/melanoma.hypotheses.json``), agreed as the single source
of truth so the fixture and the arena code never drift. Concretely:
  * axis keys      — ``right_target`` / ``right_tissue`` / … / ``tractability``
  * cost tiers     — ordinal ``1`` (lookup) · ``2`` (synthesis) · ``3`` (run_experiment)
  * axis entry     — ``{value, confidence, cost, direction, strength, data_origin,
                        finding, interpretation, source}``

A ``HypothesisCard`` collects one ``Evidence`` per axis for a single framed
therapeutic hypothesis. The arena ranks cards (Pareto + tournament); the VoI
loop decides which axis to resolve next by comparing each candidate action's
expected information against its ``cost`` tier. Everything downstream
(pareto.py, tournament.py, voi/selector.py, fixture_loader.py) depends on these
types, so they are locked first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Axis(str, Enum):
    """The scoring objectives — AZ 5R plus cross-cutting Tractability (DESIGN §3.1).

    Member ``.value`` strings are jcaky's fixture axis keys, so ``Axis("right_target")``
    and JSON round-trips work directly. Member *names* (``Axis.TARGET``) stay short
    for internal use.
    """

    TARGET = "right_target"        # Right Target — does modulating it cause the effect?
    TISSUE = "right_tissue"        # Right Tissue — is it where the disease is, not elsewhere?
    SAFETY = "right_safety"        # Right Safety — will hitting it harm normal biology?
    PATIENT = "right_patient"      # Right Patient — is there a stratum + biomarker?
    COMMERCIAL = "right_commercial"  # Right Commercial — crowded or whitespace?
    TRACTABILITY = "tractability"  # cross-cutting, modality-gated — can it be drugged?

    @classmethod
    def ranking_axes(cls) -> list["Axis"]:
        """The axes that participate in Pareto/tournament ranking.

        All six by default; a build may drop COMMERCIAL to a light view. Kept as a
        single source of truth so pareto.py and tournament.py never re-list axes.
        """
        return list(cls)


class CostTier(int, Enum):
    """Discrete cost of producing one Evidence record — jcaky's ordinal 1/2/3 tiers.

    Cost is a discrete tier, not seconds or dollars — VoI's argmax(netEVPI) needs
    only the ordinal gap between a lookup and a run_experiment. (Our earlier draft
    used 1/10/100; we adopt jcaky's 1/2/3 as the shared fixture convention.)
    """

    LOOKUP = 1      # single API/DB call, sub-second, ~free (OT, TCGA, openFDA, trials)
    SYNTHESIS = 2   # multi-call / LLM synthesis / data download (lit-synth, cellxgene-fetch)
    EXPERIMENT = 3  # real computation on real data via run_experiment (tau, Boltz-2)


@dataclass
class Evidence:
    """One axis's worth of evidence for one hypothesis — the universal skill output.

    Shape follows jcaky's fixture axis-entry (the keystone). EVERY skill (lookup or
    experiment) returns this. ``value`` and ``confidence`` are normalised to [0, 1]
    so axes are commensurable and ``value`` is higher=better on every axis (what
    Pareto/judges compare on); ``cost`` is the discrete tier; ``data_origin`` is the
    honesty flag (``opentargets`` real · ``hybrid`` · ``synthetic`` designed prior);
    ``finding``/``interpretation`` are the prose the LLM judge panel argues over.
    """

    axis: Axis
    value: float             # normalised [0,1], higher = better on this axis
    confidence: float        # 0 (guess) .. 1 (certain) — drives VoI's remaining uncertainty
    cost: CostTier           # tier of the skill that produced this (1/2/3)
    direction: str = "neutral"   # supports | refutes | neutral
    strength: str = ""       # strong | moderate | weak (qualitative)
    data_origin: str = ""    # opentargets | hybrid | synthetic — read before trusting value
    finding: str = ""        # prose the judge panel can argue over
    interpretation: str = ""  # what it means for the go/no-go
    source: dict[str, Any] = field(default_factory=dict)  # {db, fields, synthetic_parts}

    def __post_init__(self) -> None:
        self.axis = Axis(self.axis)
        self.cost = CostTier(self.cost)
        self.value = _clamp01(self.value)
        self.confidence = _clamp01(self.confidence)

    @classmethod
    def from_entry(cls, axis: Axis | str, entry: dict[str, Any]) -> "Evidence":
        """Build from a fixture axis-entry dict (jcaky's schema)."""
        return cls(
            axis=Axis(axis),
            value=entry.get("value", 0.0),
            confidence=entry.get("confidence", 0.0),
            cost=CostTier(int(entry.get("cost", 1))),
            direction=entry.get("direction", "neutral"),
            strength=entry.get("strength", ""),
            data_origin=entry.get("data_origin", ""),
            finding=entry.get("finding", ""),
            interpretation=entry.get("interpretation", ""),
            source=entry.get("source") or {},
        )

    def to_record(self) -> dict[str, Any]:
        """Serialise back to jcaky's axis-entry shape (round-trips with the fixture)."""
        return {
            "value": round(self.value, 4),
            "confidence": round(self.confidence, 4),
            "cost": int(self.cost),
            "direction": self.direction,
            "strength": self.strength,
            "data_origin": self.data_origin,
            "finding": self.finding,
            "interpretation": self.interpretation,
            "source": self.source or None,
        }


@dataclass
class HypothesisCard:
    """A framed therapeutic hypothesis + its per-axis evidence — the arena "player".

    ``hypothesis_id`` links back to the ``Hypothesis`` in arena/hypothesis.py.
    Axes with no evidence yet are simply absent from ``axes`` — the VoI loop reads
    that absence as maximum uncertainty and a candidate action.
    """

    hypothesis_id: str
    label: str  # human string, e.g. "B7-H3 · ADC · LUAD · stromal-high"
    axes: dict[Axis, Evidence] = field(default_factory=dict)

    def put(self, ev: Evidence) -> "HypothesisCard":
        """Attach/overwrite the evidence for one axis (a re-run replaces the old)."""
        self.axes[ev.axis] = ev
        return self

    def get(self, axis: Axis) -> Evidence | None:
        return self.axes.get(Axis(axis))

    def value_vector(self, axes: list[Axis] | None = None) -> list[float]:
        """Per-axis value in a fixed axis order (missing axis → 0.0).

        This is the point compared by Pareto dominance and scalarisation. Missing
        evidence scores 0 so an un-investigated card cannot dominate an investigated
        one on an axis it never measured.
        """
        order = axes or Axis.ranking_axes()
        return [self.axes[a].value if a in self.axes else 0.0 for a in order]

    def missing_axes(self, axes: list[Axis] | None = None) -> list[Axis]:
        order = axes or Axis.ranking_axes()
        return [a for a in order if a not in self.axes]

    def total_cost_spent(self) -> int:
        return sum(int(ev.cost) for ev in self.axes.values())

    def to_record(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "label": self.label,
            "axes": {a.value: self.axes[a].to_record() for a in self.axes},
            "cost_spent": self.total_cost_spent(),
        }


def _clamp01(x: float) -> float:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if x < 0 else 1.0 if x > 1 else x
