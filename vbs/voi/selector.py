"""selector.py — the compute-budgeted Value-of-Information loop (ARENA.md §5, INFORMATION_MAXIMISATION.md).

The "AI scientist" part. Don't gather all evidence or run all matches up front —
spend the next unit of compute where it most changes the ranking. One policy over
one global decision (best allocation of the remaining budget across the portfolio),
formalised as budget-constrained sequential experimental design:

    budget = B
    init each hypothesis from cheap retrieved axes only
    while budget > 0:
        a* = argmax_a  netEVPI(a)          # a ∈ {resolve an axis, run a match, run_experiment, mutate}
        if netEVPI(a*) < 0: break          # nothing left worth its cost → STOP
        execute(a*); budget -= cost(a*); re-rank

Migration note (A5): the *skeleton* here — a hard budget gate, candidate actions
ranked by expected value, a no-thrash "never re-pull a depleted arm" rule, and a
stop condition — is ported from virtual-biotech-agents' harness info-max loop
(token-budget greedy). The UPGRADE (B3) is replacing token-greedy with proper
netEVPI (info value − cost) using the CostTier from arena/card.py.

Status: budget loop + action enumeration + no-thrash guard IMPLEMENTED;
``expected_information`` (the EVPI estimate) is a SCAFFOLD placeholder to fill.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..arena.card import Axis, CostTier, HypothesisCard

DEFAULT_BUDGET = 30  # in cost-tier units (tiers are 1/2/3 — jcaky's convention)


class ActionKind(str, Enum):
    RESOLVE_AXIS = "resolve_axis"   # gather/compute one axis's Evidence for one hypothesis
    RUN_MATCH = "run_match"         # play one head-to-head to sharpen the tournament
    RUN_EXPERIMENT = "run_experiment"  # tier-3 computation via experiments/interface.py
    MUTATE = "mutate"               # evolve a losing hypothesis (arena/mutate.py)


@dataclass
class Action:
    """One candidate move the policy can spend budget on."""

    kind: ActionKind
    cost: CostTier
    hypothesis_id: str | None = None
    axis: Axis | None = None
    pair: tuple[str, str] | None = None  # for RUN_MATCH
    meta: dict = field(default_factory=dict)

    def key(self) -> tuple:
        """Identity for the no-thrash 'executed' set — same key ⇒ zero new info."""
        return (self.kind.value, self.hypothesis_id, self.axis.value if self.axis else None,
                self.pair)


def enumerate_actions(cards: list[HypothesisCard]) -> list[Action]:
    """All moves currently available: every missing axis on every card, plus matches.

    TODO(B3): also emit RUN_EXPERIMENT actions (for axes whose resolution needs
    tier-3 computation) and MUTATE actions (for current losers). Cost per axis
    should come from the skill registry, not a flat LOOKUP default.
    """
    actions: list[Action] = []
    for c in cards:
        for axis in c.missing_axes():
            actions.append(Action(ActionKind.RESOLVE_AXIS, CostTier.LOOKUP,
                                   hypothesis_id=c.hypothesis_id, axis=axis))
    return actions


def expected_information(action: Action, cards: list[HypothesisCard]) -> float:
    """EVPI estimate: how much resolving ``action`` would change the budget decision.

    TODO(B3) — THE CORE. Estimate the probability that this action's result flips a
    rank / the top-k front, weighted by how much it would move it. Concretely:
    higher for axes on cards near the decision boundary and with low current
    ``confidence``; ~0 for a clear leader or a clear reject (so an expensive
    experiment on a mid-pack hypothesis scores low EVPI − high cost → negative
    netEVPI → never selected; selectivity emerges from the math, not a hand rule).

    Placeholder: uncertainty proxy = mean (1 − confidence) over the card's present
    axes, so the loop demonstrably prefers the least-resolved hypotheses.
    """
    card = next((c for c in cards if c.hypothesis_id == action.hypothesis_id), None)
    if card is None or not card.axes:
        return 1.0  # nothing known → maximally informative to learn anything
    return sum(1.0 - ev.confidence for ev in card.axes.values()) / len(card.axes)


def net_evpi(action: Action, cards: list[HypothesisCard]) -> float:
    """Expected information value minus cost — the single yardstick all actions share.

    Info value is scaled up so a tier-1 lookup with real information beats a tier-3
    experiment with none; the exact scale is a knob to calibrate in B3.
    """
    return expected_information(action, cards) * 100.0 - int(action.cost)


@dataclass
class VoIResult:
    executed: list[Action] = field(default_factory=list)
    spent: int = 0
    stopped_reason: str = ""


def run_loop(cards: list[HypothesisCard], execute, *, budget: int = DEFAULT_BUDGET) -> VoIResult:
    """Drive the budgeted VoI loop; ``execute(action)`` mutates cards in place.

    ``execute`` is the caller's dispatcher (resolve an axis via a skill / ToolUniverse,
    run a match, run_experiment, or mutate) — the selector stays agnostic to *how*
    an action is carried out, only *which* to pick. IMPLEMENTED: budget gate,
    greedy argmax(netEVPI), no-thrash executed-set, negative-netEVPI stop.
    """
    res = VoIResult()
    executed_keys: set[tuple] = set()
    while res.spent < budget:
        actions = [a for a in enumerate_actions(cards) if a.key() not in executed_keys]
        if not actions:
            res.stopped_reason = "no actions left"
            break
        best = max(actions, key=lambda a: net_evpi(a, cards))
        if net_evpi(best, cards) < 0:
            res.stopped_reason = "netEVPI < 0 — nothing worth its cost"
            break
        if res.spent + int(best.cost) > budget:
            res.stopped_reason = "next action exceeds budget"
            break
        execute(best)                       # caller resolves the axis / match / experiment
        executed_keys.add(best.key())       # no-thrash: never re-pull a depleted arm
        res.executed.append(best)
        res.spent += int(best.cost)
    else:
        res.stopped_reason = res.stopped_reason or "budget exhausted"
    return res
