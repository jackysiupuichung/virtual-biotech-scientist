# Potential directions

Where this project can go beyond a weekend prototype. Ordered roughly from "buildable at the
event" to "ambitious roadmap." The core deliverable is the [arena](ARENA.md); these extend it.

## Near-term (event-buildable)

1. **Demonstrate non-obvious ranking.** ToolUniverse's case study lands on HMGCR (statins) — the
   textbook answer, chosen by a human. A compelling demo shows the arena ranking competing
   hypotheses and surfacing a *defensible, less-obvious* lead, with the Pareto front + match
   rationales explaining why.
2. **Show the ranking change as evidence arrives.** Reveal an expensive axis (e.g. single-cell
   specificity) for a boundary hypothesis and watch the leaderboard / Pareto front visibly re-sort.
   The *update* is the demo.
3. **Auditable provenance.** Every card value and every match verdict links to the tool/evidence
   behind it — a trust feature and a judge-legible artifact.

## Medium-term

4. **The compute-budgeted VoI loop (ARENA §5).** Promote the stretch goal: boundary-focused match
   selection + a marginal-information stopping rule, so the system spends compute like a scientist
   rather than running a static round-robin.
5. **Evolving hypotheses** ([self-improving level B](SELF_IMPROVING.md#level-b--self-improving-hypotheses-the-strongest-new-angle-build-a-slice)).
   Don't just rank a fixed slate — *mutate* losing hypotheses (swap modality, narrow the patient
   stratum) and re-enter them, keeping a **diverse** front (quality-diversity / MAP-Elites style)
   rather than collapsing to one idea.
6. **Close the loop with experiments.** Add the experiment-design + readout step from
   [DESIGN.md §4](DESIGN.md#4-closing-the-loop-with-experiments-future-direction): design the next
   decisive test for the leading hypotheses, obtain a readout (simulated oracle / Boltz-2 / ADMET-AI
   / projected dataset), feed it back, and re-rank.
7. **Portfolio decisions under budget.** Given a fixed experiment budget, which *sequence* of tests
   de-risks the whole portfolio fastest — ranking as resource allocation, not a one-shot sort.

## Ambitious / roadmap

8. **Close the loop with real assays.** Connect the readout interface to real experimental data —
   public assay results, collaborators' datasets, or lab-automation/CRO APIs — so the agent's
   hypotheses are tested against reality, not only in silico.
9. **Multi-disease / multi-modality.** Generalise the axis set and modality assumptions (small
   molecule, biologic, etc.) so the same arena runs across indications.
10. **Self-improving tool use** ([self-improving level C](SELF_IMPROVING.md#level-c--self-improving-toolkit-one-scripted-instance)).
    Lean on ToolUniverse's tool-composition / spec-optimisation to let the agent build or refine tools
    it lacks for a given axis, rather than being limited to the pre-wired set.
11. **Self-improving judgement** ([self-improving level D](SELF_IMPROVING.md#level-d--self-improving-judgement-honest-roadmap-do-not-claim)).
    Calibrate the arena's axis weights and judge against real clinical-trial-success outcomes — the
    one form of self-improvement that needs ground truth we don't have at the event.

## Open questions to pressure-test

- In a multi-objective ranking, when do we report the **Pareto set** vs. commit to a single winner —
  and how are scalarisation weights kept honest (and defensible to a domain expert)?
- When should the loop **stop** — confidence threshold, budget exhaustion, or a clear lead — and how
  do we avoid premature convergence on an obvious answer?
- How do we calibrate in-silico predictions used *as* readouts so the loop doesn't over-trust them?
