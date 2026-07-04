"""scheduler.py — which matches to play (ARENA.md §4).

Schedule format by field size: round-robin for n ≤ 10 (all pairs), Swiss for
n = 12–15 (don't run all pairs when n is large). The VoI loop (voi/selector.py)
overrides "which match next" for the *adaptive* run — play the pair nearest the
decision boundary, not at random — but a static schedule is the fallback and the
baseline.

  * **Round-robin** — IMPLEMENTED (trivial, load-bearing for n ≤ 10).
  * **Swiss pairing** — SCAFFOLD (pair equal-score players each round).
"""
from __future__ import annotations

from .tournament import MatchResult


def round_robin(ids: list[str]) -> list[tuple[str, str]]:
    """All unordered pairs — the n ≤ 10 schedule. O(n²) matches."""
    return [(ids[i], ids[j]) for i in range(len(ids)) for j in range(i + 1, len(ids))]


def swiss_round(ids: list[str], results: list[MatchResult]) -> list[tuple[str, str]]:
    """One Swiss round: pair players on equal running scores (ARENA.md §4).

    TODO(B1d): compute each id's running win-count from ``results``, sort, and pair
    adjacent unpaired players (standard Swiss), avoiding rematches. Used for
    n = 12–15 so match count stays ~n·rounds instead of n². For now returns a
    single round of adjacent pairs by current score so the plumbing runs.
    """
    score: dict[str, float] = {i: 0.0 for i in ids}
    for r in results:
        score[r.a_id] = score.get(r.a_id, 0.0) + r.a_score
        score[r.b_id] = score.get(r.b_id, 0.0) + (1.0 - r.a_score)
    ordered = sorted(ids, key=lambda i: score.get(i, 0.0), reverse=True)
    return [(ordered[i], ordered[i + 1]) for i in range(0, len(ordered) - 1, 2)]


def schedule(ids: list[str], results: list[MatchResult] | None = None) -> list[tuple[str, str]]:
    """Pick the schedule by field size (ARENA.md §4)."""
    if len(ids) <= 10:
        return round_robin(ids)
    return swiss_round(ids, results or [])
