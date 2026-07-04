# Prior Art: Rank-First vs. Dominance-First Pareto Front Construction

**Scope.** Is the construction *"rank all items to a total order on each axis independently, then
compute the Pareto front on the resulting rank vectors"* (**rank-first**) already established —
(a) as a general MCDA / multi-objective-optimization technique, and (b) specifically in LLM-based or
computational drug-target prioritization? The contrast is **dominance-first**: computing Pareto
dominance directly from noisy per-pair, per-axis qualitative comparisons, without ever building a
per-axis total order (the approach in `comparison_based_multi_agent_pareto_system.md`).

**Method.** Deep-research pass, 2026-07-04: fan-out web search → source fetch → 3-vote adversarial
verification per claim (2/3 refutes kills a claim). ~97 agents, primary sources fetched and quoted
verbatim where possible. Verdicts below are the **verified** claims; refuted over-claims are noted.

> **Headline.** The rank-first construction is **not novel** — it is a named MCDA/MOO primitive
> *and* it has **already been published in LLM drug-target prioritization by the AD-Pareto paper**,
> which is a far closer neighbor than previously recorded. AD-Pareto does essentially the exact
> "per-axis pairwise ranking → Pareto front" pipeline we were considering as our improvement.

---

## 1. The two constructions

| | **Dominance-first** (current doc) | **Rank-first** (the alternative) |
|---|---|---|
| Unit of judgment | local `A_better/tie/incomparable/insufficient` per pair × axis | a per-axis **total ranking** of all items |
| Dominance computed on | scattered pairwise relations | **rank vectors** |
| Comparability | gaps allowed → block dominance | every cell filled → always comparable |
| Front size | bloats | tighter — but still bloats (see §3) |
| Order-sensitivity | yes (incremental front) | no (global per-axis ranking) |
| Reintroduces scoring? | no | a total order per axis (comparison-derived, so not absolute scoring) |

---

## 2. Q1 — Is rank-first a known MCDA/MOO primitive? **YES — established, multiple named forms.**

The verification pass confirmed several independent, primary-sourced instances. This is a
well-trodden operations-research idea, not novel in the abstract.

