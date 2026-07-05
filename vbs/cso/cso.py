"""cso.py — the CSO orchestrator (DESIGN.md §2.1).

Migrated *role* (A1) from virtual-biotech-agents' cso.py: the CSO turns a query
into a briefing + a decomposition + a routing plan, integrates division outputs,
and states the recommendation — running **no analysis itself** (the reasoning
roles are delegated to the driving agent via prompts/, the verdict to the arena).
Maintains a traceable decision log (every claim → the tool/evidence behind it).

Key change from the source: the source's terminal step was a **Prometheux verdict
on one hypothesis**; here the CSO hands the framed hypotheses to the **arena** for
a multi-objective ranking (DESIGN §2.2). SCAFFOLD: briefing/decompose/synthesis
are structured stubs that call an optional ``runner`` (vbs.runners) and fall back
to honest deterministic plans when no backend is set — matching the source's
stub-when-keyless behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..arena.hypothesis import HypothesisSlate, frame_slate
from ..divisions.base import DIVISIONS, DivisionSpec


@dataclass
class Briefing:
    """Chief-of-Staff pre-analysis: field context + data availability (DESIGN §2.1)."""

    query: str
    disease: str
    context: str = ""
    data_availability: str = ""


@dataclass
class Plan:
    """The CSO's decomposition + routing: which divisions run on which axes."""

    slate: HypothesisSlate
    routed: list[DivisionSpec] = field(default_factory=list)


class CSO:
    """Orchestrator: brief → decompose → route → (divisions) → integrate → hand to arena."""

    def __init__(self, runner=None) -> None:
        self.runner = runner  # vbs.runners.Runner or None (offline stub)
        self.decision_log: list[dict] = []

    def brief(self, query: str, disease: str) -> Briefing:
        """Chief-of-Staff briefing (prompts/chief_of_staff.md).

        TODO(A1): with a runner, produce field context + data-availability so effort
        goes where it counts. Offline: an honest empty briefing.
        """
        return Briefing(query=query, disease=disease)

    def decompose(self, briefing: Briefing, targets: list[str]) -> Plan:
        """Frame the competing hypothesis slate and route divisions (prompts/orchestrator.md).

        TODO(A1): LLM framing of the slate (arena/hypothesis.frame_slate does the
        real framing once wired). Routing is deterministic: every division runs to
        populate its axes. Placeholder frames one hypothesis per candidate target.
        """
        slate = frame_slate(briefing.disease, targets, runner=self.runner)
        return Plan(slate=slate, routed=list(DIVISIONS))

    def synthesize(self, plan: Plan, ranking: list[str]) -> dict:
        """State the recommendation from the arena ranking (prompts/orchestrator.md).

        TODO(A1): with a runner, write the narrative recommendation citing the
        arena's Pareto front + tournament board, every claim traceable via the
        decision log. Offline: return the structured ranking as the recommendation.
        """
        return {
            "disease": plan.slate.disease,
            "ranking": ranking,
            "top": ranking[0] if ranking else None,
            "decision_log": self.decision_log,
        }
