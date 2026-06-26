# Potential directions

Where this project can go beyond a weekend prototype. Ordered roughly from "buildable at the
event" to "ambitious roadmap." Each is framed around the project's core thesis: a virtual biotech
is a **closed loop** that prioritises under uncertainty and refines from data.

## Near-term (event-buildable)

1. **Demonstrate non-obvious prioritisation.** The reference case study lands on HMGCR (statins) —
   the textbook answer, chosen by a human. A compelling demo shows our scorer ranking a candidate
   set and surfacing a *defensible, less-obvious* lead, with the comparison matrix explaining why.
2. **Show the loop changing its mind.** Run one refinement cycle live: critic flags a weak axis →
   experiment-design requests a readout → the ranking visibly updates. The *update* is the demo.
3. **Auditable decision log.** Every ranking claim links to the tool call and evidence behind it.
   This is both a trust feature and a judge-legible artifact.

## Medium-term

4. **Portfolio decisions under budget.** Move from "rank N targets" to "given a fixed experiment
   budget, which sequence of tests maximises information / de-risks the portfolio fastest?" — i.e.
   the loop as a **resource-allocation** problem, not just a ranking.
5. **Active learning over readouts.** Use the experiment-design agent to pick the *most informative*
   next test (expected information gain), not just the next obvious one — turning the loop into a
   proper experimental-design strategy.
6. **Richer readout adapters.** Make the pluggable readout swap cleanly between simulated oracle,
   Boltz-2/ADMET-AI predictions, and projected datasets, with calibrated confidence so the
   re-ranking is principled rather than ad hoc.

## Ambitious / roadmap

7. **Close the loop with real assays.** Connect the readout interface to real experimental data —
   public assay results, collaborators' datasets, or lab-automation/CRO APIs — so the agent's
   hypotheses are tested against reality, not only in silico.
8. **Multi-disease / multi-modality.** Generalise the axis set and modality assumptions (small
   molecule, biologic, etc.) so the same loop runs across indications.
9. **Self-improving tool use.** Lean on ToolUniverse's tool-composition / spec-optimisation to let
   the agent build or refine tools it lacks for a given axis, rather than being limited to the
   pre-wired set.

## Open questions to pressure-test

- How do we keep the scorer's weights honest (and defensible to a domain expert) rather than
  arbitrary?
- When should the loop **stop** — confidence threshold, budget exhaustion, or a clear lead — and how
  do we avoid premature convergence on an obvious answer?
- How do we calibrate in-silico predictions used *as* readouts so the loop doesn't over-trust them?