- **Ranking-dominance (Kukkonen & Lampinen, IEEE CEC 2007, "Ranking-Dominance and Many-Objective
  Optimization," pp. 3983–3990, DOI 10.1109/CEC.2007.4424990)** — *[verified, high confidence]*. The
  canonical named primitive: "based on **ranking a set of solutions according to each separate
  objective** and an aggregation function to calculate a scalar fitness value." Explicitly motivated
  to **"tackle the curse of dimensionality"** and to **"sort a set of solutions even for a large
  number of objectives when the Pareto-dominance relation cannot distinguish solutions from one
  another anymore."** This is exactly the front-bloat problem, addressed exactly by rank-first.
  > Caveat surfaced by verification: strict ranking-dominance ranks per objective and then
  > *aggregates to a scalar*, so it is not identical to "Pareto-on-rank-vectors." The rank-per-axis
  > step is the shared, established idea; whether you then dominate on the rank vector or scalarize
  > is a design choice.

- **COPA (arXiv:2503.14321, Javaloy/Vergari/Valera, "Comparing the Incomparable in Multi-Objective
  Model Evaluation")** — *[verified, high]*. Replaces each raw criterion with its **empirical-CDF /
  probability-integral transform** `F_i(c_i) ~ Uniform(0,1)` — a per-axis **rank normalization** —
  before Pareto navigation, precisely to make **"semantically incomparable criteria comparable."**
  The rank transform is order-preserving/monotone (their D4). This is the "use ranks not raw scores
  to fix cross-axis incomparability" idea, formalized.

- **Pareto-ranking via non-dominated sorting (Keller, "Pareto-ranking efficient method using
  dominance-based Hasse diagrams")** — *[verified, high]*. Standard iterated non-dominated sorting
  (front 1, peel, front 2, …) — the peeling procedure the current doc's incremental construction
  approximates.

**Verdict Q1:** rank-first / ordinal-dominance is an **established MCDA/MOO primitive** with a named
citation (ranking-dominance) and a modern rank-normalization variant (COPA). **Not claimable as
novel.**

## 3. Q2 — Does ranking reduce front bloat? **YES, documented — but it does not eliminate it.**

- Kukkonen & Lampinen motivate ranking-dominance *specifically* because Pareto-dominance "cannot
  distinguish solutions from one another anymore" at high objective counts — i.e. the bloat problem
  is the stated reason the method exists. *[verified]*
- **AD-Pareto documents the residual bloat directly** *[verified, high — from primary full text]*:
  even after per-axis ranking, "the Pareto front **typically contains many targets** (since
  trade-offs exist and we have no external weights…), **so** to produce a practical overall ranking,
  we introduced a 'utopia point' method." The word "so" makes front bloat the explicit motivation
  for a second scalarization step.

**Verdict Q2:** rank-first improves comparability and resolution (documented), but for genuinely
trade-off-heavy problems the front is still large enough that a **second step** (utopia-point /
scalarization) is needed to get a usable ranking. Ranking alone is not a cure.

## 4. Q3 — The comparison-derived-ranking → Pareto hybrid: **published, in two forms.**

- **AD-Pareto** (see §5) derives each per-axis ranking from **within-axis pairwise LLM comparisons**
  (a QuickSort with the LLM as comparison oracle), then computes the Pareto front — this *is* the
  comparison-based-ranking-then-Pareto pipeline. *[verified, high]*
- **MO-IRL (arXiv:2505.11864, Cherukuri & Lala, "Learning Pareto-Optimal Rewards from Noisy
  Preferences")** — *[verified, high]* — models noisy preferences with **Plackett–Luce / Bradley–
  Terry**, recovers latent **vector-valued** rewards, and defines the **Pareto front** component-wise
  on those vectors. So "pairwise preferences → (BT/PL) latent multi-objective values → Pareto front"
  is already a published framework, with sample-complexity theory.

**Verdict Q3:** the hybrid is **not novel**. Both a domain instance (AD-Pareto, LLM+QuickSort) and a
theory instance (MO-IRL, Bradley–Terry/Plackett–Luce → Pareto) exist. Note AD-Pareto uses QuickSort
verdict-splitting, **not** a Bradley–Terry win-matrix fit — so a *rigorously BT/Elo-aggregated*
per-axis ranking feeding Pareto is a slightly less-occupied variant, but the idea is anticipated.

## 5. Q4 — AD-Pareto's actual pipeline: **it is rank-first from pairwise comparisons. DECISIVE.**

The full text was fetched and quoted this pass (it was blocked last time). Verified findings:

- **Per-axis rankings from pairwise comparisons** *[verified, high]*: "We implemented a novel
  pairwise **QuickSort**-based ranking procedure that leverages the LLM as a **comparative oracle**…
  the LLM is queried to compare each remaining target to the pivot… recurses… until **a complete
  ranking is obtained**" — a full rank order of all 522 targets **per criterion**.
- **Six criteria ≈ our six axes** *[verified]*: biological confidence, technical feasibility,
  clinical developability, patient impact, competitive landscape, safety.
- **Pairwise beat pointwise** *[verified]*: they ran both and "pairwise comparative reasoning
  consistently exceeded pointwise scoring across five of six criteria" (16 replicate runs/criterion)
  — the same calibration-drift argument the current doc makes, already empirically tested.
- **Pareto front + utopia-point** *[verified, high]*: Pareto ranking on the per-criterion results,
  then a utopia-point (percentile-rank vector → Euclidean distance to (100,…,100)) scalarization to
  break the bloated front.
- **Elo/preference-learning cited only as inspiration** *[verified]*, not as the aggregation
  mechanism — so a true BT/Elo latent-strength aggregation is *not* what they did.

**What verification REFUTED (be careful here):** the strong claim that AD-Pareto computes Pareto
dominance *directly on per-axis rank vectors and not on scores* was **refuted / left ambiguous**
*[2 independent verifiers, medium]*. Because the paper produces **both** per-criterion QuickSort
rankings **and** pointwise scores and benchmarks them, the full text does not unambiguously state
which representation feeds the Pareto operator. So: AD-Pareto is definitively **rank-first from
pairwise comparisons**, but whether its Pareto step ingests ranks vs. scores is not nailed down.

**Verdict Q4:** AD-Pareto **anticipates the rank-first-from-pairwise idea in the exact application
(LLM drug-target prioritization)**. It is a much nearer neighbor than the earlier memo recorded — it
shares the six axes, the pairwise-over-pointwise rationale (tested), the per-axis full ranking, the
Pareto front, and even the front-bloat → utopia-point fix.

---

## 6. Bottom line

| Cell | Verdict | Novel? |
|---|---|---|
| Rank-first as general MCDA/MOO primitive | **established** (ranking-dominance 2007; COPA 2025) | **No** |
| Ranking reduces (not eliminates) front bloat | **documented** (Kukkonen; AD-Pareto utopia-point) | **No** |
| Pairwise → ranking → Pareto hybrid | **published** (AD-Pareto; MO-IRL) | **No** |
| Rank-first in **LLM drug-target prioritization** | **published — AD-Pareto** | **No** |

**Consequence for the project.** Switching the arena from dominance-first to rank-first is a sound
*engineering* choice (better comparability, order-independence, smaller front), but it is **fully
anticipated** — and, worse, it moves the design *toward* AD-Pareto rather than away from it. A
reviewer citing AD-Pareto would find our six axes, our pairwise-over-pointwise argument, our Pareto
front, and now our rank-first construction all already present there.

This **reinforces the existing prior-art memo's conclusion**: the defensible novelty is **not the
ranking/front method**. It is the parts AD-Pareto explicitly lacks —
1. the **closed comparison-native VoI loop** (AD-Pareto produces a static ranking and stops), and
2. the **evidence-gap vs. genuine-trade-off split** (only `insufficient_evidence` ties are
   experiment-breakable; AD-Pareto has no such routing).

If anything, adopt rank-first *because it is the validated, standard choice* (cite Kukkonen, COPA,
AD-Pareto), and spend the novelty budget entirely on the loop and the gap/trade-off split.

---

## 7. Key sources (verified, primary where fetched)

- Kukkonen & Lampinen, **"Ranking-Dominance and Many-Objective Optimization,"** IEEE CEC 2007,
  pp. 3983–3990, DOI 10.1109/CEC.2007.4424990. *(named rank-per-axis primitive; curse-of-dimensionality motivation)*
- Javaloy, Vergari, Valera, **"COPA: Comparing the Incomparable in Multi-Objective Model
  Evaluation,"** arXiv:2503.14321, 2025. *(per-axis CDF/rank normalization before Pareto)*
- Keller, **"Pareto-ranking efficient method using dominance-based Hasse diagrams."**
  *(iterated non-dominated sorting)*
- Cherukuri & Lala, **"Learning Pareto-Optimal Rewards from Noisy Preferences: A Framework for
  Multi-Objective Inverse RL,"** arXiv:2505.11864, 2025. *(Bradley–Terry/Plackett–Luce preferences → vector rewards → Pareto front)*
- **AD-Pareto** — "Large Language Model-Driven Prioritization of Alzheimer's Disease Drug Targets
  Across Multidimensional Criteria," **medRxiv 2025.12.28.25343106** (Dec 2025). *(LLM QuickSort
  pairwise per-axis ranking → Pareto + utopia-point; six criteria; pairwise > pointwise, tested)*

> Provenance: deep-research run `wf_7bf6d238-988`, journal at
> `…/subagents/workflows/wf_7bf6d238-988/journal.jsonl`. The synthesis phase crashed on a
> structured-output retry cap; this report is reconstructed from the verified per-claim verdicts in
> that journal (search + fetch + 3-vote verification all completed).
