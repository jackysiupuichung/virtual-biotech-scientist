# Design: Virtual Biotech Scientist

This document describes the architecture, the agentic workflow, and the methods. It assumes
the framing in the [README](../README.md): we build a **closed-loop** AI scientist on top of
[ToolUniverse](https://github.com/mims-harvard/ToolUniverse) as the evidence/prediction layer.

---

## 1. Vision

A virtual biotech is defined by a loop, not a pipeline. Its defining act is **generating data
to test a hypothesis**, then updating. We model the four moves a discovery team actually makes:

1. **Hypothesise** — frame the disease/biology question and an initial thesis.
2. **Prioritise** — gather evidence on candidate targets and *choose* among them under uncertainty.
3. **Experiment** — design the next decisive test and obtain a readout.
4. **Refine** — update the thesis and ranking from what the readout showed; repeat until convergence
   or a stop condition (budget, confidence, or a clear lead).

The contribution is the **prioritisation engine** and the **refinement loop** that ToolUniverse's
own flagship case study leaves to a human and to a single open-loop pass, respectively.

---

## 2. Architecture

### 2.1 Agents

- **Target-ID agent** — turns a disease/biology question into a candidate target set, using
  ToolUniverse retrieval tools (e.g. Open Targets associations). Output: a candidate list with
  raw evidence handles.
- **Prioritisation agent** — the core contribution. Consumes per-target evidence across multiple
  axes and produces a **ranked, scored, and justified** ordering of the candidate set (not a
  per-target dossier dump, and not a deferral to a human).
- **Critic agent** — inspects the ranking for weak, missing, or conflicting evidence and emits
  targeted *refinement requests* (which axis, which target, which tool to re-query).
- **Experiment-design agent** — for the leading candidate(s), proposes the next decisive test and
  routes it to a **readout source** (see §4). Downstream concerns (toxicity, tractability, binding
  affinity, ADMET) live here.
- **Orchestrator** — runs the loop, enforces stop conditions, and maintains a **traceable decision
  log** (every claim → the tool call and evidence that supports it).

### 2.2 The loop

```
hypothesis
   │
   ▼
Target-ID ──► Prioritisation ──► Critic
   ▲               │               │
   │               │          gap found?
   │               ▼               │
   │          Experiment-design ◄──┘ (re-query specific axis/target)
   │               │
   │            Readout (sim / Boltz / dataset)
   │               │
   └──── update thesis + re-rank ◄─┘
                   │
            stop? (budget / confidence / clear lead)
```

The loop is **open at the bottom** in ToolUniverse's design (predict → stop); here it **closes**
through the readout step that feeds back into re-ranking.

---

## 3. Methods: multi-axis prioritisation

ToolUniverse's case study scores targets on essentially two axes — *tractability* and a *literature
search* — and then asks a human to pick. We replace that with an explicit, auditable scorer.

### 3.1 Evidence axes

Each candidate target is scored on multiple axes, each backed by specific tool calls:

| Axis | Question | Example evidence source |
| --- | --- | --- |
| **Genetic / causal** | Is there genetic support that this target drives the disease? | Open Targets associations, GWAS |
| **Tractability** | Can it be drugged (pockets, modality, precedent)? | Open Targets tractability |
| **Literature / novelty** | What is known; is this obvious or differentiated? | EuropePMC / PubMed search |
| **Safety / on- vs off-target** | Expression specificity; likely tox liabilities? | expression atlases, ADMET-AI |
| **Chemical matter** | Do tractable starting compounds exist? | ChEMBL similarity / known ligands |
| **Competitive / IP** | Is the space crowded; is there freedom to operate? | patent / clinical-precedent tools |

> The axis set is configurable per disease. The point is **comparability across the candidate
> set**, not an exhaustive single-target dossier.

### 3.2 Scoring and ranking

- Each axis yields a normalised sub-score with an attached **confidence** (evidence strength).
- A weighting scheme combines sub-scores into a target score; weights are explicit and tunable
  (and can themselves be a judgement the agent defends).
- Output is a **comparison matrix** (targets × axes) plus a ranked list with a written rationale
  per target — so a human can audit *why* the ranking is what it is, rather than being asked to
  make the call.

### 3.3 Why a scorer, not "ask the human"

Deferring to `expert_consult_human_expert` (as the reference case study does) hides the hardest
step. An explicit scorer (a) makes the decision reproducible, (b) exposes *which* evidence moved
the ranking, and (c) is what the refinement loop acts on. The human becomes a reviewer of a
defended decision, not the decision-maker of last resort.

---

## 4. Methods: closing the loop (pluggable readout)

A virtual biotech generates data. We don't need a wet lab for a working demo — we make the
**readout source pluggable** behind one interface, so the loop is real even when the data is
simulated:

- **Simulated oracle** — a stochastic model returns an assay-like readout; fastest to demo, lets
  us show the loop updating beliefs.
- **In-silico prediction as readout** — treat a Boltz-2 binding-affinity or ADMET-AI prediction
  *as* the experimental result that updates the ranking (this is the most ToolUniverse-native option).
- **Projected dataset** — ingest the conclusions of a real dataset as the "experimental evidence"
  for a target/compound, updating priors. (Carries over the dataset-projection idea from prior work.)

Each readout updates the relevant axis sub-score and confidence, and the orchestrator re-runs
prioritisation. The **critic** decides whether the new evidence resolved its earlier gap.

---

## 5. How we consume ToolUniverse

- Access tools via the **MCP server**; use **compact mode** / tool selection from the start so we
  expose a handful of discovery tools to Claude rather than 580+ schemas (context blow-up is the
  first failure mode to avoid).
- Claude is the reasoning engine across all agents; tool calls are structured and logged.
- We treat ToolUniverse purely as the **evidence/prediction layer** — our agents, scorer, loop,
  and readout adapters are the new surface area.

See [REFERENCES.md](REFERENCES.md) for each tool/model and its citation, and
[DIRECTIONS.md](DIRECTIONS.md) for where this can go.
