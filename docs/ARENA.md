# The Prioritisation Arena

The arena is this project's core contribution and the main thing we build at the event. It is
deliberately **small and fast to build** — a standalone ranking harness over the evidence the
scientist divisions produce.

> **One-line framing.** The *Virtual Biotech* paper assesses each therapeutic hypothesis **in
> isolation** and weighs the evidence narratively. We instead make hypotheses **compete head-to-head**
> and rank them as a **multi-objective optimisation**. Same evidence, but a quantified, reproducible,
> auditable ranking instead of a single narrative verdict.

---

## 1. What competes: the therapeutic hypothesis

The "player" is **not a bare gene** — it is a fully-framed hypothesis:

```
target × disease × modality × mechanism/direction × patient stratum
e.g. "B7-H3, antagonised via an ADC, in LUAD, exploiting stromal overexpression,
      with a selection biomarker for high-antigen patients."
```

This is exactly what the paper *outputs* (B7-H3→ADC; OSMRβ→mAb) and what an arena can meaningfully
compare. Scope for a hackathon: **5–15 candidate hypotheses per disease.**

Each hypothesis carries a **card**: its score + confidence on each evidence axis, with every value
traceable to the division/tool that produced it.

## 2. The axes (objectives)

Hypotheses are scored on multiple, **competing** objectives — these come from the scientist
divisions (see [DESIGN.md](DESIGN.md)). No single number; that's the point of multi-objective.

| Objective | Question | Division / evidence |
| --- | --- | --- |
| **Genetic / causal support** | Does genetics implicate the target? | Target ID (Open Targets associations) |
| **Disease-cell localisation** | Is the antigen on the disease/malignant cells (not just stroma)? | Target ID (single-cell / specificity) |
| **Tractability** | Can it be drugged with the chosen modality? | Modality (Open Targets tractability, structure) |
| **Safety / off-target** | Expression specificity, essentiality, known liabilities? | Target Safety (OT factors, ADMET) |
| **Novelty / differentiation** | Crowded space or whitespace? | Disease biology / literature |
| **Clinical precedent** | Prior trials, modality precedent? | Clinical |

> Axes are configurable per disease. Some are cheap (one API call); some are expensive (compute a
> single-cell specificity score). This cost asymmetry drives the compute loop (§5).

## 3. Multi-objective ranking — a few options

Because the objectives genuinely **trade off** (a target can be highly specific but poorly tractable),
the honest model is **multi-objective optimisation**, not a single weighted sum. We treat the choice
of aggregation as a design knob and will likely show more than one view:

| Option | How it ranks | Pros / cons |
| --- | --- | --- |
| **Pareto fronts** *(primary view)* | A hypothesis is on the front if nothing beats it on *all* axes. Front 1 = the non-dominated set; peel for fronts 2, 3… | Honest about trade-offs; no arbitrary weights. But gives a *set*, not a single winner — pair with one of the below to order within a front. |
| **Weighted scalarisation** | Combine axes with explicit weights → one score. | Simple, single ranking; weights are a defensible judgement the CSO states. Hides trade-offs if used alone. |
| **Pairwise tournament (Elo / Bradley–Terry)** | Each match is a head-to-head; a panel judges; ratings accumulate into a leaderboard. | Directly comparative, great for a live demo; Bradley–Terry gives confidence intervals. Needs a match schedule + judge. |
| **Hypervolume / ε-constraint** | Score by dominated hypervolume, or fix floors on some axes and optimise the rest. | Principled MOO; more machinery than a hackathon needs — list as a direction. |

**Recommended combination:** compute the **Pareto fronts** as the primary, weight-free view, and
within/over them run a **pairwise tournament** (Elo live for the demo animation; Bradley–Terry for the
final, CI-bearing board). This mirrors how AI Co-Scientist and LMArena converged (Elo → Bradley–Terry).

## 4. Match format & judging (for the tournament view)

