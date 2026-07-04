# Comparison-Based Multi-Agent Pareto Front Analysis System

## 1. Purpose

This system is designed to prioritise therapeutic hypotheses without asking an LLM to assign absolute numerical scores.

Instead of scoring each hypothesis independently, the system derives a Pareto front through **qualitative pairwise comparisons** between hypotheses. Each comparison is performed by multiple axis-specific LLM agents, and the final Pareto front is computed using deterministic dominance rules.

The system is intended for hypothesis reports that contain information such as:

- target and disease metadata,
- proposed therapeutic modality,
- biological rationale,
- data-analysis results,
- experiment results,
- literature-derived evidence,
- known liabilities,
- evidence gaps,
- proposed follow-up experiments.

The first version focuses on building a conservative, auditable, comparison-based Pareto front and a domination graph.

---

## 2. Motivation

Absolute LLM scoring is often unreliable because the model may be strict in one call and generous in another. For example, one hypothesis may receive a score of `0.8` under one implicit calibration standard, while another receives `0.7` under a different standard. These numbers may not be meaningfully comparable.

To avoid this problem, the system asks a simpler question:

> Given two hypotheses, which one is better on a specific axis?

This turns prioritisation into a comparison problem rather than a scoring problem.

The final output is not a total ranking. It is a **partial order**:

- some hypotheses dominate others,
- some are non-dominated and remain on the Pareto front,
- some cannot be ordered because they involve genuine trade-offs or insufficient evidence.

This is more appropriate for early-stage scientific and drug-discovery decision-making, where hypotheses often differ across multiple competing criteria.

---

## 3. High-Level Workflow

The system follows three main steps:

```text
Input hypothesis reports
        ↓
Red-flag screening
        ↓
Surviving hypotheses
        ↓
Incremental comparison-based Pareto-front construction
        ↓
Axis-specific pairwise comparison agents
        ↓
Conservative dominance aggregation
        ↓
Final Pareto front + domination graph
```

The first version does **not** implement:

- clustering,
- repeated comparisons,
- numeric LLM scoring,
- Monte Carlo uncertainty propagation,
- active learning,
- global rank aggregation.

These can be added in later versions.

---

## 4. Input Hypothesis Format

Each input hypothesis is a structured report. A typical report may look like this:

```json
{
  "id": "H1",
  "target": {
    "symbol": "BRAF",
    "ensembl_id": "ENSG00000157764"
  },
  "disease": {
    "name": "cutaneous melanoma",
    "efo_id": "MONDO_0005012"
  },
  "modality": "small_molecule",
  "narrative": {
    "target_overview": "...",
    "pathways": ["..."],
    "liabilities": ["..."],
    "evidence_gaps": ["..."],
    "proposed_experiments": [
      {
        "experiment": "single-cell malignant-fraction profiling",
        "axis": "right_tissue",
        "cost_tier": 3,
        "rationale": "..."
      }
    ]
  },
  "axes": {
    "right_target": {...},
    "right_tissue": {...},
    "right_safety": {...},
    "right_patient": {...},
    "right_commercial": {...},
    "tractability": {...}
  }
}
```

The six axes used in the first version are:

| Axis | Meaning |
|---|---|
| `right_target` | Strength of causal and mechanistic support for the target-disease relationship |
| `right_tissue` | Relevance of the target in the correct tissue, cell type, disease state, or patient context |
| `right_safety` | Expected therapeutic safety margin; higher means safer or more tolerable |
| `right_patient` | Likely patient impact, clinical relevance, biomarker clarity, and endpoint relevance |
| `right_commercial` | Commercial attractiveness, differentiation, and strategic whitespace |
| `tractability` | Feasibility of modulating the target with the proposed modality |

All axes are treated as “higher is better” conceptually, but the LLM agents are never asked to produce numerical values.

---

## 5. Step 1: Red-Flag Screening

Before Pareto analysis, a red-flag LLM reviews each hypothesis independently.

Its purpose is to remove hypotheses that should not enter the comparison process at all.

Examples of red flags include:

- catastrophic or unacceptable safety liability,
- no plausible target-disease rationale,
- no plausible intervention modality,
- disease context mismatch,
- target is only a biomarker with no causal or interventional rationale,
- evidence is almost entirely synthetic,
- missing required fields,
- contradictory report contents,
- incoherent therapeutic hypothesis.

The red-flag agent does not rank hypotheses and does not assign scores.

