"""fixture_loader.py — load jcaky's hypothesis-card fixture into HypothesisCards.

jcaky's PR #1 (arena/synthetic-fixtures) ships the melanoma fixture of 15
hypothesis cards with mostly-real Open Targets evidence. Now that ``card.py``
adopts his card contract verbatim (axis keys ``right_*``, cost tiers 1/2/3, the
full axis-entry fields), this is a direct load — ``Evidence.from_entry`` and
``Axis(key)`` map 1:1, no reconciliation needed.

The embedded ``label.positive`` is the eval ground truth — returned separately and
NOT put on the card (judges must not see it).
"""
from __future__ import annotations

import json
from pathlib import Path

from .card import Axis, Evidence, HypothesisCard


def load(path: str | Path) -> tuple[list[HypothesisCard], dict[str, bool], dict[str, str]]:
    """Return (cards, positives_by_symbol, symbol_by_hypothesis_id).

    ``positives`` maps target symbol → is it a true clinical positive (eval label);
    ``symbol_by_hid`` lets a hypothesis-id ranking be scored on target symbols
    (what eval/augc.py works on).
    """
    data = json.loads(Path(path).read_text())
    raw = data["hypotheses"] if isinstance(data, dict) else data
    cards: list[HypothesisCard] = []
    positives: dict[str, bool] = {}
    symbol_by_hid: dict[str, str] = {}
    for h in raw:
        hid = h["id"]
        symbol = h["target"]["symbol"]
        symbol_by_hid[hid] = symbol
        positives[symbol] = bool(h.get("label", {}).get("positive"))
        card = HypothesisCard(hypothesis_id=hid,
                              label=f"{symbol} · {h.get('modality', '?')} · {h['disease']['name']}")
        for key, entry in h["axes"].items():
            if key in Axis._value2member_map_:  # skip any unknown axis key gracefully
                card.put(Evidence.from_entry(Axis(key), entry))
        cards.append(card)
    return cards, positives, symbol_by_hid
