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

## 12. Why the System Is Comparison-Based

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

## 13. Known Limitations of the First Version

### 13.1 Input-order sensitivity

Because the algorithm compares each new candidate only against the current front, the result may depend on input order.

A later version could reduce this by:

- shuffling input order across multiple runs,
- repeating analysis with different orderings,
- constructing a fuller dominance graph,
- comparing near-front hypotheses after the first pass.

### 13.2 No repeated comparisons

Each pairwise axis comparison is performed only once. This means LLM variance is not yet controlled.

A future version could add:

- order-swapped comparisons,
- repeated calls,
- multiple judge models,
- adjudication for front-defining comparisons.

### 13.3 Conservative dominance may produce large fronts

Because any unresolved or incomparable axis blocks dominance, many hypotheses may remain on the front.

This is acceptable for the first version because the goal is not to force a ranking, but to identify clearly dominated hypotheses.

### 13.4 No clustering

The first version does not cluster hypotheses by disease, pathway, modality, or patient segment.

A future version could compute local Pareto fronts within clusters and then compare local front members globally.

### 13.5 Red-flag dependence on LLM judgement

The red-flag filter uses an LLM and may itself be imperfect.

For high-stakes use, red-flag removal should be conservative and reviewable.

---

## 14. Suggested Future Extensions

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

## 15. Summary

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