It returns structured output:

```json
{
  "hypothesis_id": "H1",
  "decision": "keep",
  "red_flags": [
    {
      "severity": "major",
      "category": "safety",
      "reason": "The report notes broad knockout phenotypes, suggesting a possible safety liability."
    }
  ],
  "rationale": "The hypothesis has safety concerns but remains comparable, so it is kept."
}
```

A hypothesis is removed if:

```text
red_flag_decision = "remove"
```

or if it contains at least one critical red flag.

Removed hypotheses are stored in the final output with their red-flag explanations.

---

## 6. Step 2: Incremental Pareto Front Construction

The system maintains a current front group:

```python
front = []
domination_edges = []
```

It processes surviving hypotheses one by one.

For each new candidate hypothesis:

1. Compare the candidate against each current front member.
2. If any current front member dominates the candidate, discard the candidate.
3. Store a domination edge from the incumbent to the candidate.
4. If the candidate dominates any current front member, mark those front members for removal.
5. Store domination edges from the candidate to each dominated front member.
6. If the candidate is not dominated, add it to the front.
7. Remove any front members dominated by the candidate.

Pseudo-code:

```python
def build_pareto_front(survivors):
    front = []
    domination_edges = []

    for candidate in survivors:
        candidate_is_dominated = False
        front_members_to_remove = []

        for incumbent in list(front):
            comparison = compare_hypotheses(candidate, incumbent)

            if comparison.overall_relation == "B_dominates_A":
                candidate_is_dominated = True
                domination_edges.append(
                    make_edge(dominator=incumbent, dominated=candidate, comparison=comparison)
                )
                break

            elif comparison.overall_relation == "A_dominates_B":
                front_members_to_remove.append(incumbent)
                domination_edges.append(
                    make_edge(dominator=candidate, dominated=incumbent, comparison=comparison)
                )

        if not candidate_is_dominated:
            for h in front_members_to_remove:
                front.remove(h)
            front.append(candidate)

    return front, domination_edges
```

This first version is intentionally simple. It compares each new hypothesis only with the current front group. This makes the algorithm efficient, but it also means the result may be input-order sensitive.

The output should include an algorithm note:

```json
{
  "algorithm_note": "Incremental Pareto construction is input-order sensitive in this first version because dominated non-front hypotheses are not compared against future candidates."
}
```

---

## 7. Step 3: Axis-Specific Pairwise Comparison Agents

Each pairwise comparison between two hypotheses is decomposed into six axis-specific comparisons.

For a candidate `A` and incumbent `B`, the system calls six subagents in parallel:

```text
right_target_agent
right_tissue_agent
right_safety_agent
right_patient_agent
right_commercial_agent
tractability_agent
```

Each subagent compares the two hypotheses only on its assigned axis.

For example, the safety agent answers:

> Is Hypothesis A safer, less safe, tied, incomparable, or insufficiently evidenced compared with Hypothesis B?

Each axis agent returns:

```json
{
  "axis": "right_safety",
  "relation": "A_better",
  "confidence": "medium",
  "rationale": "Hypothesis A has fewer known on-target liabilities and a more favourable therapeutic window.",
  "decisive_evidence": [
    "Hypothesis A has no curated safety liability in the report.",
    "Hypothesis B has broad mouse-knockout phenotypes."
  ],
  "missing_evidence": [
    "No human tolerability data are provided for either hypothesis."
  ]
}
```

Allowed axis-level relations are:

| Relation | Meaning |
|---|---|
| `A_better` | A is clearly or probably better than B on this axis |
| `B_better` | B is clearly or probably better than A on this axis |
| `tie` | A and B are materially similar on this axis |
| `incomparable` | A and B cannot be fairly ordered on this axis |
| `insufficient_evidence` | The reports do not contain enough evidence to compare them |

Allowed confidence labels are:

| Confidence | Meaning |
|---|---|
| `high` | Direct evidence and a clear comparison |
| `medium` | Evidence supports a direction but with caveats |
| `low` | Weak, indirect, synthetic, or incomplete evidence |

No axis agent is allowed to assign a numerical score.

---

## 8. Axis Agent Responsibilities

### 8.1 `right_target` agent

Compares the strength of causal and mechanistic support for the target-disease relationship.

It should prefer:

- human genetics,
- somatic genetics,
- perturbation evidence,
- pathway causality,
- disease biology,
- curated disease association evidence.

