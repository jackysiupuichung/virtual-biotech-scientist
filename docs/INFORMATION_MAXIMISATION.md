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

## The actions span a cost spectrum (not separate stages)

VoI chooses among action types that differ in cost and in which decision they move:

1. **Cheap retrieval** — "for B7-H3→ADC→LUAD, which lookup axis to resolve next?" (Open Targets,
   literature). Mostly sharpens the *ranking*.
2. **Expensive functional experiment** — "run Boltz-2 / single-cell on *which* candidate?" Mostly
   resolves a *commit-or-kill* (go/no-go) on a strong hypothesis.
3. **Generative** — "create or mutate a hypothesis?" ties to
   [self-improving level B](SELF_IMPROVING.md#level-b--self-improving-hypotheses-the-strongest-new-angle-build-a-slice).

## These are one loop, not separate stages

A tempting design is to split this into tiers — cheap "ranking VoI" vs. expensive "validation VoI".
**Don't.** They are the *same* policy. The field already has the unifying object: **Expected Value of
(Partial) Perfect Information** — EVPPI — which simultaneously answers *which parameter (target/axis)
most contributes to decision uncertainty* (that **is** prioritisation) and *whether resolving it beats
its cost* (that **is** the experiment-selection). Prioritisation isn't *served by* VoI; **prioritisation
is VoI.**

The decision the policy optimises is **not** "who ranks #3 vs #4" — that has no payoff. It is **one
global decision: the best allocation of the remaining budget across the whole portfolio**, formalised
as a budget-constrained **sequential experimental design** (a POMDP whose state is the portfolio's
beliefs, whose actions are the experiments, whose utility is information-per-cost). There is no fixed
top-k cutoff; the **budget constraint** plays that role.

```
ONE policy.  state = portfolio beliefs.  pick argmax  NET EVPI  =  (info value − cost):

cheap ──────────────────────────────────────────────► expensive
Open Targets   literature    single-cell        Boltz-2 functional
lookup         search        specificity        validation
│                                                │
mostly moves the RANKING        mostly resolves a COMMIT/KILL
        act → re-rank → repeat until budget spent or net EVPI < 0
```

**The tiers dissolve into the cost term.** A Boltz-2 run on a mid-pack hypothesis has low EVPI (it
won't change the allocation) minus high cost → **negative net EVPI → never selected.** Expensive
functional experiments fire *only* on candidates where they'd change the budget decision — selectivity
**emerges from the math**, not a hand-coded rule.

**Why this framing:**
- It prevents waste — net EVPI is the gate; nothing is computed that can't change the decision.
- It's demo-legible — "the system decides B7-H3's specificity is the one experiment worth running,
  runs it, the board re-sorts" is one clean story.
- It matches the Genentech quote exactly: *"each experimental cycle is maximally informative…
  prioritising the synthesis and testing of molecules that offer the highest learning gain."*
- It respects the field's **prioritisation-vs-validation distinction** (see
  [DRUG_DISCOVERY_PRIMER.md](DRUG_DISCOVERY_PRIMER.md#prioritisation-vs-validation)) — different cost,
  evidence type, and decision stakes — while unifying the *mechanism*.

## One-liner

> *We don't collect evidence and then rank. We rank continuously, and collect only the evidence that
> could change the ranking — the same value-of-information policy that runs clinical trials, A/B tests,
> and Genentech's lab-in-the-loop.*
