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

## 2. Architecture — CSO + scientist divisions (after Zhang et al. 2026)

We adopt the paper's org structure: a **Chief Scientific Officer (CSO) agent** that receives a
query, decomposes it, delegates to **domain-specialist scientist-agent divisions**, and integrates
their evidence — with a **Scientific Reviewer** that audits the result and can **re-route** to fill a
gap. We then hand the integrated hypotheses to the **arena** for ranking (the paper stops at the
CSO's narrative integration; see [ARENA.md](ARENA.md)).

### 2.1 Roles

- **CSO agent (orchestrator)** — turns a scientific query into a briefing, a decomposition, and a
  routing plan; integrates division outputs via data-driven reasoning; states the final
  recommendation. Maintains a **traceable decision log** (every claim → the tool/evidence behind it).
- **Scientist divisions** — each a specialist that answers a sub-question using ToolUniverse tools:
  - **Target ID** — genetic/causal support, disease-cell localisation (single-cell specificity,
    malignant-vs-stroma), functional dependency.
  - **Target Safety** — expression specificity, essentiality, known liabilities, off-target risk.
  - **Modality** — druggability/tractability, structure, which modality (small molecule, antibody, ADC).
  - **Disease biology / literature** — mechanism, novelty, competitive landscape.
  - **Clinical** — prior trials, modality precedent.
  > A hackathon build runs a **subset** of these (Target ID + Safety + Modality + Clinical is plenty).
- **Scientific Reviewer** — audits the integrated evidence for gaps/conflicts and emits a **re-route**
  request (which division, which axis, which tool) — the paper's audit loop, and our refinement
  mechanism *before* a hypothesis enters the arena.

### 2.2 The CSO loop, then the arena

```
query ──► CSO: briefing + decompose + route
              │
              ▼
        scientist divisions  ──(ToolUniverse tools)──►  evidence per axis
              │
              ▼
        CSO integrates ──► Scientific Reviewer audits
              │                     │
              │ gap? ◄──────────────┘  re-route to a division to fill it
              ▼
        framed hypotheses (cards) ──►  PRIORITISATION ARENA  (see ARENA.md)
                                        head-to-head, multi-objective ranking
```

Two differences from the paper, both deliberate:

1. **The reviewer re-route loop** gives us refinement *within* assessment (gap → re-query), matching
   the paper's audit step — not a single open-loop pass.
2. **The arena replaces the paper's narrative "weigh the divisions" verdict** with a quantified,
   reproducible, multi-objective ranking. This is the contribution; everything above it is adopted.

---

## 3. Methods: prioritisation

The divisions produce **evidence per axis** for each hypothesis; the arena turns that into a ranking.
The full method — the competing objectives, the multi-objective (Pareto + tournament) ranking, the
match format, and the compute-budgeted loop — lives in **[ARENA.md](ARENA.md)**. The short version:

- Each hypothesis gets a **card**: score + confidence per axis (genetics, disease-cell localisation,
  tractability, safety, novelty, clinical precedent), each traceable to the division/tool behind it.
- Ranking is **multi-objective**, not a single collapsed score: **Pareto fronts** as the weight-free
  primary view, a **pairwise tournament** (Elo → Bradley–Terry) for a comparative leaderboard.
- A **compute-budgeted loop** spends the next match/evidence call where it most changes the rank
  (Value of Information), instead of gathering everything up front.

This is the delta from both prior systems: the paper and ToolUniverse assess each hypothesis **in
isolation** (and ToolUniverse defers the final pick to a human); the arena makes them **compete** and
produces a reproducible, auditable ranking.

---

## 4. Closing the loop with experiments (future direction)

The arena ranks on *available* evidence. The differentiating step is to **generate new evidence and
feed it back**: when the Value-of-Information selector ([ARENA.md §5](ARENA.md#5-compute-budgeted-loop-the-ai-scientist-part))
picks an axis that needs new computation, it dispatches a `run_experiment(hypothesis, axis)` call
through the **MCP experiment interface**, whose backend is pluggable — **Boltz-2** (live), single-cell
on a real atlas, or a DNA/RNA language model. A frontier-model computation on real data *is* the
experiment; its result updates the card and re-ranks. This is the project's headline — see
[DIFFERENTIATION.md](DIFFERENTIATION.md).

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
