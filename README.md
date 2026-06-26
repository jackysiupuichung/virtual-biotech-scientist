# Virtual Biotech Scientist

> A multi-agent AI scientist for drug-target discovery that **ranks competing therapeutic
> hypotheses in an arena** — built on the *Virtual Biotech* framework (Zhang et al. 2026),
> with [ToolUniverse](https://github.com/mims-harvard/ToolUniverse) as the tool layer and
> Claude as the reasoning engine.

This project stands on two pieces of prior work and adds one thing they lack:

- **[The Virtual Biotech](https://www.biorxiv.org/content/10.64898/2026.02.23.707551v1)**
  (Zhang, Eckmann, Miao, Mahon, Zou — Stanford, 2026) — a **CSO agent** orchestrating
  domain-specialist **scientist-agent divisions** that mirror a real therapeutics org. We adopt
  this org structure. Its assessment, however, is **absolute and per-hypothesis**: each candidate
  gets a narrative evidence dossier weighed in isolation — *there is no head-to-head comparison.*
- **[ToolUniverse](https://github.com/mims-harvard/ToolUniverse)** — the standardised tool layer
  (databases + in-silico models via MCP) the scientist agents call.

**What we add: the prioritisation arena.** We convert the paper's qualitative "weigh the divisions"
step into a **quantified, reproducible ranking** — competing **(target × disease × modality)
hypotheses** are pitted head-to-head, judged by a panel of division agents, and ranked as a
**multi-objective optimisation** (no single score: Pareto fronts across efficacy, safety,
tractability, novelty). A compute-budgeted loop spends evidence-gathering where it most changes the
ranking. See [docs/ARENA.md](docs/ARENA.md).

```
   query: "best target for lung cancer?"
        │
        ▼
   ┌─────────┐   delegates      ┌──────────────────────────────────────────┐
   │   CSO    │ ───────────────► │  SCIENTIST-AGENT DIVISIONS                │
   │  agent   │                  │   Target ID · Target Safety · Modality ·  │
   │          │ ◄─────────────── │   Disease biology · Clinical              │
   └────┬─────┘   evidence       └───────────────────┬──────────────────────┘
        │                                            │ tools
        │         ┌──────────────────┐               ▼
        │         │ Scientific       │      ToolUniverse MCP
        │ ◄─────► │ Reviewer (audit, │   OpenTargets · ChEMBL · EuropePMC ·
        │  gap →  │  re-route gap)   │   ADMET-AI · Boltz-2 · single-cell · …
        │  re-run └──────────────────┘
        ▼
   ┌────────────────────── PRIORITISATION ARENA ──────────────────────┐  ← our contribution
   │  competing (target × disease × modality) hypotheses              │
   │  pitted head-to-head → panel of division judges → ranked as a    │
   │  MULTI-OBJECTIVE optimisation (Pareto fronts, not one score)     │
   │  compute-budgeted: spend matches/evidence where rank is decided  │
   └──────────────────────────────────────────────────────────────────┘
```

## What we build on, and what we add

| Layer | Foundation | What this project adds |
| --- | --- | --- |
| **Org / agents** | Virtual Biotech (Zhang 2026): CSO → scientist divisions → reviewer loop | adopt directly (lighter, fewer divisions for a hackathon) |
| **Tools** | ToolUniverse: standardised MCP layer over 580+ databases + in-silico models | consume as the evidence layer |
| **Prioritisation** | both systems assess each hypothesis **in isolation** (narrative dossier; no comparison) | a **head-to-head arena** that produces a quantified, reproducible ranking |
| **Ranking method** | single weighed verdict / human pick | **multi-objective optimisation** — Pareto fronts across efficacy/safety/tractability/novelty, not one collapsed score |
| **Compute** | static, single-pass | **budgeted information-maximisation loop** — spend the next match/evidence call where it most changes the rank (VoI) |

> The unit ranked is a **therapeutic hypothesis** — *target × disease × modality × mechanism ×
> patient stratum* (e.g. "B7-H3, via an ADC, in LUAD, exploiting stromal overexpression") — exactly
> what the paper *outputs* and what an arena can compare. Not a bare gene.

**New to drug discovery?** Start with [docs/DRUG_DISCOVERY_PRIMER.md](docs/DRUG_DISCOVERY_PRIMER.md)
— a plain-English orientation for non-scientists (pipeline, target ID, prioritisation, worked example).

**What sets this apart:** see [docs/DIFFERENTIATION.md](docs/DIFFERENTIATION.md) — the loop closes onto
**real computation** via an MCP `run_experiment` interface (Boltz-2 live; single-cell + DNA/RNA-LM
pluggable), driven by a Value-of-Information selector. We rank → act → re-rank, closing the loop the
paper leaves open.

See [docs/DESIGN.md](docs/DESIGN.md) for the CSO/division architecture,
[docs/ARENA.md](docs/ARENA.md) for the prioritisation arena (the core build),
[docs/INFORMATION_MAXIMISATION.md](docs/INFORMATION_MAXIMISATION.md) for where Value-of-Information
lives (rank continuously, collect only what could change the rank),
[docs/SELF_IMPROVING.md](docs/SELF_IMPROVING.md) for the self-improving-scientist angles (improve the
answer, the hypotheses, and the toolkit),
[docs/REFERENCES.md](docs/REFERENCES.md) for tools and citations, and
[docs/DIRECTIONS.md](docs/DIRECTIONS.md) for potential directions.

## Status

Design-stage. This repository currently contains documentation only; the implementation
spine is built at the event.

## Repo layout (planned)

```
virtual-biotech-scientist/
├── README.md                 # this file
├── docs/
│   ├── DRUG_DISCOVERY_PRIMER.md  # plain-English domain context for non-scientists
│   ├── DESIGN.md             # CSO + scientist-division architecture
│   ├── ARENA.md              # the prioritisation arena (core build)
│   ├── REFERENCES.md         # tools, models, citations
│   └── DIRECTIONS.md         # potential directions / roadmap
├── cso/                      # (planned) CSO orchestrator + reviewer re-route loop
├── divisions/               # (planned) scientist agents: target-id, safety, modality, clinical
├── arena/                    # (planned) match scheduler, panel judge, Pareto ranker
├── tools/                    # (planned) ToolUniverse MCP client
└── eval/                     # (planned) case studies (B7-H3 lung cancer)
```
