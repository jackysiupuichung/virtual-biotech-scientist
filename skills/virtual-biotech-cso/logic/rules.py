"""The rule set — stratified Datalog, evaluated in Python.

Each rule is a pure function ``base -> new_facts`` over the current fact set. The
engine applies a stratum's rules to a fixpoint before moving to the next stratum, so
negation (``not p(X)``) is only ever taken over a *lower*, already-saturated stratum —
i.e. the program is stratified and its least model is well-defined and deterministic.

The Datalog these mirror (canonical form, also in ``README.md``):

  # stratum 1 — coverage & safety signals (positive over EDB)
  axis_covered(A)    :- graded(_, A, G), G != "absent".
  axis_attempted(A)  :- evidence(_, A, _, _).
  axis_score(A, 2)   :- scored_axis(A), graded(_, A, "strong").
  safety_fail(A)     :- safety_axis(A), safety_signal(_, "boxed_warning").
  safety_fail(A)     :- safety_axis(A), safety_signal(_, "serious_ae").

  # stratum 2 — gaps, decision floor, report grounding (negation over stratum 1)
  axis_score(A, 1)   :- scored_axis(A), graded(_, A, "supporting"), not axis_score(A, 2).
  axis_score(A, 0)   :- scored_axis(A), not axis_covered(A).
  axis_unassessed(A) :- required_axis(A), not axis_attempted(A).
  force_reroute(A,S) :- axis_unassessed(A), route_skill(A, S).
  floor_nogo         :- safety_fail(_).
  report_downgrade(S,"strong","supporting")
                     :- graded(S,_,"strong"), executed(S,_), not nonempty(S).
  report_reject(S)   :- graded(S,_,"strong"), not executed(S,_).

``force_reroute`` (a required axis with no graded evidence) and ``floor_nogo`` (a
serious safety signal) are the *non-silenceable floor*: they are pure functions of the
evidence, independent of any LLM output, and the harness honours them over the panel
vote / synthesis tier.
"""

from __future__ import annotations

from typing import Callable

from .facts import Fact, f


def _args_where(base: set[Fact], pred: str) -> list[tuple]:
    return [fact.args for fact in base if fact.pred == pred]


def _has(base: set[Fact], pred: str, *args) -> bool:
    return Fact(pred, tuple(args)) in base


# --------------------------------------------------------------------------- #
# Stratum 1 — positive rules over the EDB
# --------------------------------------------------------------------------- #

def r_axis_covered(base: set[Fact]) -> set[Fact]:
    out: set[Fact] = set()
    for (_step, axis, grade) in _args_where(base, "graded"):
        if grade != "absent":
            out.add(f("axis_covered", axis))
    return out


def r_axis_attempted(base: set[Fact]) -> set[Fact]:
    """An axis was *attempted* if any evidence row exists for it — regardless of grade.
    Distinct from ``axis_covered`` (which needs non-absent evidence): a step that ran
    but returned nothing still counts as attempted, so it is not a *structural* gap."""
    return {f("axis_attempted", axis) for (_step, axis, _skill, _src)
            in _args_where(base, "evidence")}


def r_axis_score_strong(base: set[Fact]) -> set[Fact]:
    out: set[Fact] = set()
    scored = {a for (a,) in _args_where(base, "scored_axis")}
    for (_step, axis, grade) in _args_where(base, "graded"):
        if grade == "strong" and axis in scored:
            out.add(f("axis_score", axis, 2))
    return out


def r_safety_fail(base: set[Fact]) -> set[Fact]:
    out: set[Fact] = set()
    safety_axes = {a for (a,) in _args_where(base, "safety_axis")}
    signals = {kind for (_step, kind) in _args_where(base, "safety_signal")}
    for axis in safety_axes:
        if "boxed_warning" in signals or "serious_ae" in signals:
            out.add(f("safety_fail", axis))
    return out


# --------------------------------------------------------------------------- #
# Stratum 2 — rules that read negation over the saturated stratum 1
# --------------------------------------------------------------------------- #

def r_axis_score_supporting(base: set[Fact]) -> set[Fact]:
    """supporting → 1, but only if the axis has no strong grade (else strong wins)."""
    out: set[Fact] = set()
    scored = {a for (a,) in _args_where(base, "scored_axis")}
    for (_step, axis, grade) in _args_where(base, "graded"):
        if grade == "supporting" and axis in scored and not _has(base, "axis_score", axis, 2):
            out.add(f("axis_score", axis, 1))
    return out


def r_axis_score_absent(base: set[Fact]) -> set[Fact]:
    out: set[Fact] = set()
    for (axis,) in _args_where(base, "scored_axis"):
        if not _has(base, "axis_covered", axis):
            out.add(f("axis_score", axis, 0))
    return out


def r_axis_unassessed(base: set[Fact]) -> set[Fact]:
    """A *structural* gap: a required axis with no evidence row at all (never
    attempted). This — not a low grade — is what forces a re-route. An axis that was
    attempted but returned weak/absent evidence is a coverage question for the LLM
    lenses, not a structural gap for the engine."""
    out: set[Fact] = set()
    for (axis,) in _args_where(base, "required_axis"):
        if not _has(base, "axis_attempted", axis):
            out.add(f("axis_unassessed", axis))
    return out


def r_force_reroute(base: set[Fact]) -> set[Fact]:
    out: set[Fact] = set()
    route = {axis: skill for (axis, skill) in _args_where(base, "route_skill")}
    for (axis,) in _args_where(base, "axis_unassessed"):
        skill = route.get(axis)
        if skill:
            out.add(f("force_reroute", axis, skill))
    return out


def r_floor_nogo(base: set[Fact]) -> set[Fact]:
    if _args_where(base, "safety_fail"):
        return {f("floor_nogo")}
    return set()


def r_report_downgrade(base: set[Fact]) -> set[Fact]:
    """A 'strong' grade that executed but returned no content is only 'supporting'."""
    out: set[Fact] = set()
    for (step, _axis, grade) in _args_where(base, "graded"):
        if grade != "strong":
            continue
        executed = any(s == step for (s, _src) in _args_where(base, "executed"))
        if executed and not _has(base, "nonempty", step):
            out.add(f("report_downgrade", step, "strong", "supporting"))
    return out


def r_report_reject(base: set[Fact]) -> set[Fact]:
    """A 'strong' grade with no executed source is fabricated — reject the row."""
    out: set[Fact] = set()
    for (step, _axis, grade) in _args_where(base, "graded"):
        if grade != "strong":
            continue
        executed = any(s == step for (s, _src) in _args_where(base, "executed"))
        if not executed:
            out.add(f("report_reject", step))
    return out


# Stratified program: list of strata, each a list of rule functions. The engine
# saturates stratum i before starting stratum i+1.
STRATA: list[list[Callable[[set[Fact]], set[Fact]]]] = [
    [r_axis_covered, r_axis_attempted, r_axis_score_strong, r_safety_fail],
    [
        r_axis_score_supporting,
        r_axis_score_absent,
        r_axis_unassessed,
        r_force_reroute,
        r_floor_nogo,
        r_report_downgrade,
        r_report_reject,
    ],
]
