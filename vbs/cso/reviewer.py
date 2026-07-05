"""reviewer.py — the Scientific Reviewer panel + re-route loop (DESIGN.md §2.1).

Migrated *shape* (A4) from virtual-biotech-agents' reviewer panel: multiple lenses
(completeness · methodology · …) audit the integrated evidence, vote, and a
majority **forces a re-route** to a division to fill a gap — the paper's audit
step, and our refinement mechanism *before* a hypothesis enters the arena. The
prompt is migrated verbatim at vbs/cso/prompts/reviewer.md.

Key change from the source: the source's non-silenceable gap-detector was a
**Prometheux Vadalog** structural rule. Here the same idea becomes a **structural
axis-coverage check** (a hypothesis card missing a required axis is a provable gap
that forces re-work) — no Prometheux dependency. IMPLEMENTED: the structural gap
check + reroute-request aggregation. SCAFFOLD: the LLM-lens panel vote.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..arena.card import Axis, HypothesisCard

# Axes that MUST be resolved before a hypothesis is allowed into the arena.
# Absence here is a structural, non-silenceable gap (the deductive fact that
# replaces the source's Prometheux gap-detector).
REQUIRED_AXES = [Axis.TARGET, Axis.TISSUE, Axis.SAFETY, Axis.TRACTABILITY]


@dataclass
class RerouteRequest:
    """A gap the reviewer wants filled: which hypothesis, which axis, why."""

    hypothesis_id: str
    axis: Axis
    reason: str
    forced_by_structure: bool = False  # True = provable missing required axis (non-silenceable)


@dataclass
class ReviewVerdict:
    """Panel outcome: synthesize now, or re-route to fill gaps first."""

    verdict: str  # "synthesize" | "re-route"
    reroutes: list[RerouteRequest] = field(default_factory=list)
    lens_votes: dict[str, str] = field(default_factory=dict)


def structural_gaps(cards: list[HypothesisCard]) -> list[RerouteRequest]:
    """Provable gaps: any required axis absent on any card (IMPLEMENTED).

    This is the non-silenceable panel member — it needs no LLM and cannot be
    voted down: a missing required axis is a deductive fact, so it forces re-work.
    """
    out: list[RerouteRequest] = []
    for c in cards:
        for axis in c.missing_axes(REQUIRED_AXES):
            out.append(RerouteRequest(
                hypothesis_id=c.hypothesis_id, axis=axis,
                reason=f"required axis {axis.value!r} unresolved for {c.label}",
                forced_by_structure=True,
            ))
    return out


def review(cards: list[HypothesisCard], *, runner=None,
           max_reroutes: int = 1) -> ReviewVerdict:
    """Audit the cards; force a re-route on the highest-value gap, else synthesize.

    IMPLEMENTED: the structural gap path (forces re-route when a required axis is
    missing), capped at ``max_reroutes`` per pass so the loop converges — the
    source's "force exactly one re-route" rule.

    TODO(A4): the LLM lens panel — completeness/methodology/etc. judges (via
    ``runner``, prompt at prompts/reviewer.md), order-swapped, majority vote adds
    *soft* reroutes ranked below the structural ones. Aggregate as
    (forced_by_structure desc, corroborating-lens-count desc) so a provably-missing
    required axis is always filled first (mirrors the source's aggregate ranking).
    """
    gaps = structural_gaps(cards)
    if gaps:
        return ReviewVerdict(verdict="re-route", reroutes=gaps[:max_reroutes])
    # TODO(A4): run the LLM lens panel here for soft gaps before declaring done.
    return ReviewVerdict(verdict="synthesize")
