# Where information-maximisation lives

A design note on a question that looks like a binary but isn't: should the
information-maximisation drive **evidence-collection for a target–disease pair**, or **ranking**?

## The binary is false — they're two layers of one loop

You only collect evidence *because* it might change the ranking. **Ranking defines what "informative"
means; evidence-collection is how you buy information.** Neither works alone:

- Evidence-collection *alone* (gather everything for every target) is the open-loop behaviour we are
  differentiating *against* — it's exactly what ToolUniverse's case study does before deferring to a human.
- Ranking *alone* (sort what you happen to have) never improves.

The connecting rule is **Value of Information**: spend the next unit of compute on the action whose
result would most change *which hypothesis wins*.

## The same pattern across domains

Every field that does sequential decisions solved this identically. The columns are the same shape:

| Domain | The "ranking" question (what info is *for*) | The "collect" action (how to buy info) | Connecting rule |
| --- | --- | --- | --- |
| **Clinical trials** | which drug arm is best? | enrol the next patient into which arm? | enrol where it most resolves *which arm wins* |
| **A/B testing** | which variant converts best? | show the next user which variant? | bandit: sample the uncertain, rank-decisive variant |
| **Chess / Elo (LMArena)** | who is strongest? | schedule which match? | pair *close* ratings; a blowout teaches nothing |
| **AutoML / Hyperband** | which config is best? | spend the next GPU-hour on which config? | kill the worst half early; escalate to survivors |
| **Active learning (Genentech lab-in-the-loop)** | which molecule to synthesise? | run the next assay on which molecule? | test the **highest learning-gain** molecule |
| **Our arena** | which (target × disease × modality) wins? | `run_experiment` on which (hypothesis, axis)? | resolve the axis whose result could **flip a rank** |

The information-maximisation is never "in collection" *or* "in ranking" — it is a **policy that uses
the ranking's uncertainty to choose the next collection action.**

## The real decision: at what granularity does VoI act?

Three levels — and *this* is the actual choice:

1. **Within one hypothesis (evidence level)** — "for B7-H3→ADC→LUAD, which axis to resolve next?"
   This is the *target–disease-pair evidence-gathering* framing.
2. **Across hypotheses (ranking level)** — "which match, or which hypothesis's missing axis, most
   sharpens *the leaderboard*?"
3. **Generative (which hypothesis to create at all)** — Bayesian-optimisation territory; ties to
   [self-improving level B](SELF_IMPROVING.md#level-b--self-improving-hypotheses-the-strongest-new-angle-build-a-slice).

## Recommendation: operate at level 2; level 1 falls out for free

Make **ranking** the objective; evidence-collection becomes the *mechanism*, not a separate place:

```
objective:  reduce uncertainty about WHO WINS (the ranking)
                    │
   VoI scores every candidate action by EIG / cost:
   ┌──────────────────┬──────────────────────┬─────────────────────┐
 "collect axis X       "run match (Hi, Hj)"    "create / mutate
  for hypothesis H"                              a hypothesis"
   └──────────────────┴──────────────────────┴─────────────────────┘
        pick argmax  →  act (maybe run_experiment)  →  re-rank  →  repeat
```

Evidence-collection and matchmaking are just **action types in one VoI argmax**, judged by the same
yardstick: *does this change the ranking?* You compute B7-H3's expensive specificity score **only if
its score-interval overlaps a rival's** (could reorder the board); if it's clearly #1 or clearly last,
you skip it and spend the call elsewhere.

**Why level 2:**
- It's the only framing that prevents waste — selectivity is the whole point.
- It's demo-legible — "the system decides B7-H3's specificity is the one experiment worth running,
  runs it, leaderboard re-sorts" is one clean story.
- It matches the Genentech quote exactly: *"each experimental cycle is maximally informative…
  prioritising the synthesis and testing of molecules that offer the highest learning gain."* Their
  "learning gain" is defined relative to a downstream decision — same as ranking here.

## One-liner

> *We don't collect evidence and then rank. We rank continuously, and collect only the evidence that
> could change the ranking — the same value-of-information policy that runs clinical trials, A/B tests,
> and Genentech's lab-in-the-loop.*
