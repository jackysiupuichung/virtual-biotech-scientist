# Virtual Biotech Scientist

> A closed-loop, multi-agent AI scientist for drug-target discovery — built on top of
> [ToolUniverse](https://github.com/mims-harvard/ToolUniverse) and reasoned by Claude.

Most "AI scientist" pipelines today are **open-loop**: they retrieve knowledge, run an
in-silico prediction, narrate a summary, and stop. A real biotech doesn't stop there. It
forms a hypothesis, *chooses* between many candidate targets under uncertainty, designs an
experiment, reads out a result, and **revises its thesis**. This project builds that loop.

```
        ┌──────────────────── HYPOTHESIS REFINEMENT LOOP ────────────────────┐
        │                                                                     │
   Target ID  ──►  Prioritisation  ──►  Experiment design  ──►  Readout       │
   (evidence       (multi-axis            (downstream:           (pluggable:   │
    gathering)      scoring + rank)        tox, tractability,     sim / Boltz /│
        ▲                                  binding, ADMET)        dataset)     │
        │                                                            │        │
        └──────────────── refine: critic finds a gap ───────────────┘        │
        └─────────────────────────────────────────────────────────────────────┘
                                     │
                    ToolUniverse MCP (evidence + prediction layer)
            OpenTargets · ChEMBL · EuropePMC · ADMET-AI · Boltz-2 · …
```

## What we build on, and what we add

[ToolUniverse](https://aiscientist.tools) is an excellent **foundation**: a standardised
MCP-based protocol over 580+ biomedical tools (databases, APIs, and pretrained ML models),
usable from any LLM. We use it as our **evidence and prediction layer** rather than
reinventing data access.

On top of it, we add the parts a virtual biotech needs that a tool-access layer doesn't
provide on its own:

| Layer | Foundation (ToolUniverse) | What this project adds |
| --- | --- | --- |
| **Evidence** | 580+ retrieval + prediction tools via MCP | consume directly |
| **Prioritisation** | per-target dossiers; final pick left to a human expert | a **multi-axis scoring + ranking engine** that compares the candidate set and *makes* a defensible decision |
| **Loop** | linear, single-pass (predict → stop) | a **hypothesis-refinement loop**: a critic finds weak/conflicting evidence and triggers re-query + re-rank |
| **Data** | retrieval + in-silico prediction only | a **pluggable experimental readout** that closes the loop (simulated oracle, Boltz-2 affinity, or a projected real dataset) |

**New to drug discovery?** Start with [docs/DRUG_DISCOVERY_PRIMER.md](docs/DRUG_DISCOVERY_PRIMER.md)
— a plain-English orientation for non-scientists (pipeline, target ID, prioritisation, worked example).

See [docs/DESIGN.md](docs/DESIGN.md) for the architecture and methods,
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
│   ├── DESIGN.md             # architecture, workflow, methods
│   ├── REFERENCES.md         # tools, models, citations
│   └── DIRECTIONS.md         # potential directions / roadmap
├── agents/                   # (planned) target-id, prioritisation, critic, experiment-design
├── loop/                     # (planned) refinement-loop orchestrator
├── tools/                    # (planned) ToolUniverse MCP client + readout adapters
└── eval/                     # (planned) case studies, e.g. hypercholesterolemia
```
