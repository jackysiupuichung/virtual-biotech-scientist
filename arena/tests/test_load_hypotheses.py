"""_load_hypotheses accepts both the arena fixture and virtual-biotech-cso 5R cards."""
import json
import os

from arena.pareto_agent.run import _adapt_cso_card, _is_cso_card, _load_hypotheses

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
CARDS_DIR = os.path.join(ROOT, "skills/virtual-biotech-cso/eval/arena_set/cards")
FIXTURE = os.path.join(ROOT, "arena/fixtures/melanoma.hypotheses.json")


def test_fixture_format_unchanged():
    # the arena's own fixture still loads as before (no regression)
    hyps = _load_hypotheses(FIXTURE)
    assert len(hyps) > 0
    assert all("id" in h for h in hyps)


def test_cso_card_detection():
    assert _is_cso_card({"per_axis": {}})
    assert _is_cso_card([{"per_axis": {}}])
    assert not _is_cso_card({"hypotheses": [{"id": "H1"}]})
    assert not _is_cso_card([{"id": "H1", "axes": {}}])


def test_adapt_single_card_has_required_id_and_axes():
    card = {"target": "BRAF", "disease": "melanoma",
            "per_axis": {"right_target": {"finding": "strong causal link",
                                          "grade": "strong", "provenance": "OT"}}}
    h = _adapt_cso_card(card, 1, label={"positive": True})
    # the arena keys on 'id' by name — it must exist
    assert h["id"] == "H1_BRAF"
    assert h["target"]["symbol"] == "BRAF"
    assert h["axes"]["right_target"]["finding"] == "strong causal link"
    assert h["axes"]["right_target"]["strength"] == "strong"
    assert h["label"] == {"positive": True}


def test_cards_directory_loads_with_labels():
    if not os.path.isdir(CARDS_DIR):
        return  # cards not present in this checkout
    hyps = _load_hypotheses(CARDS_DIR)
    assert len(hyps) == 10
    assert all("id" in h for h in hyps)                 # every hyp is judge-ready
    assert all("per_axis" not in h for h in hyps)       # adapted, not raw cards
    positives = {h["target"]["symbol"] for h in hyps if h.get("label", {}).get("positive")}
    assert positives == {"BRAF", "MAP2K1", "KDR"}       # labels attached from manifest
