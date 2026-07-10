"""Fact contract for the symbolic logic layer.

Evidence envelopes (``{step, division, skill, question, result, source}`` — see
``cso.execute_skill``) are projected into a set of ground :class:`Fact` tuples (the
EDB). The rule engine (``engine.py`` + ``rules.py``) then derives the IDB. Both the
loop grounding (``_engine_gaps``/``_engine_decision``) and the report grounding read
that one shared fact base — the facts are derived once per loop pass.

A ``Fact`` is a predicate name plus a tuple of ground (hashable) arguments, so the
whole base is a ``set[Fact]`` — deterministic, order-free, and cheap to reason over.
This deliberately avoids any external logic engine (none is pinned); a real Vadalog
backend can replace the evaluator behind the ``LogicEngine`` interface later while
keeping this exact fact vocabulary.
"""

from __future__ import annotations

from typing import Any, NamedTuple


class Fact(NamedTuple):
    """One ground atom: ``pred(*args)``. ``args`` must be hashable."""

    pred: str
    args: tuple[Any, ...]


def f(pred: str, *args: Any) -> Fact:
    """Construct a :class:`Fact` — ``f("graded", step, axis, "strong")``."""
    return Fact(pred, tuple(args))


# --------------------------------------------------------------------------- #
# Configuration facts (static — derived from routing.yaml + policy)
# --------------------------------------------------------------------------- #

# The prioritisation axes whose *absence of any graded evidence* is a structural
# gap that forces a re-route. Deliberately a subset of the 6 divisions: the
# landscape axis (right_commercial) and the cross-cutting tractability axis are
# non-core — leaving them unassessed never *forces* control flow (the LLM lenses
# may still flag them). This mirrors the harness test contract: a plan covering
# {target, tissue, safety, patient} triggers no forced re-route, while one missing
# safety/tissue does. Kept as data so policy is one edit, not a code change.
CORE_AXES: tuple[str, ...] = (
    "right_target",
    "right_tissue",
    "right_safety",
    "right_patient",
)

# All six divisions contribute to the coverage score behind the GO/NO-GO tier.
ALL_AXES: tuple[str, ...] = (
    "right_target",
    "right_tissue",
    "right_safety",
    "right_patient",
    "right_commercial",
    "tractability",
)

# The axis the safety hard-gate watches.
SAFETY_AXIS = "right_safety"

# When an axis has no graded evidence, re-route to this skill to fill it. The value
# is a *skill name* (validated by ``cso._reroute_task`` against ``catalog_skills``),
# not an intent key. Chosen as the canonical live skill for each axis's gap.
AXIS_REROUTE_SKILL: dict[str, str] = {
    "right_target": "gwas-lookup",
    "right_tissue": "celltype-specificity-profiler",
    "right_safety": "openfda-safety",
    "right_patient": "clinical-trial-finder",
}

# Source labels that count as a real, executed evidence row. Kept in sync with
# ``cso.EXECUTED_SOURCES``; imported lazily in ``derive_facts`` to avoid a hard
# import cycle at module load.
_EXECUTED_SOURCES = ("tooluniverse", "tool-descriptor")

# Result keys / markers that indicate a serious safety signal on a right_safety row.
_BOXED_WARNING_KEYS = ("boxed_warning", "black_box_warning", "boxed_warnings")
_SERIOUS_AE_KEYS = ("serious_adverse_events", "serious_ae", "serious")


def _grade(env: dict[str, Any]) -> str:
    """Grade a step from its source. Mirrors ``cso._evidence_grade`` exactly.

    Imported from cso when available (single source of truth); falls back to an
    identical local map so this module stays importable in isolation (unit tests).
    """
    try:  # pragma: no cover - trivial import guard
        import cso  # type: ignore  # sibling module when the skill dir is on sys.path
    except Exception:
        cso = None  # noqa: N806
    if cso is not None and hasattr(cso, "_evidence_grade"):
        return cso._evidence_grade(env)
    src = env.get("source", "")
    return {"tooluniverse": "strong", "tool-descriptor": "supporting",
            "web": "supporting"}.get(src, "absent")


def _is_nonempty(result: Any) -> bool:
    """True iff the step returned real content (a non-empty dict without a bare
    'not executed' marker)."""
    if not isinstance(result, dict) or not result:
        return False
    status = str(result.get("status", "")).lower()
    if status in ("not executed", "unavailable", "error"):
        return False
    return True


def _safety_signals(result: Any) -> list[str]:
    """Serious-safety signal kinds found in a right_safety result payload."""
    kinds: list[str] = []
    if not isinstance(result, dict):
        return kinds
    blob = result
    # boxed warning: truthy under any of the known keys
    if any(blob.get(k) for k in _BOXED_WARNING_KEYS):
        kinds.append("boxed_warning")
    # serious AE: a truthy flag, or a positive count under known keys
    for k in _SERIOUS_AE_KEYS:
        v = blob.get(k)
        if isinstance(v, bool) and v:
            kinds.append("serious_ae")
            break
        if isinstance(v, (int, float)) and v > 0:
            kinds.append("serious_ae")
            break
    return kinds


def derive_edb(results: list[dict[str, Any]]) -> set[Fact]:
    """Project evidence envelopes + static config into the EDB (base facts).

    Predicates emitted:
      - ``evidence(step, axis, skill, source)``   — one per envelope
      - ``graded(step, axis, grade)``             — grade ∈ strong|supporting|absent
      - ``executed(step, source)``                — iff source is an executed source
      - ``nonempty(step)``                        — iff the result carries content
      - ``safety_signal(step, kind)``             — right_safety serious signals
      - ``required_axis(axis)``                   — the core forcing axes
      - ``scored_axis(axis)``                     — every axis in the coverage score
      - ``safety_axis(axis)``                     — the hard-gate axis
      - ``route_skill(axis, skill)``              — reroute target per core axis
    """
    facts: set[Fact] = set()
    for axis in CORE_AXES:
        facts.add(f("required_axis", axis))
    for axis in ALL_AXES:
        facts.add(f("scored_axis", axis))
    facts.add(f("safety_axis", SAFETY_AXIS))
    for axis, skill in AXIS_REROUTE_SKILL.items():
        facts.add(f("route_skill", axis, skill))

    for env in results:
        step = env.get("step", "")
        axis = env.get("division", "")
        skill = env.get("skill", "")
        source = env.get("source", "")
        result = env.get("result", {})
        facts.add(f("evidence", step, axis, skill, source))
        facts.add(f("graded", step, axis, _grade(env)))
        if source in _EXECUTED_SOURCES:
            facts.add(f("executed", step, source))
        if _is_nonempty(result):
            facts.add(f("nonempty", step))
        if axis == SAFETY_AXIS:
            for kind in _safety_signals(result):
                facts.add(f("safety_signal", step, kind))
    return facts
