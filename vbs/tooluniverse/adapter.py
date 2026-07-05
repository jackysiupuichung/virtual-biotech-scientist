"""adapter.py — map ToolUniverse tool payloads onto the card contract (DESIGN.md §3.2).

Every division consumes ToolUniverse output but the arena/VoI only compose if the
result is normalised to ``Evidence(value, axis, confidence, cost)``. This module
is the seam: one adapter per tool, each turning a raw ToolUniverse JSON payload
into an Evidence on the right AZ-5R axis, with cost = the tool's tier and
provenance = the tool id.

SCAFFOLD: the axis/cost mapping table is defined (real, load-bearing design
decisions); each adapter's field extraction + [0,1] normalisation is the TODO.
"""
from __future__ import annotations

from typing import Any, Callable

from ..arena.card import Axis, CostTier, Evidence

# Which axis + cost tier each exposed tool feeds (DESIGN §3.1 axis table, §3.2 tiers).
TOOL_AXIS: dict[str, tuple[Axis, CostTier]] = {
    "OpenTargets_get_associated_diseases": (Axis.TARGET, CostTier.LOOKUP),
    "OpenTargets_get_target_factors": (Axis.SAFETY, CostTier.LOOKUP),
    "OpenFDA_get_adverse_events": (Axis.SAFETY, CostTier.LOOKUP),
    "ClinicalTrials_search": (Axis.PATIENT, CostTier.LOOKUP),
    "Boltz2_predict_binding_affinity": (Axis.TRACTABILITY, CostTier.EXPERIMENT),
}


def to_evidence(tool: str, payload: dict[str, Any]) -> Evidence:
    """Normalise a raw ToolUniverse payload into an Evidence on its mapped axis.

    TODO(B5): per-tool field extraction + [0,1] normalisation. E.g. OT association
    → value = normalised association score; openFDA AE → value = 1 − normalised
    adverse-event burden (higher = safer); clinical-trials → value from max phase.
    Set ``confidence`` from result completeness / n. The axis+cost come from
    TOOL_AXIS; provenance = the tool id.
    """
    axis, cost = TOOL_AXIS.get(tool, (Axis.TARGET, CostTier.LOOKUP))
    raise NotImplementedError(
        f"adapter for {tool!r} not wired — extract fields from payload and "
        f"normalise → Evidence(axis={axis.value}, cost={int(cost)}). See TODO(B5)."
    )


# Registry so divisions can look up an adapter by tool name (extend as tools are added).
ADAPTERS: dict[str, Callable[[dict[str, Any]], Evidence]] = {}
