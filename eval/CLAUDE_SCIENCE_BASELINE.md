# Eval: Prioritisation — Arena (pairwise) vs. Claude Science (pointwise)

**Claim under test.** Given the *same underlying model*, a **head-to-head prioritisation arena**
(pairwise comparison) produces a more **enriched, consistent, and reproducible** target ranking
than **isolated per-hypothesis assessment** (pointwise scoring) — the mode of both the Virtual
Biotech paper and Claude Science. This is a claim about **method, not intelligence**.

**This is not a hunch — it replicates a published result.** Adaszewski & Schindler (medRxiv 2025,
`10.64898/2025.12.28.25343106`) show, on **522 Alzheimer's targets across 6 criteria**, that
**pairwise comparison beats pointwise scoring** with large effect sizes, and that a
web-augmented LLM reaches **AUGC ≈0.72** (matching Open Targets) at enriching known clinical-trial
targets. We adopt their **ground-truth design** and **pairwise-vs-pointwise axis**, use **Claude
Science as the pointwise baseline**, and extend into the gaps they leave open (see below).

Claude Science is a **local scientific-analysis app** (interactive only; no headless API). It is a
**pointwise** system — it reads and returns a narrative verdict per hypothesis. So it plays the
role of the **isolated-assessment baseline**, driven by hand.

> Baseline run **out-of-the-box** (default access, *not* wired to ToolUniverse). The failure we
> measure — pointwise losing to pairwise — is a property of the **method**, not evidence quality,
> so this is not a handicap. State this if challenged.

---

## The two systems

| | **Ours (arena)** | **Baseline (Claude Science)** | **Paper's analogue** |
|---|---|---|---|
| Assessment | pairwise head-to-head, panel of division judges | one narrative verdict per hypothesis, in isolation | pairwise vs. pointwise |
| Aggregation | ranking model over match outcomes → Pareto front | implicit, from the narrative | QuickSort + Pareto/utopia-point |
| Evidence | budgeted **VoI** loop (spend where rank is decided) | ad hoc | one-shot (no VoI) |
| Consistency | measured (transitivity / τ) | measured | **not measured** in paper |

## Task scope & ground truth

**Task:** plain **target prioritisation** — rank known candidate targets. (Not *novel*-target
prioritisation; novelty stays a Pareto objective but we don't claim outcome-validation on novel
targets.)

**Test set: reuse the paper's AD set for direct comparability** — 522 AD targets (high-quality
chemical probes), of which **44 reached AD clinical trials** = the positive label set. Sourced from
Open Targets + the paper's supplement (Cummings et al. trial-target list). Using their set lets us
place our AUGC **directly next to their 0.72**.

**Ground truth is retrospective, not predictive.** No future prediction: we score **early
enrichment of the 44 known clinical-trial targets** in the ranking. Watch for **leakage** — the
model knows which AD targets are in trials; for a fair enrichment eval the signal must be that the
*ranking* surfaces them early from the criteria, not that the model recites trial status. Note this
limitation honestly; the paper has the same exposure.

---

## Metrics

1. **AUGC — Normalised Area Under the Gain Curve** *(primary, comparable to the paper's 0.72).*
   (A_actual − A_random)/(A_perfect − A_random). 1.0 = perfect early enrichment of the 44 positives,
   0 = random. Report for ours **and** for the Claude Science pointwise baseline.

2. **Pairwise consistency / transitivity** *(our contribution — the paper does NOT measure this).*
   Probe pairwise "A vs B" judgments and count **intransitive triples** (A>B, B>C, C>A) and
   position/order-bias. Expected: the pointwise baseline, when forced into pairwise probes, is
   inconsistent; our arena is consistent by construction. **This is the headline differentiator.**

3. **Reproducibility — Kendall's τ across runs.** Run each system 3× (re-ordered candidate lists).
   Report τ for both.

4. **Trade-off recovery — Pareto count.** How many candidates are Pareto-optimal across objectives;
   show ≥1 case where the pointwise pick is Pareto-dominated once objectives are separated.

5. **Auditability (qualitative).** Ours: per-match judge rationale. Baseline: one paragraph.

---

## Protocol

### Baseline — Claude Science (pointwise)
1. Install (macOS installer; or Linux `curl -fsSL https://claude.ai/install-claude-science.sh | bash`
   → `claude-science serve`). Sign in; open a project; `@`-add the `eval/` data folder.
2. **Pointwise:** ask it to score each target on the 6 criteria and produce a ranking → compute AUGC
   vs the 44 positives.
3. **Consistency probe:** in fresh conversations, ask a sample of C(k,2) pairwise "A vs B" questions
   independently → count intransitive triples + order bias.
4. Repeat 3× with re-ordered lists for τ.

### Ours — arena (pairwise)
1. Run the pipeline on the AD 522-set (or a fixed sample), same 6 criteria.
2. Record: full Pareto front, ranking, per-match judge outputs → compute AUGC, τ, transitivity.
3. Re-run to confirm stability.

---

## Results table (fill in)

| Metric | Ours (arena) | Claude Science (pointwise) | Paper (reference) |
|---|---|---|---|
| AUGC (enrichment of 44 trial targets) | | | ~0.72 web-aug / ~0.40 vanilla |
| Kendall's τ across 3 runs | | | — |
| Intransitive triples (per k triads) | | | **not reported** |
| Pareto-optimal candidates surfaced | | | Pareto/utopia used |
| Top-1 stable across 3 runs? | | | — |
| "Why rank i > rank j" inspectable? | yes (per match) | one paragraph | n/a |

## Narrative for the writeup / pitch

> Same model, same data, same 6 criteria as the Alzheimer's prioritisation benchmark. A published
> result already shows pairwise comparison beats pointwise scoring at enriching real clinical-trial
> targets (AUGC 0.72 vs 0.40). We reproduce that with Claude Science as the pointwise baseline — and
> then go where the paper didn't: we **measure pairwise consistency** (the baseline produces
> intransitive judgments; the arena is consistent by construction) and add a **budgeted VoI loop**
> that reaches the ranking spending evidence only where it changes the rank. Prioritisation is a
> *comparison* problem; isolated assessment is the wrong shape for it — now shown, not asserted.
