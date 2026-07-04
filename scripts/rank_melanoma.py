#!/usr/bin/env python
"""rank_melanoma.py — the first real closed loop: fixture → arena → AUGC.

Loads jcaky's melanoma hypothesis-card fixture, ranks it with our arena
(Pareto front + scalarised tie-break), scores the ranking against the fixture's
embedded clinical-outcome labels with the eval's AUGC metric, and compares it to
the single-axis Open Targets baseline (sort on the Right Target association only).

This is the minimal end-to-end proof that the two halves connect on REAL data:
evidence cards (jcaky) → ranking (our arena) → measured AUGC (eval).

Run:  python scripts/rank_melanoma.py
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from eval.augc import augc  # noqa: E402
from vbs.arena import pareto  # noqa: E402
from vbs.arena.card import Axis  # noqa: E402
from vbs.arena.fixture_loader import load  # noqa: E402

FIXTURE = os.path.join(ROOT, "arena", "fixtures", "melanoma.hypotheses.json")


def _symbols(hid_ranking, symbol_by_hid):
    """Map a hypothesis-id ranking to the target-symbol ranking AUGC scores on."""
    return [symbol_by_hid[h] for h in hid_ranking]


def main() -> None:
    cards, positives, symbol_by_hid = load(FIXTURE)
    pos_symbols = {s for s, is_pos in positives.items() if is_pos}
    n_pos = len(pos_symbols)
    print(f"fixture: {len(cards)} hypotheses · {n_pos} positive "
          f"({n_pos / len(cards):.0%}) · pool = the 15 cards themselves\n")

    # --- 1. our arena: multi-objective Pareto + scalarised tie-break ---
    arena_hids = pareto.rank(cards)
    arena_syms = _symbols(arena_hids, symbol_by_hid)
    arena_augc, _ = augc(arena_syms, pos_symbols)

    # --- 2. baseline: sort on the Right Target (OT association) axis alone ---
    ot_sorted = sorted(cards, key=lambda c: c.get(Axis.TARGET).value if c.get(Axis.TARGET) else 0.0,
                       reverse=True)
    ot_syms = [symbol_by_hid[c.hypothesis_id] for c in ot_sorted]
    ot_augc, _ = augc(ot_syms, pos_symbols)

    # --- report ---
    fronts = pareto.fronts(cards)
    print(f"Pareto: {len(fronts)} front(s); front-1 = "
          f"{[symbol_by_hid[c.hypothesis_id] for c in fronts[0]]}\n")
    print("ranking (arena, best→worst):")
    for i, (hid, sym) in enumerate(zip(arena_hids, arena_syms), 1):
        mark = "  ✅ clinical positive" if sym in pos_symbols else ""
        print(f"  {i:2}. {sym}{mark}")
    print()
    print("=" * 46)
    print(f"  arena (multi-objective)   AUGC = {arena_augc:+.4f}")
    print(f"  OT single-axis baseline   AUGC = {ot_augc:+.4f}")
    print("=" * 46)
    print("  (1.0 = perfect · 0.0 = random · reference: OT on full pool ≈ 0.45)")


if __name__ == "__main__":
    main()