It should not reward literature popularity alone.

### 8.2 `right_tissue` agent

Compares whether the target is active and relevant in the right tissue, cell type, disease state, or patient context.

It should prefer:

- single-cell evidence,
- spatial evidence,
- disease-tissue evidence,
- malignant-vs-stromal evidence,
- disease-context-specific expression or activity evidence.

It should penalize purely synthetic tissue assumptions.

### 8.3 `right_safety` agent

Compares expected therapeutic safety margin.

Better means:

- safer,
- more tolerable,
- less likely to create unacceptable on-target toxicity,
- better therapeutic window.

It should consider:

- known safety liabilities,
- essentiality,
- genetic constraint,
- knockout phenotypes,
- pathway toxicity,
- tissue distribution,
- modality-related risks.

### 8.4 `right_patient` agent

Compares likely patient impact and clinical relevance.

It should prefer hypotheses with:

- defined patient populations,
- biomarker strategy,
- clinical precedent,
- meaningful endpoints,
- high unmet need,
- plausible therapeutic benefit.

### 8.5 `right_commercial` agent

Compares commercial attractiveness and strategic whitespace.

Better means:

- stronger differentiation,
- less crowding,
- clearer market opportunity,
- better competitive position,
- more attractive indication niche.

It should not confuse scientific validity with commercial attractiveness.

### 8.6 `tractability` agent

Compares feasibility of modulating the target with the proposed modality.

It should prefer:

- direct modality precedent,
- approved drugs,
- high-quality ligands,
- structural pockets,
- assayability,
- developable molecules,
- delivery feasibility,
- modality-target fit.

---

## 9. Aggregating Axis Comparisons into Pareto Dominance

After the six axis agents return their reports, the system aggregates them using conservative deterministic rules.

Let the candidate be `A` and the incumbent be `B`.

### A dominates B

`A` dominates `B` if:

```text
- at least one axis returns A_better
- no axis returns B_better
- no axis returns incomparable
- no axis returns insufficient_evidence
```

### B dominates A

`B` dominates `A` if:

```text
- at least one axis returns B_better
- no axis returns A_better
- no axis returns incomparable
- no axis returns insufficient_evidence
```

### Otherwise

The result is:

```text
tradeoff_or_unresolved
```

This happens when:

- both hypotheses are better on different axes,
- at least one axis is incomparable,
- at least one axis has insufficient evidence,
- neither hypothesis is strictly better on any axis.

Examples:

| Axis pattern | Overall result |
|---|---|
| A better on 2 axes, tied on 4 axes | A dominates B |
| A better on 5 axes, insufficient evidence on 1 axis | No strict dominance |
| A better on target, B better on safety | Trade-off; no dominance |
| All axes tied | No dominance |
| B better on 1 axis, tied on 5 axes | B dominates A |

The dominance rule is intentionally conservative. A hypothesis should only dominate another if the comparison is clean across all axes.

---

## 10. Domination Graph

Whenever one hypothesis dominates another, the system stores a directed domination edge:

```text
H_i → H_j
```

meaning:

```text
H_i dominates H_j
```

Each edge stores the complete axis-level comparison evidence.

Example edge:

```json
{
  "dominator": "H1",
  "dominated": "H3",
  "comparison_summary": {
    "overall_relation": "A_dominates_B",
    "strictly_better_axes": ["right_target", "tractability"],
    "tied_axes": ["right_patient", "right_tissue", "right_safety", "right_commercial"],
    "worse_axes": [],
    "unresolved_axes": []
  },
  "axis_comparisons": {
    "right_target": {
      "relation": "A_better",
      "confidence": "high",
      "rationale": "...",
      "decisive_evidence": ["..."],
      "missing_evidence": ["..."]
    },
    "right_tissue": {
      "relation": "tie",
      "confidence": "medium",
      "rationale": "...",
      "decisive_evidence": ["..."],
      "missing_evidence": ["..."]
    }
  }
}
```

The graph output contains:

- all input hypotheses as nodes,
- node status: `front`, `dominated`, or `red_flagged`,
- all stored domination edges,
- full comparison reports for each edge.

---

## 11. Final Output Format

The final system output is a JSON object:

```json
{
  "run_metadata": {
    "num_input_hypotheses": 10,
    "num_removed_by_red_flags": 2,
    "num_surviving_hypotheses": 8,
    "num_front_hypotheses": 3,
    "num_domination_edges": 5,
    "algorithm_note": "Incremental Pareto construction is input-order sensitive in this first version because dominated non-front hypotheses are not compared against future candidates."
  },
  "red_flagged_hypotheses": [
    {
      "hypothesis_id": "H7",
      "decision": "remove",
      "red_flags": [
        {
          "severity": "critical",
          "category": "safety",
          "reason": "..."
        }
      ],
      "rationale": "..."
    }
  ],
  "pareto_front": [
    {
      "hypothesis_id": "H1",
      "target": "BRAF",
      "disease": "cutaneous melanoma",
      "modality": "small_molecule",
      "front_status": "non_dominated"
    }
  ],
  "domination_graph": {
    "nodes": [
      {
        "hypothesis_id": "H1",
        "status": "front"
      },
      {
        "hypothesis_id": "H3",
        "status": "dominated"
      },
      {
        "hypothesis_id": "H7",
        "status": "red_flagged"
      }
    ],
    "edges": [
      {
        "dominator": "H1",
        "dominated": "H3",
        "comparison_summary": {...},
        "axis_comparisons": {...}
      }
    ]
  }
}
```

---

## 12. Worked Example: Melanoma

This section runs the full pipeline end-to-end on a concrete disease so that every step, and
every failure mode discussed in Section 13, is grounded in a real example.

### 12.1 The input set

The query is: *"What is the best therapeutic hypothesis for cutaneous melanoma?"* Ten hypotheses
enter the system. Each is a fully-framed `target × disease × modality × mechanism` report.

| ID | Target | Modality | Mechanism / stratum |
|---|---|---|---|
| H1 | BRAF | small molecule | V600E kinase inhibition, BRAF-mutant patients |
| H2 | MEK1/2 | small molecule | downstream MAPK inhibition, combination partner |
| H3 | PD-1 | antibody | checkpoint blockade, immune-inflamed tumours |
| H4 | NRAS | small molecule | direct NRAS-Q61 inhibition, NRAS-mutant patients |
| H5 | CTLA-4 | antibody | checkpoint blockade, combination with PD-1 |
| H6 | c-KIT | small molecule | acral/mucosal melanoma, KIT-mutant stratum |
| H7 | MITF | small molecule | lineage transcription factor knockdown |
| H8 | PMEL | ADC | melanosomal antigen, high-antigen stratum |
| H9 | LAG-3 | antibody | checkpoint blockade, PD-1-refractory stratum |
| H10 | TYR | small molecule | tyrosinase enzymatic inhibition |

### 12.2 Step 1 — red-flag screening

The red-flag agent reviews each hypothesis in isolation and removes two:

- **H7 (MITF)** — `remove`, critical **tractability/rationale** flag. MITF is a lineage
  transcription factor with no small-molecule binding pocket and no plausible direct-inhibition
  modality; the report proposes "small-molecule knockdown" with no mechanism. Incoherent
  hypothesis.
- **H10 (TYR)** — `remove`, critical **target** flag. Tyrosinase is a pigmentation enzyme and a
  melanocyte differentiation marker, not a driver of malignant proliferation. The report gives no
  causal disease rationale — it is a biomarker, not a therapeutic target.

Eight survivors proceed, in input order: **H1, H2, H3, H4, H5, H6, H8, H9**.

### 12.3 Step 2 — incremental front construction

Each candidate is compared only against the **current** front, and the inner loop stops the moment
the candidate is dominated (`break`). One comparison = the six axis agents of Section 7.

