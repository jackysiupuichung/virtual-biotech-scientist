# What differentiates this project

A blunt assessment of where this project stands apart — and, just as important, where it does **not**,
so we plant the flag on the defensible ground.

## The one-sentence pitch

> Every other team will either **rank targets** or **generate molecules**. We built the **decision loop
> that sits above both**: a multi-objective arena ranks competing therapeutic hypotheses, a
> Value-of-Information selector identifies the single **most-informative experiment** to run next, an
> **MCP experiment interface actually runs it** — a frontier model computing on real data, not an API
> lookup — and the result flows back to re-rank. We close the loop the *Virtual Biotech* paper leaves open.

## Where we are NOT differentiated (so we don't pitch these as novel)

Honesty here keeps us credible with judges who know the field:

- **Multi-objective ranking / the arena** is the *frame*, and it's cheap — organising evidence by
  prioritisation axis and sorting. Useful, but not where the novelty lives.
- **Active learning / maximally-informative experiment selection** is **field-standard** —
  Genentech/Roche's "lab in the loop," Recursion, Isomorphic, and the AI Co-Scientist paper all do it.
  We build it because it's table stakes for a serious entry and rare *at a hackathon*, but it is not
  our headline.
- **Generative molecule design** — a crowded space; we don't compete there.

## Where we ARE differentiated (the flag)

Two things almost no hackathon team will have together:

### 1. The loop closes onto real computation, via an MCP experiment interface
The paper assesses each hypothesis **in isolation**; ToolUniverse **defers the pick to a human**;
AI Co-Scientist **ranks but doesn't act**. We **rank → act → re-rank**. The "act" is a single
`run_experiment` MCP call whose backend is *pluggable*, and at least one backend produces **genuine new
computation on real data** — not a database lookup. That reframes the hardest question ("where does the
experiment run?") into the thesis: **the experiment runs wherever the most-informative computation
lives, and a frontier model doing real inference IS the experiment.**

### 2. Frontier models as the "experiment"
The experiment backends are frontier scientific models, interchangeable behind one interface:
- **Boltz-2** — binding-affinity prediction for a ligand against the target (**the live demo backend**).
- **Single-cell on a real atlas** — specificity / malignant-localisation computation (CELLxGENE).
- **DNA/RNA language model** — Evo / Nucleotide Transformer scoring a sequence or variant.

> **Demo scope (honest):** the interface is universal and **all three are wired**, but **one is live**
> (Boltz-2) and the others are **registered stubs** behind the same interface. "All three wired, one
> live" is impressive and achievable; "all three live in 48h" is how teams ship nothing.

## The differentiation stack

| Layer | Role | Novelty |
| --- | --- | --- |
| **Arena** | organise evidence by axis → multi-objective sort | frame (cheap) |
| **VoI selector** | pick the single most-informative (hypothesis, axis) to resolve next | mechanism (field-standard, rare at a hackathon) |
| **MCP experiment interface** | one `run_experiment` call, pluggable backend | **architecture differentiator** |
| **Frontier-model backends** | Boltz-2 / single-cell / DNA-RNA LM = real computation *as* experiment | **headline — real data, real models** |
| **Re-rank** | result flows back; the leaderboard / Pareto front moves | closes the loop |

## The self-improving layer

On top of the experiment loop, the system improves along three axes it can defend (and names a fourth
it can't) — see [SELF_IMPROVING.md](SELF_IMPROVING.md):

- **answer** (the VoI loop — have it), **hypotheses** (mutate the losers — build a slice), **toolkit**
  (compose new tools on a gap — one scripted instance);
- **judgement** is the honest limit — it needs real trial outcomes we don't have in 48h.

## Explicitly cut (so we ship)

- **Drug-making / synthesis** → one [DIRECTIONS](DIRECTIONS.md) bullet, not a build.
- **Multiple live frontier-model skills** → exactly one live (Boltz-2); the rest stubbed-pluggable.
- **Patient stratification** → survives only as the *patient-stratum field* on the hypothesis card
  (already part of our unit of analysis), not a separate module.

## Demo risk note (Boltz-2)

Boltz-2 is the flashiest live backend but also the riskiest: diffusion-based, slow, GPU-hungry; a cold
run can take minutes per ligand. Mitigation, baked into the design: **pre-compute and cache** Boltz-2
results for the demo hypotheses; the live `run_experiment` call **falls back to cache** if a run
stalls. The leaderboard always moves on stage, live run or not.
