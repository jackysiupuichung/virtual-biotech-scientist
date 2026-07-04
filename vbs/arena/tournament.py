"""tournament.py — the pairwise, head-to-head ranking view (ARENA.md §3, §4).

The comparative leaderboard: each match is two hypothesis cards → an LLM-judge
panel of division judges → a winner + margin + rationale, recorded as a ``BEAT``
edge; ratings accumulate into a board. Elo drives the live demo animation;
Bradley–Terry gives the final, CI-bearing board (mirrors how AI Co-Scientist and
LMArena converged: Elo → Bradley–Terry).

Split by certainty:
  * **Elo update** and **Bradley–Terry MLE** — pure math, IMPLEMENTED.
  * **The judge** (who wins a given match) — SCAFFOLD: one LLM call per match via
    vbs.runners; order-swapped to kill position bias (ARENA.md §4).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .card import Axis, HypothesisCard


@dataclass
class MatchResult:
    """Outcome of one head-to-head, recorded as an auditable ``BEAT`` edge."""

    a_id: str
    b_id: str
    winner_id: str          # a_id or b_id (draws use score 0.5 via ``a_score``)
    a_score: float          # 1.0 a won · 0.0 b won · 0.5 draw
    margin: float = 0.0     # judge-reported confidence in the win, 0..1
    rationale: str = ""     # written justification (auditable)
    per_axis: dict[str, str] = field(default_factory=dict)  # axis → which side it favoured


# --------------------------------------------------------------------------- #
# Elo — IMPLEMENTED (live demo board)
# --------------------------------------------------------------------------- #

class EloBoard:
    """Incremental Elo ratings — the live, animatable leaderboard."""

    def __init__(self, ids: list[str], *, base: float = 1000.0, k: float = 32.0) -> None:
        self.rating = {i: base for i in ids}
        self.k = k

    def expected(self, a: str, b: str) -> float:
        return 1.0 / (1.0 + 10 ** ((self.rating[b] - self.rating[a]) / 400.0))

    def update(self, res: MatchResult) -> None:
        ea = self.expected(res.a_id, res.b_id)
        self.rating[res.a_id] += self.k * (res.a_score - ea)
        self.rating[res.b_id] += self.k * ((1.0 - res.a_score) - (1.0 - ea))

    def leaderboard(self) -> list[tuple[str, float]]:
        return sorted(self.rating.items(), key=lambda kv: kv[1], reverse=True)


# --------------------------------------------------------------------------- #
# Bradley–Terry — IMPLEMENTED (final CI-bearing board)
# --------------------------------------------------------------------------- #

def bradley_terry(ids: list[str], results: list[MatchResult],
                  iters: int = 200, tol: float = 1e-9) -> dict[str, float]:
    """Bradley–Terry strengths via MM iteration (Hunter 2004); normalised to sum 1.

    Strength β_i where P(i beats j) = β_i / (β_i + β_j). Draws count as half a win
    to each side. Deterministic, dependency-free; CIs (bootstrap over matches) are
    a TODO but the point estimate is exact.
    """
    if not ids:
        return {}
    beta = {i: 1.0 for i in ids}
    wins = {i: 0.0 for i in ids}
    pairs: dict[tuple[str, str], int] = {}
    for r in results:
        wins[r.a_id] += r.a_score
        wins[r.b_id] += 1.0 - r.a_score
        key = tuple(sorted((r.a_id, r.b_id)))
        pairs[key] = pairs.get(key, 0) + 1
    for _ in range(iters):
        new = {}
        for i in ids:
            denom = 0.0
            for (x, y), n in pairs.items():
                if i == x:
                    denom += n / (beta[i] + beta[y])
                elif i == y:
                    denom += n / (beta[i] + beta[x])
            new[i] = (wins[i] / denom) if denom > 0 else beta[i]
        s = sum(new.values()) or 1.0
        new = {i: v / s for i, v in new.items()}
        if max(abs(new[i] - beta[i]) for i in ids) < tol:
            beta = new
            break
        beta = new
    return beta


# --------------------------------------------------------------------------- #
# The judge — SCAFFOLD (LLM-as-judge panel)
# --------------------------------------------------------------------------- #

def judge_match(a: HypothesisCard, b: HypothesisCard, *, runner=None,
                axes: list[Axis] | None = None) -> MatchResult:
    """Decide one head-to-head via a panel of division judges (ARENA.md §4).

    TODO(B1c): build the panel — one judge per axis-area, each arguing from that
    axis's Evidence; run order-swapped (a,b) and (b,a) to cancel position bias;
    use a cheap single-turn compare for lopsided pairs and multi-turn debate only
    for close, rank-decisive pairs (Successive-Halving). ``runner`` is a
    vbs.runners.Runner; the prompt lives beside vbs/cso/prompts/reviewer.md.

    Placeholder (no runner): deterministic scalarised comparison so the tournament
    plumbing (EloBoard, bradley_terry) runs end-to-end in the offline demo.
    """
    order = axes or Axis.ranking_axes()
    if runner is None:
        from .pareto import scalarise
        sa, sb = scalarise(a, axes=order), scalarise(b, axes=order)
        a_score = 1.0 if sa > sb else 0.0 if sa < sb else 0.5
        return MatchResult(
            a_id=a.hypothesis_id, b_id=b.hypothesis_id,
            winner_id=a.hypothesis_id if a_score >= 0.5 else b.hypothesis_id,
            a_score=a_score, margin=abs(sa - sb),
            rationale="offline placeholder: weighted-sum comparison (no judge LLM)",
        )
    raise NotImplementedError("LLM judge panel not yet wired — see TODO(B1c)")