| Step | Candidate | Compared against (current front) | Outcome | Comparisons | Front after |
|---|---|---|---|---|---|
| 1 | H1 (BRAF) | *(front empty)* | seeds front | 0 | {H1} |
| 2 | H2 (MEK) | H1 | **H1 dominates H2** (BRAF has stronger genetic/causal support on `right_target`, both tied elsewhere) → `break` | 1 | {H1} — H2 discarded, edge H1→H2 |
| 3 | H3 (PD-1) | H1 | trade-off (H1 better `right_target`, H3 better `right_patient`/`right_commercial`) → not dominated | 1 | {H1, H3} |
| 4 | H4 (NRAS) | H1 → H3 | **H1 dominates H4** (BRAF is more tractable; NRAS is historically undruggable → `tractability` = A_better, rest tied) → `break` | 1 | {H1, H3} — H4 discarded, edge H1→H4 |
| 5 | H5 (CTLA-4) | H1 → H3 | trade-off vs H1; **H3 dominates H5** (better safety window, tied elsewhere) → edge H3→H5, but H5 already not on front path… see note | 2 | {H1, H3} — H5 discarded, edge H3→H5 |
| 6 | H6 (c-KIT) | H1 → H3 | trade-off vs both (narrow acral/mucosal stratum: worse `right_patient`, better `right_commercial` whitespace) → not dominated | 2 | {H1, H3, H6} |
| 7 | H8 (PMEL ADC) | H1 → H3 → H6 | trade-off vs all three (novel modality, strong `right_tissue` specificity, weak `right_patient` evidence) → not dominated | 3 | {H1, H3, H6, H8} |
| 8 | H9 (LAG-3) | H1 → H3 → H6 → H8 | **H3 dominates H9** (same checkpoint class, more clinical precedent; H9 is a PD-1-refractory niche) → `break` | 2 | {H1, H3, H6, H8} — H9 discarded, edge H3→H9 |

**Total pairwise comparisons: 0+1+1+1+2+2+3+2 = 12** (each = 6 axis-agent calls → ~72 axis-agent
calls).

**Final Pareto front:** {H1 (BRAF), H3 (PD-1), H6 (c-KIT), H8 (PMEL ADC)}
**Dominated (with edges):** H2←H1, H4←H1, H5←H3, H9←H3
**Red-flagged:** H7 (MITF), H10 (TYR)

The front is honest about the real structure of melanoma therapy: a MAPK-pathway small molecule
(H1), a checkpoint antibody (H3), a niche-stratum kinase inhibitor (H6), and a novel-modality ADC
(H8) genuinely trade off across the six axes and none strictly dominates another. The system does
**not** force them into a false 1–2–3–4 ranking.

### 12.4 What this example already reveals

Two properties visible in the trace above are analysed in depth in Section 13:

- **Coverage is incomplete.** H2, H4, H5, H9 were each eliminated on first contact and never
  compared against later candidates. If (say) H6 also dominated H2, that edge is never recorded —
  the domination graph is missing true edges.
- **The count is small but order-dependent.** Twelve comparisons is far below the 28 a full
  round-robin over eight survivors would cost — but that saving is exactly what makes the front
  sensitive to the arrival order. Section 13.2 re-runs this same melanoma set in a different order
  and gets a different front.

---

## 13. Scalability and Stability

The worked example in Section 12 is small and clean. This section examines what happens as the
number of hypotheses grows (**scalability**) and whether the same inputs reliably produce the same
output (**stability**). Both are consequences of the two design choices made in Sections 6 and 7:
comparing only against the current front, and calling the LLM once per comparison.

### 13.1 Scalability — how the comparison count grows

The cost of a run is dominated by the number of `compare_hypotheses` calls, because each one fans
out into six axis-agent LLM calls. Two regimes bound the behaviour:

| Regime | When it happens | Comparisons for *n* survivors |
|---|---|---|
| **Best case** | Every candidate is dominated by the first front member it meets (`break` fires immediately) | `n − 1` (linear) |
| **Worst case** | No hypothesis ever dominates another; the front grows to include everyone | `n(n − 1) / 2` (quadratic) |

The incremental algorithm is therefore **between linear and quadratic**, and — critically — it is
the *conservative dominance rule* (Section 9) that pushes it toward the expensive end. Because any
single `incomparable` or `insufficient_evidence` axis blocks dominance, most comparisons resolve to
`tradeoff_or_unresolved`, nobody is eliminated, the front keeps growing, and each new candidate must
be compared against an ever-larger front. **Conservatism and cost compound.**

For the melanoma set this is benign — with `n = 8` the worst case is only 28 comparisons (168
axis-agent calls). But the growth is real:

| Survivors *n* | Best case (`n−1`) | Worst case (`n(n−1)/2`) | Worst-case axis-agent calls (×6) |
|---|---|---|---|
| 8 (melanoma) | 7 | 28 | 168 |
| 15 | 14 | 105 | 630 |
| 30 | 29 | 435 | 2,610 |
| 50 | 49 | 1,225 | 7,350 |

At the intended scale of this system (**5–15 hypotheses per disease**), even the worst case is
cheap and the full round-robin discussed in Section 13.3 is affordable. The quadratic term only
becomes a real constraint above ~30 hypotheses — at which point clustering (Section 17.3) or a
Swiss-style match schedule, rather than all-pairs comparison, becomes necessary.

