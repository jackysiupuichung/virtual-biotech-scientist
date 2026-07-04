"""Smoke tests for the new arena / VoI framework — enough to pin the contracts.

These cover the IMPLEMENTED parts (card schema, Pareto dominance, Elo/Bradley-Terry
math, VoI budget loop, reviewer structural gap, mutation). The SCAFFOLD parts
(LLM judge, ToolUniverse calls, experiment backends) are asserted to raise
NotImplementedError so the "not yet wired" boundary is explicit and tested.
"""
from __future__ import annotations

import pytest

from vbs.arena.card import Axis, CostTier, Evidence, HypothesisCard
from vbs.arena import pareto
from vbs.arena.tournament import EloBoard, MatchResult, bradley_terry, judge_match
from vbs.arena.scheduler import round_robin
from vbs.arena.hypothesis import Hypothesis, Modality
from vbs.arena import mutate
from vbs.voi import selector
from vbs.cso import reviewer


def _card(hid, **axes):
    c = HypothesisCard(hid, hid)
    for a, v in axes.items():
        c.put(Evidence(a, v, 0.8, CostTier.LOOKUP, data_origin="test"))
    return c


def test_card_clamps_and_vector():
    c = _card("H0", **{Axis.TARGET: 1.5, Axis.SAFETY: -0.2})
    assert c.get(Axis.TARGET).value == 1.0  # clamped to [0,1]
    assert c.get(Axis.SAFETY).value == 0.0
    assert Axis.TISSUE in c.missing_axes()


def test_pareto_dominance_and_fronts():
    dom = _card("dom", **{a: 0.9 for a in Axis.ranking_axes()})
    weak = _card("weak", **{a: 0.1 for a in Axis.ranking_axes()})
    assert pareto.dominates(dom, weak)
    assert not pareto.dominates(weak, dom)
    fronts = pareto.fronts([dom, weak])
    assert fronts[0][0].hypothesis_id == "dom"


def test_pareto_tradeoff_is_one_front():
    a = _card("a", **{Axis.TARGET: 0.9, Axis.SAFETY: 0.1})
    b = _card("b", **{Axis.TARGET: 0.1, Axis.SAFETY: 0.9})
    assert len(pareto.fronts([a, b])) == 1  # neither dominates → same front


def test_elo_and_bradley_terry():
    ids = ["a", "b"]
    board = EloBoard(ids)
    res = MatchResult("a", "b", "a", 1.0)
    board.update(res)
    assert board.rating["a"] > board.rating["b"]
    bt = bradley_terry(ids, [res] * 5)
    assert bt["a"] > bt["b"]
    assert abs(sum(bt.values()) - 1.0) < 1e-6


def test_offline_judge_runs_without_llm():
    a = _card("a", **{Axis.TARGET: 0.9})
    b = _card("b", **{Axis.TARGET: 0.1})
    res = judge_match(a, b)  # runner=None → deterministic placeholder
    assert res.winner_id == "a"


def test_round_robin_pair_count():
    assert len(round_robin(["a", "b", "c"])) == 3


def test_voi_loop_resolves_missing_and_stops():
    cards = [_card("H0", **{Axis.TARGET: 0.8}), _card("H1")]

    def execute(action):
        card = next(c for c in cards if c.hypothesis_id == action.hypothesis_id)
        card.put(Evidence(action.axis, 0.5, 0.9, action.cost, data_origin="resolved"))

    res = selector.run_loop(cards, execute, budget=100)
    assert res.executed
    assert not cards[1].missing_axes()  # fully resolved
    # no-thrash: no action key repeats
    keys = [a.key() for a in res.executed]
    assert len(keys) == len(set(keys))


def test_reviewer_forces_reroute_on_missing_required_axis():
    incomplete = _card("H0", **{Axis.TARGET: 0.8})  # missing TISSUE/SAFETY/TRACTABILITY
    verdict = reviewer.review([incomplete])
    assert verdict.verdict == "re-route"
    assert verdict.reroutes[0].forced_by_structure


def test_reviewer_synthesises_when_required_axes_present():
    complete = _card("H0", **{a: 0.7 for a in reviewer.REQUIRED_AXES})
    assert reviewer.review([complete]).verdict == "synthesize"


def test_mutation_narrows_stratum_on_safety_loss():
    h = Hypothesis("H0", "B7-H3", "LUAD", Modality.ADC)
    child = mutate.mutate_loser(h, "H0m", "safety")
    assert child.parent_id == "H0"
    assert child.patient_stratum != "all-comers"


def test_card_schema_matches_jcaky_fixture():
    """Lock alignment: the fixture loads, and an axis entry round-trips field-for-field."""
    import os
    from vbs.arena.card import Axis
    from vbs.arena.fixture_loader import load

    fixture = os.path.join(os.path.dirname(__file__), "..", "arena", "fixtures",
                           "melanoma.hypotheses.json")
    if not os.path.exists(fixture):
        pytest.skip("melanoma fixture not present")
    cards, positives, symbol_by_hid = load(fixture)
    assert len(cards) == 15 and sum(positives.values()) == 3
    # axis keys are jcaky's right_* convention
    assert Axis.TARGET.value == "right_target"
    ev = cards[0].get(Axis.TARGET)
    rec = ev.to_record()
    assert set(rec) >= {"value", "confidence", "cost", "direction", "data_origin",
                        "finding", "interpretation"}
    assert rec["cost"] in (1, 2, 3)  # jcaky's ordinal tiers


def test_scaffold_boundaries_raise():
    from vbs.tooluniverse.client import ToolUniverseClient
    with pytest.raises(NotImplementedError):
        ToolUniverseClient().connect()
    from vbs.experiments.interface import _REGISTRY
    with pytest.raises(NotImplementedError):
        _REGISTRY["boltz2"].run(Hypothesis("H0", "EGFR", "LUAD", Modality.SMALL_MOLECULE))
