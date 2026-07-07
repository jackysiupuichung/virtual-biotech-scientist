"""Unit tests for the symbolic logic layer (logic/) — pure engine, no harness/LLM.

These prove the fact/rule derivation is correct and, crucially, that the two floor
mechanisms are *non-silenceable*: a required axis with no evidence forces a re-route,
and a serious safety signal clamps the decision to NO_GO regardless of coverage.
"""
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR))

import logic  # noqa: E402
from logic.facts import Fact, derive_edb, f  # noqa: E402


def _env(step, division, source, result=None):
    return {"step": step, "division": division, "skill": f"skill-{division}",
            "question": "q?", "result": result if result is not None else {}, "source": source}


# A "full" evidence set: every core axis attempted with real (tooluniverse) data.
def _full_results():
    return [
        _env("s1", "right_target", "tooluniverse", {"hit": 1}),
        _env("s2", "right_tissue", "tooluniverse", {"tau": 0.9}),
        _env("s3", "right_safety", "tooluniverse", {"boxed_warning": False}),
        _env("s4", "right_patient", "tooluniverse", {"trials": 3}),
    ]


# --------------------------- fact derivation ------------------------------- #

def test_derive_facts_grades_from_source():
    facts = logic.default_engine().derive_facts([
        _env("s1", "right_target", "tooluniverse", {"hit": 1}),
        _env("s2", "right_tissue", "unavailable"),
    ])
    assert f("graded", "s1", "right_target", "strong") in facts
    assert f("graded", "s2", "right_tissue", "absent") in facts
    assert f("executed", "s1", "tooluniverse") in facts
    # an unavailable step is neither executed nor nonempty
    assert not any(fact.pred == "executed" and fact.args[0] == "s2" for fact in facts)


def test_axis_attempted_distinct_from_covered():
    # a step that ran but graded absent is *attempted* (no structural gap) but not covered
    facts = logic.default_engine().derive_facts([_env("s1", "right_safety", "unavailable")])
    assert f("axis_attempted", "right_safety") in facts
    assert f("axis_covered", "right_safety") not in facts
    assert f("axis_unassessed", "right_safety") not in facts  # attempted → not structural gap


# --------------------------- loop grounding -------------------------------- #

def test_required_axis_never_attempted_forces_reroute():
    eng = logic.default_engine()
    # only right_target attempted → safety/tissue/patient are structural gaps
    facts = eng.derive_facts([_env("s1", "right_target", "tooluniverse", {"hit": 1})])
    gaps = eng.gaps(facts)
    routed = {g["route_to"] for g in gaps}
    assert {"openfda-safety", "celltype-specificity-profiler", "clinical-trial-finder"} <= routed
    assert all(g["forces_reroute"] for g in gaps)
    assert all(g["lenses"] == ["prometheux"] for g in gaps)


def test_full_coverage_no_forced_gap():
    eng = logic.default_engine()
    gaps = eng.gaps(eng.derive_facts(_full_results()))
    assert gaps == []


# --------------------------- decision grounding ---------------------------- #

def test_all_absent_yields_review():
    eng = logic.default_engine()
    results = [_env(f"s{i}", ax, "unavailable")
               for i, ax in enumerate(("right_target", "right_tissue",
                                       "right_safety", "right_patient"))]
    d = eng.decision(eng.derive_facts(results))
    assert d["tier"] == "REVIEW"
    assert d["score"] == 0


def test_full_strong_coverage_yields_go():
    eng = logic.default_engine()
    d = eng.decision(eng.derive_facts(_full_results()))
    # 4 axes strong (score 8) of 12 → 0.66 → GO band boundary; add commercial+tractability
    results = _full_results() + [
        _env("s5", "right_commercial", "tooluniverse", {"x": 1}),
        _env("s6", "tractability", "tooluniverse", {"x": 1}),
    ]
    d2 = eng.decision(eng.derive_facts(results))
    assert d2["tier"] == "GO"
    assert d2["score"] == 12


def test_safety_signal_forces_nogo_floor():
    """The non-silenceable NO_GO proof: a boxed warning clamps to NO_GO even with
    otherwise-GO full strong coverage across all six axes."""
    eng = logic.default_engine()
    results = _full_results() + [
        _env("s5", "right_commercial", "tooluniverse", {"x": 1}),
        _env("s6", "tractability", "tooluniverse", {"x": 1}),
        _env("s7", "right_safety", "tooluniverse", {"boxed_warning": True}),
    ]
    d = eng.decision(eng.derive_facts(results))
    assert d["tier"] == "NO_GO"
    assert d["floor_nogo"] is True


def test_serious_ae_count_forces_nogo():
    eng = logic.default_engine()
    results = _full_results() + [_env("s7", "right_safety", "tooluniverse",
                                      {"serious_adverse_events": 42})]
    d = eng.decision(eng.derive_facts(results))
    assert d["tier"] == "NO_GO"


# --------------------------- report grounding ------------------------------ #

def test_report_downgrade_strong_without_result():
    eng = logic.default_engine()
    # executed (tooluniverse) but empty result → 'strong' downgraded to 'supporting'
    facts = eng.derive_facts([_env("s1", "right_target", "tooluniverse", {})])
    grounding = eng.validate_report(facts, [])
    assert grounding["s1"]["grade"] == "supporting"
    assert grounding["s1"]["reject"] is False


def test_report_reject_strong_without_execution():
    # A fabricated 'strong' grade with no executed source must be rejected. Build the
    # EDB directly (a real envelope can't produce this via _evidence_grade, so we test
    # the rule against the pathological fact set it guards against) and saturate.
    from logic.engine import PyDatalogEngine
    eng = PyDatalogEngine()
    edb = {f("graded", "s1", "right_target", "strong")}  # strong, but no executed(s1)
    facts = eng._saturate(edb)
    grounding = eng.validate_report(facts, [])
    assert grounding["s1"]["reject"] is True


def test_grounded_strong_is_clean():
    eng = logic.default_engine()
    facts = eng.derive_facts([_env("s1", "right_target", "tooluniverse", {"hit": 1})])
    grounding = eng.validate_report(facts, [])
    assert "s1" not in grounding  # a properly grounded strong row has no verdict


# --------------------------- determinism ----------------------------------- #

def test_fixpoint_is_deterministic():
    eng = logic.default_engine()
    results = _full_results()
    a = frozenset(eng.derive_facts(list(results)))
    b = frozenset(logic.default_engine().derive_facts(list(results)))
    assert a == b


def test_derive_edb_is_pure_set():
    facts = derive_edb(_full_results())
    assert all(isinstance(x, Fact) for x in facts)
    assert len(facts) == len(set(facts))
