# Pareto Agent — Design Discussion

Open questions and tradeoffs behind `arena/pareto_agent/`. This is a discussion doc, not a
spec — decisions marked **(v1 choice)** are what's actually implemented; everything else is
an option we considered or deferred.

## 1. Quantitative vs. qualitative Pareto front

**Quantitative**: ask the LLM to assign each hypothesis a numeric score per axis, then compute
the Pareto front with plain arithmetic comparisons.

- **Pros:** easy to implement; cheap — one sweep over all hypotheses (`O(n)` LLM calls total).
- **Cons:** LLM scoring isn't calibrated across calls — it can be lenient on one hypothesis and
  strict on another with no shared reference point, so two hypotheses that are "obviously tied"
  can end up numerically separated for no principled reason. That noise then gets silently
  baked into a hard dominance cutoff.

**Qualitative (v1 choice)**: comparison-based — the LLM only ever answers "is A better, worse,
tied, or incomparable to B on this axis," never "what is A's score."

- **Pros:** sidesteps the calibration problem entirely — a pairwise judgement doesn't need a
  stable global scale, only local consistency between the two hypotheses in front of it.
- **Cons:** costly. See [§5 Cost model](#5-cost-model) below — this is the main reason
  question 3 (large front) matters.

Worth noting these aren't fully separate worlds: the axis *evidence entries* in each hypothesis
card already carry a numeric `value` (see `arena/build_hypotheses.py`), but that number is
precomputed deterministically from real Open Targets data, not assigned by the comparison LLM.
The LLM only reasons qualitatively *over* that evidence — it never recomputes or overrides the
number itself. So "qualitative" describes the judgement step, not a claim that no numbers exist
anywhere in the pipeline.

## 2. How to measure confidence of judgement?

1. **LLM self-reports a confidence label** (`high` / `medium` / `low`) alongside the relation —
   ad hoc, but free (same call). **(v1 choice)** — see `AxisComparison.confidence` in
   `models.py`.
2. **Vote and compute entropy as confidence** — sample the same comparison N times and treat
   disagreement as low confidence. Principled, but multiplies LLM cost by N and reintroduces the
   "repeated comparison" mechanism this first version deliberately excludes.
3. **Use confidence purely as provenance, not as logic** — this is what v1 actually does:
   `confidence` is stored on every axis comparison and surfaced in the domination graph for a
   human to audit, but it never gates the dominance computation itself. A `high`-confidence
   `A_better` and a `low`-confidence `A_better` currently count identically toward dominance.
4. **Confidence-gated dominance (deferred)** — a cheap middle ground between (1) and (2): treat
   a `low`-confidence `A_better`/`B_better` as if it were `insufficient_evidence` before running
   the aggregation rule. No extra LLM calls, but it does make the front stricter (more axes
   become "unresolved," so fewer dominance edges fire) — directly relevant to §3 below.

## 3. What if the Pareto front is too large after the first run? How do we propose the next
   move/experiment that most reduces uncertainty or maximizes information gain?

1. **LLM directly proposes a next step after seeing the first-round results** — ad hoc but
   cheap; no structural guarantee it's actually the highest-value action.

2. **A simple counting-based VoI score (concrete proposal).** Resolving an axis is only
   valuable if it could actually flip a decision. Every pairwise comparison already stored in
   the domination graph carries `unresolved_axes` and a `reason`
   (`insufficient_evidence` / `incomparable_axes` / `both_sides_have_advantages` — see
   `pareto.py::_build_comparison_summary`), so we don't need a new LLM call to define this, just
   an aggregation over data already produced. For each axis `a`:

   - `swing_pairs(a)` = the number of pairwise comparisons among current front members where
     `a` is the **sole** entry in `unresolved_axes`, and the comparison's `reason` is
     `insufficient_evidence` or `incomparable_axes` (**not** `both_sides_have_advantages`).
     That last condition matters: if the reason is `both_sides_have_advantages`, a real
     disagreement already exists on some *other* axis, so resolving `a` can't change that pair's
     outcome — it isn't a swing axis for it.
   - `cost(a)` = the axis's evidence `cost` tier, already present on every axis entry
     (1 = cheap lookup, 2 = synthesis, 3 = `run_experiment` — e.g. `right_tissue` is tier 3 in
     every fixture card, per `arena/build_hypotheses.py`).

   ```
   VoI(a) = swing_pairs(a) / cost(a)
   ```

   Recommend resolving whichever axis has the highest `VoI(a)` — the one that could unblock the
   most front-pairs per unit of experimental cost. `swing_pairs(a)` is a literal count of "how
   many current decisions actually depend on this unknown," and dividing by `cost(a)` is the
   "for how cheap" half of the ratio — a narrow but concrete formalization of value-of-
   information, not just a label for "seems important."

3. **Even simpler fallback**, if (2) is still more machinery than a first pass needs: skip the
   sole-blocker/`reason` filter and just tally raw frequency of each axis across *every*
   `unresolved_axes` list, divided by `cost`. Cheaper to compute, but overcounts axes that
   wouldn't actually change an outcome because a genuine tradeoff already exists elsewhere in
   that pair.


## 4. Incremental vs. batch Pareto construction

Not in the original discussion, but worth recording since it's a real design choice already
made: v1 builds the front **incrementally** (§3 of the spec) — each candidate is compared only
against the *current* front, not against every other survivor.

- **Pros:** cheap early exit. A candidate dominated by the first front member it meets is
  discarded immediately; we never pay for the remaining comparisons. In the best case (a strict
  total order) this is `O(n)` pairwise comparisons instead of `O(n^2)`.
- **Cons:** **input-order sensitive.** A hypothesis discarded early is never reconsidered, even
  if a later candidate would have made a *different* front member (which it never got to face)
  vulnerable. This is called out explicitly in `run_metadata.algorithm_note` at run time rather
  than silently assumed. The order-independent fix is a batch/all-pairs pass — compute every
  pairwise relation up front, then derive the front from the full domination graph — which is
  strictly correct but pays the full `O(n^2)` cost unconditionally, with no early-exit savings.

## 5. Cost model

Rough accounting, since "costly" in §1 deserves a number attached to it:

- Red-flag pass: `n` LLM calls (one per hypothesis, run concurrently).
- Each pairwise match: 6 LLM calls (one per axis, run concurrently via `asyncio.gather`).
- Incremental front construction: each candidate is compared against the *current* front only,
  so total pairwise matches range from `O(n)` (strict total order — every candidate resolves
  against the first incumbent it meets) to `O(n^2)` (nothing dominates anything, e.g. an
  antichain of genuine tradeoffs — every candidate is compared against every prior front
  member). Total LLM calls for the comparison stage: `6 x (pairwise matches)`, so worst case
  `~6n^2/2`.
- This is the direct tension with §3: a stricter dominance rule (more axes counted as
  unresolved) shrinks the front-pruning rate, which pushes the pairwise-match count toward the
  `O(n^2)` end of that range — the "large front" problem and the "costly" problem are the same
  knob, turned from opposite sides.

## 6. The conservatism tension

The dominance rule (`pareto.py::aggregate_axis_comparisons`) is deliberately strict: *any* axis
returning `incomparable` or `insufficient_evidence` blocks dominance outright, even if every
other axis agrees. That's the right default for a first version — it means a domination edge is
never asserted on shaky grounds — but it directly causes the §3 problem: the stricter the rule,
the more comparisons land in `tradeoff_or_unresolved`, and the larger the surviving front.

The two levers to relax this later are exactly the two deferred options above: confidence-gating
(§2.4) narrows evidence quality before the rule ever runs, while voting/repeated-comparison
(§2.2) would let the rule tolerate a *bounded* amount of disagreement instead of treating one
low-quality "incomparable" the same as five confident agreements. Both are correctly out of
scope for v1 (per the "no repeated comparison" constraint) but are the obvious next levers if
the front turns out too large in practice on a real hypothesis set.