- **Schedule:** round-robin for n ≤ 10; Swiss for n = 12–15 (don't run all pairs if n is large).
- **A match** = two hypothesis cards → an **LLM-judge panel** of *division judges* (one per axis-area),
  each arguing from its evidence; order-swapped to kill position bias.
- **Cost control:** cheap **single-turn** comparison for lopsided pairs; **multi-turn debate** only for
  close, rank-decisive pairs (Successive-Halving style).
- **Output of a match:** a winner + margin + a written rationale (auditable), recorded as a `BEAT` edge.

## 5. Compute-budgeted loop (the "AI scientist" part)

Don't gather all evidence or run all matches up front. Spend the next unit of compute where it most
changes the ranking — **Value of Information**:

The decision the policy optimises is **one global thing — the best allocation of the remaining budget
across the portfolio** (a budget-constrained sequential experimental design / POMDP), not any single
pairwise rank. Actions are scored by **net Expected Value of Perfect Information** — `info value − cost`
— so cheap lookups and expensive functional experiments compete on one yardstick. See
[INFORMATION_MAXIMISATION.md](INFORMATION_MAXIMISATION.md) for why prioritisation *is* VoI.

```
budget = B
init each hypothesis from cheap retrieved axes only
while budget > 0:
    a* = argmax_a  netEVPI(a)            # a ∈ {compute an axis, run a match, run_experiment, mutate a hypothesis}
                                         #   netEVPI = expected info value toward the budget decision − cost(a)
    if netEVPI(a*) < 0: break            # nothing left worth its cost → STOP
    execute(a*); budget -= cost(a*); re-rank
```

Concretely: an expensive experiment fires **only when its result could change the budget allocation**
(it won't, for a hypothesis that's clearly a leader or clearly out — so it's skipped, and the cost term
makes that automatic); run the next **match** on the pair nearest the decision boundary, not at random;
**stop** when the top-k fronts/ratings separate. This is the deliberate version of Co-Scientist's "Elo
plateau," and it's what turns a static tournament into an adaptive scientist. (Full technique survey
lives in the prior repo's `agentic-hypothesis-optimization.md`.)

### 5.1 The most-informative action may be an *experiment*

When the action the VoI selector picks is "resolve axis X for hypothesis H," and that axis requires
**new computation** rather than a cached lookup, it is dispatched through the **MCP experiment
interface** — a single `run_experiment(hypothesis, axis)` call with a **pluggable backend**:

```
VoI: most-informative = resolve(specificity? affinity?) for H
        │
        ▼  MCP: run_experiment(H, axis)
  ┌──────────────┬──────────────────────┬─────────────────────┐
  ▼              ▼                       ▼                     ▼
Boltz-2       single-cell            DNA/RNA LM            (cache /
binding       on real atlas         (Evo / Nucleotide      simulated
affinity      (CELLxGENE)           Transformer)           oracle)
(LIVE)        (stub)                (stub)
        │  real result → update H's card → re-rank
        ▼
```

This is the project's headline differentiator (see [DIFFERENTIATION.md](DIFFERENTIATION.md)): the loop
doesn't just rank on existing evidence, it **runs a frontier-model computation on real data as the
"experiment"** and re-ranks on the result. Backends are interchangeable behind one interface; for the
demo **Boltz-2 is live** (with pre-computed/cached results as a stage-safe fallback), single-cell and
DNA/RNA-LM are registered stubs.

## 6. Build scope for the event

Minimal viable arena (a day, not a weekend):

1. **Hypothesis cards** — a small schema; populate from division outputs (or fixtures for the demo).
2. **Pareto sort** — pure function over the cards; deterministic, ~no dependencies.
3. **Pairwise judge** — one Claude call per match returning winner + rationale; Elo accumulation.
4. **Leaderboard UI** — Streamlit: live Elo animation + Pareto-front view + per-claim provenance.
5. **(stretch) VoI loop** — boundary-focused match selection + a stopping rule.

Steps 1–4 are the demo. Step 5 is the "this is a real AI scientist, not a static ranker" upgrade.

## 7. Why this is a genuine contribution (not a re-implementation)

The paper integrates multi-scale evidence beautifully but renders **every verdict on one hypothesis
in isolation** — there is no comparison and no reproducible ranking. ToolUniverse's case study defers
the final pick to a human. The arena converts that qualitative, single-hypothesis step into a
**quantified, reproducible, multi-objective ranking with provenance** — and spends compute adaptively
to get there. That is the methodological delta, and it's demo-friendly.