> **Latency, not just count.** The six axis agents within one comparison run in parallel, so the
> per-comparison latency is one LLM round-trip, not six. But comparisons *across* the incremental
> loop are sequential — a candidate cannot be placed until the previous one settles the front — so
> wall-clock time scales with the comparison count, not just with compute.

### 13.2 Stability — the same inputs can produce different fronts

There are **two independent** sources of instability. They stack.

**(a) Algorithmic instability — input-order sensitivity.**
Because each candidate is compared only against the *current* front and eliminated candidates are
never revisited, the arrival order changes which comparisons ever happen. Re-run the melanoma set
with the survivors shuffled to **H3, H9, H1, H2, …**:

- **H3 (PD-1)** seeds the front.
- **H9 (LAG-3)** now arrives *before* H1 and *before* any BRAF comparison. It is compared only
  against H3. In Section 12 H3 dominated H9 — assume it still does → H9 discarded. Front = {H3}.
- **H1 (BRAF)** arrives and is compared against H3 → trade-off → joins. Front = {H3, H1}.
- …

In this ordering the front can settle to the same four members — but it need not. Suppose H9 had
instead been a genuine trade-off against H3 (better on `right_patient` for the PD-1-refractory
stratum, worse on `right_commercial`). In the Section 12 ordering H9 arrived *last*, met the full
front {H1, H3, H6, H8}, and — if any of those dominated it — was discarded. In the shuffled
ordering H9 arrived *second*, met only H3, was not dominated, and **joined the front**. **Same ten
hypotheses, same LLM verdicts, different Pareto front — purely because of input order.** This is the
algorithmic instability, and it exists even if the LLM is perfectly deterministic.

**(b) LLM instability — judgment variance.**
Each axis comparison is a single LLM call (Section 7). Run the same `right_safety` comparison of
BRAF-inhibitor (H1) vs PD-1 (H3) twice and the relation can flip between `tie` and `B_better`
depending on temperature, phrasing, and how the model weighs "manageable cutaneous toxicity" against
"immune-related adverse events." A single flipped axis is enough to turn a clean dominance into a
`tradeoff_or_unresolved` (or vice versa), which changes who stays on the front. This instability
exists even if the input order is fixed.

The comparison-based design (Section 12/§Why comparison-based, below) reduces **one** kind of LLM
instability — global calibration drift, the "0.8 here, 0.7 there" problem — because the model only
ever makes a local A-vs-B judgment. It does **not** remove per-comparison variance, and it does
nothing at all for the algorithmic instability in (a).

### 13.3 Mitigations, ordered by cost

At the 5–15 hypothesis scale, the algorithmic instability is cheap to eliminate outright, and the
LLM instability is cheap to suppress. In rough order of cost/benefit:

1. **Full round-robin instead of incremental (kills instability (a)).**
   At `n ≤ 15` the worst case is ≤ 105 comparisons — affordable. Comparing *all* pairs, not just
   candidate-vs-current-front, makes the front and the domination graph **order-independent and
   complete**: every true edge is recorded, and no hypothesis is eliminated before it has met every
   other. For the melanoma set this is 28 comparisons vs the incremental 12 — a small premium for
   determinism. **This is the recommended default for small sets.**

2. **Order-swapped comparisons (suppresses position bias in (b)).**
   Run each pair as both `compare(A, B)` and `compare(B, A)`; if the relation is not symmetric,
   downgrade to `tie` or `insufficient_evidence`. One extra call per pair.

3. **Repeated comparisons with majority vote (suppresses variance in (b)).**
   For front-defining or rank-decisive pairs, run the comparison *k* times and take the majority
   axis relation. Spend the repetition budget only where it matters — pairs near the dominance
   boundary — not on lopsided pairs the `break` would have settled immediately.

4. **Multiple ordering runs + stability report (measures residual (a)).**
   If the incremental algorithm is kept for cost reasons at larger *n*, run it under several random
   orderings and report the **front-membership frequency** of each hypothesis. A hypothesis on the
   front in 5/5 orderings is stable; one on the front in 2/5 is genuinely borderline and should be
   flagged as such rather than reported as a crisp front member.

5. **Clustering before comparison (bounds scalability at large *n*).**
   For `n ≫ 30`, partition hypotheses by disease sub-context, pathway, or modality, build a local
   front within each cluster, then compare only local-front members globally. This turns one large
   quadratic into several small ones. See Section 17.3.

