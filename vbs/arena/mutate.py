"""mutate.py — self-improving hypotheses: evolve the losers (SELF_IMPROVING.md Level B).

Don't pick from a fixed menu — invent better menu items by learning from what
lost. A hypothesis that loses its arena matches is not discarded; it is *mutated*
and re-entered, so the population of ideas improves over rounds, not just the
ranking of a fixed set. Cross-domain precedent: quality-diversity / evolutionary
search (MAP-Elites, FunSearch, AlphaEvolve).

The three mutation operators (SELF_IMPROVING.md Level B):
  * swap **modality**   (ADC → bispecific → CAR-T)
  * narrow **patient stratum** (all-comers → antigen-high)
  * flip **mechanism/direction** (antagonise → degrade)

SCAFFOLD: the operators are stubbed as pure transforms; the *policy* (which loser
to mutate, which operator to apply, and keeping a diverse front — one elite per
niche) is the TODO to fill.
"""
from __future__ import annotations

from .hypothesis import Direction, Hypothesis, Modality

_MODALITY_LADDER = [Modality.ADC, Modality.BISPECIFIC, Modality.CAR_T]


def swap_modality(h: Hypothesis, new_id: str) -> Hypothesis:
    """Move the hypothesis one rung along the modality ladder (ADC→bispecific→CAR-T)."""
    try:
        nxt = _MODALITY_LADDER[(_MODALITY_LADDER.index(h.modality) + 1) % len(_MODALITY_LADDER)]
    except ValueError:
        nxt = _MODALITY_LADDER[0]
    return _child(h, new_id, modality=nxt, notes="mutated: swap_modality")


def narrow_stratum(h: Hypothesis, new_id: str, stratum: str = "antigen-high") -> Hypothesis:
    """Narrow the patient stratum (all-comers → antigen-high) to recover on safety."""
    return _child(h, new_id, patient_stratum=stratum, notes=f"mutated: narrow_stratum→{stratum}")


def flip_direction(h: Hypothesis, new_id: str) -> Hypothesis:
    """Flip the mechanism (antagonise → degrade), a common tractability rescue."""
    flip = Direction.DEGRADE if h.direction != Direction.DEGRADE else Direction.ANTAGONISE
    return _child(h, new_id, direction=flip, notes="mutated: flip_direction")


def mutate_loser(h: Hypothesis, new_id: str, losing_axis: str | None = None) -> Hypothesis:
    """Pick an operator by which axis the hypothesis lost on, and produce a child.

    TODO(B6): the policy. Route by ``losing_axis`` — lost on SAFETY → narrow_stratum;
    lost on TRACTABILITY → flip_direction/swap_modality; lost on TISSUE → swap to a
    more selective modality. Then re-enter the child into the arena and keep a
    *diverse* front (one elite per niche) so the population doesn't collapse to one
    idea. Placeholder routes SAFETY→narrow, TRACTABILITY→flip, else→swap.
    """
    if losing_axis == "safety":
        return narrow_stratum(h, new_id)
    if losing_axis == "tractability":
        return flip_direction(h, new_id)
    return swap_modality(h, new_id)


def _child(h: Hypothesis, new_id: str, **overrides) -> Hypothesis:
    base = dict(
        hypothesis_id=new_id, target=h.target, disease=h.disease, modality=h.modality,
        direction=h.direction, patient_stratum=h.patient_stratum, biomarker=h.biomarker,
        parent_id=h.hypothesis_id,
    )
    base.update(overrides)
    return Hypothesis(**base)
