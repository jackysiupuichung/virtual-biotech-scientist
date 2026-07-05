#!/usr/bin/env python
"""harness.py — the closed-loop driver (DESIGN.md §2.2).

Migrated *control flow* (A1) from virtual-biotech-agents' harness: it runs the
loop query → brief → decompose → route to divisions → Scientific Reviewer audit →
(re-route to fill a gap) → hand hypotheses to the ARENA → rank → synthesize, with
an execution trace (vbs/tracing.py) and offline `--demo` / live `--live` modes.

Two changes from the source, both by design:
  1. the verdict layer is the **arena** (Pareto + tournament), not a Prometheux
     single-hypothesis tier;
  2. the evidence layer is **ToolUniverse**, not ClawBio.

Status: the loop skeleton + `--demo` are RUNNABLE on synthetic cards so the arena,
the VoI selector, and the tournament execute end-to-end today. The live evidence
path (divisions calling ToolUniverse; run_experiment) is scaffolded — see the
per-step TODOs and MIGRATION_CHECKLIST.md.
"""
from __future__ import annotations

import argparse
import json

from ..arena.card import Axis, CostTier, Evidence, HypothesisCard
from ..arena import pareto
from ..arena.scheduler import schedule
from ..arena.tournament import EloBoard, bradley_terry, judge_match
from . import reviewer
from .cso import CSO


# --------------------------------------------------------------------------- #
# Demo fixtures — synthetic cards so the arena/VoI/tournament run with no keys.
# Clearly synthetic (NOT the migrated ClawBio b7h3 fixtures, which are a different
# shape); this exists only to prove the new framework executes end-to-end.
# --------------------------------------------------------------------------- #

_DEMO_CARDS = [
    ("H00", "B7-H3 · adc · LUAD · stromal-high",
     {Axis.TARGET: 0.82, Axis.TISSUE: 0.90, Axis.SAFETY: 0.55, Axis.TRACTABILITY: 0.70}),
    ("H01", "EGFR · small_molecule · LUAD",
     {Axis.TARGET: 0.95, Axis.TISSUE: 0.40, Axis.SAFETY: 0.60, Axis.TRACTABILITY: 0.92}),
    ("H02", "MET · antibody · LUAD",
     {Axis.TARGET: 0.70, Axis.TISSUE: 0.65, Axis.SAFETY: 0.72, Axis.TRACTABILITY: 0.60}),
    ("H03", "KRAS · small_molecule · LUAD · G12C",
     {Axis.TARGET: 0.88, Axis.TISSUE: 0.50, Axis.SAFETY: 0.45, Axis.TRACTABILITY: 0.80}),
]


def _demo_cards() -> list[HypothesisCard]:
    cards = []
    for hid, label, axes in _DEMO_CARDS:
        c = HypothesisCard(hypothesis_id=hid, label=label)
        for axis, val in axes.items():
            c.put(Evidence(axis=axis, value=val, confidence=0.7,
                           cost=CostTier.LOOKUP, data_origin="demo-fixture"))
        cards.append(c)
    return cards


def run_demo() -> dict:
    """Offline end-to-end: reviewer audit → arena Pareto + tournament → ranking."""
    print("┌─ virtual-biotech SCIENTIST · arena loop (demo, no keys)")
    cards = _demo_cards()

    # 1. Scientific Reviewer audit (structural gap check is real).
    verdict = reviewer.review(cards, max_reroutes=1)
    print(f"│  reviewer: {verdict.verdict}"
          + (f"  (gap: {verdict.reroutes[0].axis.value})" if verdict.reroutes else ""))

    # 2. Arena — Pareto fronts (weight-free primary view).
    fronts = pareto.fronts(cards)
    print(f"│  arena Pareto: {len(fronts)} front(s); "
          f"front-1 = {[c.hypothesis_id for c in fronts[0]]}")

    # 3. Arena — pairwise tournament (Elo live board + Bradley–Terry final).
    ids = [c.hypothesis_id for c in cards]
    board = EloBoard(ids)
    by_id = {c.hypothesis_id: c for c in cards}
    results = []
    for a, b in schedule(ids):
        res = judge_match(by_id[a], by_id[b])  # offline placeholder judge
        board.update(res)
        results.append(res)
    bt = bradley_terry(ids, results)

    # 4. Final ranking for the eval harness (Pareto front, scalarised tie-break).
    ranking = pareto.rank(cards)
    print(f"│  Elo board:  {[f'{i}:{r:.0f}' for i, r in board.leaderboard()]}")
    print(f"│  ranking →   {ranking}")
    print("└─ demo complete")
    return {
        "mode": "demo",
        "ranking": ranking,
        "pareto_fronts": [[c.hypothesis_id for c in fr] for fr in fronts],
        "elo": dict(board.leaderboard()),
        "bradley_terry": bt,
        "reviewer_verdict": verdict.verdict,
    }


def run_live(query: str, disease: str, backend: str = "auto") -> dict:
    """Live loop skeleton — brief → decompose → (divisions/ToolUniverse) → arena.

    TODO(A1): wire the division evidence-gathering (vbs/tooluniverse + adapters),
    the VoI loop dispatch (selector.run_loop with a real ``execute``), and
    run_experiment. Today it stands up the CSO + slate so the wiring points are
    explicit and the live path fails loudly instead of faking a result.
    """
    from ..runners import select_runner
    runner = select_runner(backend)
    cso = CSO(runner=runner)
    briefing = cso.brief(query, disease)
    plan = cso.decompose(briefing, targets=[])  # TODO: seed from tools.opentargets.candidates
    raise NotImplementedError(
        f"live evidence path not wired — framed {len(plan.slate.hypotheses)} hypotheses; "
        "divisions must now call ToolUniverse and emit Evidence, then selector.run_loop "
        "drives the VoI budget and the arena ranks. See TODO(A1)/B3/B5."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Virtual Biotech Scientist — arena loop.")
    ap.add_argument("--demo", action="store_true", help="offline end-to-end on synthetic cards (no keys)")
    ap.add_argument("--live", action="store_true", help="live loop (ToolUniverse + LLM agents)")
    ap.add_argument("--query", default="best target for lung cancer?")
    ap.add_argument("--disease", default="LUAD")
    ap.add_argument("--backend", default="auto")
    ap.add_argument("--json", action="store_true", help="print result as JSON")
    args = ap.parse_args()

    if args.live:
        result = run_live(args.query, args.disease, args.backend)
    else:
        result = run_demo()
    if args.json:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