> **Recommendation for this system's scale.** Adopt (1) full round-robin and (2) order-swapping as
> the default at 5–15 hypotheses; they are cheap here and together remove the algorithmic
> instability and the worst of the position bias. Reserve (3)–(5) for larger runs. The
> `algorithm_note` in the output (Section 6) should state which regime was used, so a reader knows
> whether the reported front is order-independent or order-sensitive.

---

## 14. Two Front-Construction Strategies: Dominance-First vs. Rank-First

Sections 6 and 13 describe a **dominance-first** system: Pareto dominance is computed directly from
scattered per-pair, per-axis qualitative relations, and the front is built incrementally. This
section names the principled alternative — **rank-first** — explains why it fixes most of the
scalability and stability problems of Section 13, and records that it is **prior art**, not a
contribution of this system.

### 14.1 The two strategies

**Dominance-first** (Sections 6–9). For each pair (A, B) and each axis, an agent returns a local
relation (`A_better` / `tie` / `incomparable` / `insufficient_evidence`). Dominance is aggregated
from these scattered local verdicts. No per-axis ordering across the whole set is ever built.

**Rank-first.** First, for each axis *independently*, produce a **total ranking of all surviving
hypotheses** on that axis alone (1…x). Every hypothesis then carries a **rank vector**
`(r_target, r_tissue, r_safety, r_patient, r_commercial, r_tractability)`. The Pareto front is
computed on these rank vectors by the standard rule: A dominates B iff A's rank is no worse than B's
on every axis and strictly better on at least one.

### 14.2 Why rank-first resolves more (and stacks less)

The bloat and instability diagnosed in Section 13 come from two properties of dominance-first, both
of which rank-first removes:

- **No gaps.** A rank vector has a number in *every* cell, so `incomparable` and
  `insufficient_evidence` — the exact conditions that block dominance under Section 9 and inflate the
  front — cannot occur. Strictly more pairs resolve → a smaller, more decision-useful front.
- **Transitivity by construction.** A per-axis total order is transitive; the scattered pairwise
  verdicts of dominance-first are not (A>B>C>A can occur), which blocks dominance incoherently.
- **Order-independence.** The per-axis rankings are computed over the whole set at once, so the
  input-order sensitivity of the incremental front (Section 13.2(a)) disappears.

**But rank-first does not eliminate front bloat — it only reduces it.** For genuinely trade-off-heavy
problems the front is still large, because trade-offs are real: a hypothesis ranked 1st on safety and
last on tractability is genuinely non-dominated. In practice a rank-first system still needs a
*second* step (a scalarization such as a utopia-point / distance-to-ideal score) to turn the reduced
front into a usable total ranking. Ranking is a sharpener, not a cure.

There is also an honest cost: **a rank discards magnitude.** Ranks 1 and 2 may be near-tied or far
apart, and dominance-on-ranks treats them identically — so rank-first can *manufacture* separation
where the evidence is a wash. Dominance-first's explicit `tie` / `incomparable` labels are the honest
report of "we genuinely cannot separate these." Rank-first buys resolution partly by being less
conservative.

### 14.3 This is prior art — adopt it, do not claim it

Rank-first is **not novel**, in either the general method or this application. A prior-art review
(2026-07) established:

- **As an MCDA / multi-objective-optimization primitive** it is decades old. *Ranking-dominance*
  (Kukkonen & Lampinen, IEEE CEC 2007) ranks per objective specifically to beat the
  curse-of-dimensionality / front-bloat problem; *COPA* (arXiv:2503.14321, 2025) applies a per-axis
  CDF/rank normalization to make axes comparable before Pareto navigation.
- **The comparison-derived-ranking → Pareto hybrid is also published**: deriving each per-axis
  ranking from pairwise comparisons (Bradley–Terry / Plackett–Luce), then taking the Pareto front on
  the result, appears in multi-objective preference learning (e.g. arXiv:2505.11864).
- **In LLM drug-target prioritization specifically, it is already done.** The AD-Pareto work
  (medRxiv 2025.12.28.25343106, 2025) ranks each of six criteria — almost 1:1 with the axes here —
  using an **LLM as a pairwise comparison oracle inside a QuickSort**, then computes a Pareto front
  and breaks the residual bloat with a utopia-point scalarization. It even reports that pairwise
  comparison beat pointwise scoring on 5 of 6 criteria — the same calibration-drift argument this
  document makes in Section 15, already tested.

