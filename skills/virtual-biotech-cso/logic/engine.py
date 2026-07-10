"""The logic engine: stratified fixpoint evaluator + the LogicEngine interface.

``PyDatalogEngine`` derives a shared fact base from the evidence once, saturates the
stratified rule set to its least model, then answers three questions over that base:

  - ``gaps(facts)``           → structural re-route gaps for the loop
                                (``_engine_gaps`` → ``aggregate_panel_review``)
  - ``decision(facts)``       → the deductive GO/NO-GO tier for the report
                                (``_engine_decision`` → ``synthesize_report``)
  - ``validate_report(...)``  → per-step grade downgrades / row rejections
                                (report grounding, carried on the decision dict)

The three are pure reads over one base, so the loop and the report are grounded in the
*same* facts. ``derive_facts`` is memoised per ``results`` identity so the two harness
seams that both call it in a single pass share the computation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .facts import ALL_AXES, Fact, derive_edb
from .rules import STRATA, _args_where


class LogicEngine(ABC):
    """Interface a symbolic backend must satisfy. A real Vadalog engine can swap in
    behind this without touching the harness seams."""

    @abstractmethod
    def derive_facts(self, results: list[dict[str, Any]]) -> set[Fact]:
        ...

    @abstractmethod
    def gaps(self, facts: set[Fact]) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def decision(self, facts: set[Fact]) -> dict[str, Any] | None:
        ...

    @abstractmethod
    def validate_report(
        self, facts: set[Fact], rows: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        ...


# Coverage-score → tier bands. score is Σ axis_score over the 6 scored axes,
# max_score = 2 * len(ALL_AXES) = 12. A serious safety signal clamps to NO_GO
# regardless of coverage (the non-silenceable floor).
_GO_BAND = 0.66
_CONDITIONAL_BAND = 0.40


class PyDatalogEngine(LogicEngine):
    """Pure-Python stratified Datalog evaluator over ``set[Fact]`` — no external dep."""

    def __init__(self) -> None:
        self._cache: dict[int, set[Fact]] = {}

    # --- fixpoint --------------------------------------------------------- #

    def _saturate(self, edb: set[Fact]) -> set[Fact]:
        """Least model: saturate each stratum to a fixpoint, in order."""
        base = set(edb)
        for stratum in STRATA:
            while True:
                new: set[Fact] = set()
                for rule in stratum:
                    new |= rule(base)
                if new <= base:
                    break
                base |= new
        return base

    def derive_facts(self, results: list[dict[str, Any]]) -> set[Fact]:
        key = id(results)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        facts = self._saturate(derive_edb(results))
        self._cache[key] = facts
        return facts

    # --- loop grounding --------------------------------------------------- #

    def gaps(self, facts: set[Fact]) -> list[dict[str, Any]]:
        """One forcing gap per ``force_reroute(axis, skill)`` fact.

        ``route_to`` is a *skill name* (validated downstream by ``cso._reroute_task``
        against the catalog). ``forces_reroute`` makes it non-silenceable in
        ``aggregate_panel_review``; ``lenses=["prometheux"]`` tags provenance.
        """
        out: list[dict[str, Any]] = []
        for (axis, skill) in sorted(_args_where(facts, "force_reroute")):
            out.append({
                "missing": f"no graded evidence for {axis}",
                "route_to": skill,
                "why": (f"required axis '{axis}' has no strong/supporting evidence "
                        "(deductively derived structural gap)"),
                "forces_reroute": True,
                "lenses": ["prometheux"],
            })
        return out

    # --- decision grounding ----------------------------------------------- #

    def _coverage(self, facts: set[Fact]) -> tuple[int, int, list[str]]:
        """(score, max_score, absent_axes). Each axis contributes its single best
        axis_score (strong=2 > supporting=1 > absent=0)."""
        best: dict[str, int] = {}
        for (axis, s) in _args_where(facts, "axis_score"):
            best[axis] = max(best.get(axis, 0), s)
        score = sum(best.get(axis, 0) for axis in ALL_AXES)
        max_score = 2 * len(ALL_AXES)
        absent = sorted(axis for axis in ALL_AXES if best.get(axis, 0) == 0)
        return score, max_score, absent

    def decision(self, facts: set[Fact]) -> dict[str, Any]:
        score, max_score, absent = self._coverage(facts)
        floor = bool(_args_where(facts, "floor_nogo"))
        ratio = score / max_score if max_score else 0.0
        if floor:
            tier = "NO_GO"
            explanation = ("serious safety signal on the right_safety axis — "
                           "deductive safety hard-gate clamps the decision to NO_GO "
                           "irrespective of coverage")
        elif ratio >= _GO_BAND:
            tier = "GO"
            explanation = f"strong axis coverage ({score}/{max_score})"
        elif ratio >= _CONDITIONAL_BAND:
            tier = "CONDITIONAL_GO"
            explanation = f"partial axis coverage ({score}/{max_score})"
        else:
            tier = "REVIEW"
            explanation = (f"insufficient axis coverage ({score}/{max_score}) — "
                           "too little graded evidence to assert a go/no-go")
        return {
            "tier": tier,
            "decision": tier,
            "score": score,
            "max_score": max_score,
            "explanation": explanation,
            "absent_axes": absent,
            "floor_nogo": floor,
            "rationale": explanation,
        }

    # --- report grounding ------------------------------------------------- #

    def validate_report(
        self, facts: set[Fact], rows: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """Per-step grounding verdict: downgrade an ungrounded 'strong', reject a
        fabricated one. Keyed by step id so ``synthesize_report`` can consult it."""
        downgrades = {step: to for (step, _frm, to)
                      in _args_where(facts, "report_downgrade")}
        rejects = {step for (step,) in _args_where(facts, "report_reject")}
        grounding: dict[str, dict[str, Any]] = {}
        for step in set(downgrades) | rejects:
            grounding[step] = {
                "grade": downgrades.get(step),
                "reject": step in rejects,
            }
        return grounding


def default_engine() -> LogicEngine:
    """The default logic engine (pure-Python Datalog). A real Vadalog backend can be
    substituted here later without touching call sites."""
    return PyDatalogEngine()