**Recommendation.** Adopt rank-first as the default front-construction strategy *because it is the
validated, standard choice*, and cite the prior art above rather than presenting it as new. Concretely:
for each axis, obtain a total ranking of the survivors from within-axis pairwise comparisons (the same
axis agents of Section 7, aggregated via QuickSort or Bradley–Terry), then compute the Pareto front on
the rank vectors. This keeps the comparison-based ethos of Section 15 (no absolute 0–1 scoring) while
gaining order-independence and a tighter front.

> **Where the actual contribution must live.** Because rank-first moves this system *toward* its
> nearest neighbor (AD-Pareto) rather than away from it, the front-construction method cannot be the
> novelty. The defensible contribution is what AD-Pareto and the MCDA prior art lack: a **closed,
> comparison-native value-of-information loop** that treats an unresolved front as
> information-acquisition decisions and proposes experiments to collapse it, and a **split between
> `insufficient_evidence` ties (breakable by an experiment) and genuine trade-offs (not breakable)**
> — see Sections 9 and 17. Prior systems produce a static ranking and stop; the loop is the delta.

---

## 15. Why the System Is Comparison-Based

The central design decision is to avoid absolute LLM scoring.

The system never asks:

```text
How good is this hypothesis from 0 to 1?
```

Instead, it asks:

```text
Between Hypothesis A and Hypothesis B, which one is better on this axis?
```

This has several advantages:

1. **Reduced calibration drift**  
   The LLM does not need to maintain a global numerical scale across many calls.

2. **More natural expert reasoning**  
   Experts often find it easier to say which of two options is better than to assign absolute scores.

3. **Auditable trade-offs**  
   The final graph shows exactly why one hypothesis dominated another.

4. **Partial-order output**  
   The system does not force a false total ranking when hypotheses involve genuine trade-offs.

5. **Conservative decision-making**  
   If evidence is insufficient or incomparable on any axis, the system avoids declaring dominance.

---

## 16. Known Limitations of the First Version

> Input-order sensitivity and single-shot LLM variance — the two most consequential limitations —
> are analysed in depth in Section 13 (Scalability and Stability), which also gives cost-ordered
> mitigations. This section covers the remaining limitations.

### 15.1 Conservative dominance may produce large fronts

Because any unresolved or incomparable axis blocks dominance, many hypotheses may remain on the front.

This is acceptable for the first version because the goal is not to force a ranking, but to identify clearly dominated hypotheses.

### 15.2 No clustering

The first version does not cluster hypotheses by disease, pathway, modality, or patient segment.

A future version could compute local Pareto fronts within clusters and then compare local front members globally (see Section 17.3).

### 15.3 Red-flag dependence on LLM judgement

The red-flag filter uses an LLM and may itself be imperfect.

For high-stakes use, red-flag removal should be conservative and reviewable.

---

## 17. Suggested Future Extensions

Future versions could add:

1. **Repeated comparison for robustness**  
   Re-run important pairwise comparisons with order swaps and slightly varied prompts.

2. **Uncertainty-aware front membership**  
   Estimate how stable the Pareto front is across repeated comparison runs.

3. **Clustering before comparison**  
   Compare hypotheses first within disease, modality, pathway, or patient-segment clusters.

4. **Near-front analysis**  
   Identify dominated hypotheses that are close to the front and may be rescued by one experiment.

5. **Value-of-information analysis**  
   Recommend experiments that would resolve unresolved comparisons or front membership.

6. **Adjudicator agent**  
   Add a final reviewer for ambiguous or high-impact comparisons.

7. **Full dominance graph construction**  
   Compare more than just current-front pairs to build a richer partial order.

8. **Human review interface**  
   Allow experts to inspect, override, or annotate individual axis comparisons and domination edges.

---

## 18. Summary

This system implements a conservative, comparison-based, multi-agent Pareto-front analysis workflow.

It uses LLMs for:

- red-flag screening,
- qualitative pairwise axis comparisons,
- evidence-based rationales,
- missing-evidence identification.

It uses deterministic code for:

- Pareto dominance aggregation,
- front maintenance,
- domination edge construction,
- final graph output.

The core principle is:

> LLMs provide structured qualitative comparisons; deterministic algorithms compute the Pareto front.

This avoids unreliable absolute scoring while preserving auditability, interpretability, and scientific caution.
