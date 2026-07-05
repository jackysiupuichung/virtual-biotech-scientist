# CSO ↔ ToolUniverse integration — design

**Goal.** Replace the CSO's hardcoded skill map with **runtime tool discovery +
composition** from ToolUniverse, so the CSO *designs a custom experiment per target*
instead of replaying a fixed step list.

## Division of labour

The CSO owns the *scientific reasoning structure*; ToolUniverse owns *finding,
composing, and running the instruments*. They meet at a small descriptor protocol.

| Concern | Owner |
| --- | --- |
| What to investigate — divisions, axes, reviewer gaps (Zhang et al. 2026 loop) | **CSO** |
| Which tool answers a sub-question | **ToolUniverse `Tool_Finder`** (embedding RAG) |
| How tools chain into an experiment (output→input) | **ToolUniverse `ToolGraphGenerationPipeline`** |
| Running a tool | **`execute_tool`** |

## The 3-verb agent protocol

The CSO harness is a plain Python program and cannot call MCP tools itself. So for
each routed sub-question it **emits a descriptor** and the driving agent (this Claude
Code session, or the frontend) executes it against the MCP ToolUniverse server, then
feeds the result back. Three verbs:

1. **find** — `{verb: "find", description: <sub-question>, limit: 5}`
   → agent runs `Tool_Finder` → returns ranked candidate tools (name + arg schema).

2. **compose** — `{verb: "compose", tool_configs: [<candidates>]}`
   → agent runs `ToolGraphGenerationPipeline` → returns a data-flow graph
   `{nodes, edges}`. The CSO topologically orders the axis's tools into a chain
   (e.g. `gwas_get_variants_for_trait` → `OpenTargets_get_variant_credible_sets`),
   so an axis that needs several tools runs them output→input, not in isolation.

3. **run** — `{verb: "run", tool_name, arguments}`
   → agent runs `execute_tool` → returns the tool payload; the CSO folds a compact
   summary into the evidence row.

A reviewer **re-route** is just a new `find` on the gap description — discovery is
the same mechanism whether it's an initial axis or a gap fill.

## Flow (replaces `decompose_and_route`'s fixed steps)

```
query ── parse ──▶ {gene, disease}
      │
      ▼
  planner: emit N sub-questions, one per division axis
      │
      ▼  (per sub-question)
   find ─▶ candidates ─▶ compose ─▶ ordered tool chain
                                        │
                                        ▼  (per tool in chain)
                                      run ─▶ evidence row
      │
      ▼
  reviewer panel ── gap? ──▶ find(gap) ─▶ compose ─▶ run ─▶ append
      │
      ▼
  synthesize report
```

The hardcoded 4-step B7-H3 plan is removed. The plan is now whatever sub-questions
the divisions raise for *this* target; the tool chain is whatever `find`+`compose`
return. That variability is the "custom experiment".

## Modes / determinism

- **Agent-driven (default).** Descriptors emitted; the agent executes. No local ML
  deps (`Tool_Finder` needs `torch`+`sentence_transformers`, which we don't bundle).
- **Offline cache (`tool_router.yaml`).** The 6–7 canonical axes keep a pinned tool +
  args, so the demo runs deterministically and offline without a `find` round-trip.
  Cache hit → skip discovery; cache miss → emit a `find` descriptor. This keeps the
  candidate `--demo` walkthrough byte-stable while novel axes still discover live.
- **In-process (optional).** If the `tooluniverse` package is importable, the same
  descriptors execute in-process (`ToolUniverse().run_one_tool(...)`) for a
  standalone live run.

## What changes in code

- `decompose_and_route` → `plan_axes(query)`: emit sub-questions + division tags, no
  fixed tool names.
- `execute_skill` live path → try, in order: (1) `tool_router.yaml` cache,
  (2) emit `find`→`compose`→`run` descriptors (agent) / execute in-process,
  (3) honest "deferred" descriptor.
- `tool_backend.py` gains `find_descriptor()`, `compose_descriptor()`,
  `run_descriptor()` and an in-process executor for each.
- Reviewer re-route emits a `find` on the gap instead of routing to a fixed skill.

## What the live loop proved

Running the loop against the real MCP ToolUniverse server (this agent as executor):

- **`Tool_Finder` (embedding) is unavailable** on a stock server — it needs
  `torch`/`sentence_transformers`. `Tool_Finder_Keyword` needs no ML deps, returns the
  same `{name, description, parameter}` shape, and works — so it's the DEFAULT finder.
- **Discovery reaches axes the static map can't.** The single-cell specificity axis
  (no `tool_router.yaml` entry) discovered `CellMarker_search_by_gene`,
  `GTEx_get_single_nucleus_expression`, and the SCXA atlas tools. Running
  `CellMarker_search_by_gene(gene_symbol=CD276)` returned real per-cell-type data
  (cancer cells in brain/breast/liver + normal stromal cells) — the exact
  malignant-vs-normal readout the axis needed. This is the custom-experiment payoff:
  the plan pulled a tool nobody pre-wired.
- **Arg-satisfiability matters.** `find` ranks tools by relevance, but the top hit may
  need an arg we can't supply (e.g. an experiment accession). `discover_and_run` picks
  the first ordered candidate whose *required* args are fillable from `{gene, disease,
  drug}`, falling back to the top — so it doesn't pick an unrunnable tool.

## Open risks

- Keyword discovery is shallower than embedding RAG; when the server has the ML deps,
  an executor may prefer `Tool_Finder`. The finder name is a parameter (`DEFAULT_FINDER`).
- `ToolGraphGenerationPipeline` makes LLM calls (data-flow inference) — cost/latency
  per novel axis; cache composed chains per axis signature.
- Arg-mapping: discovered tools have varied schemas. `find` returns the schema; the
  agent fills args from `{gene, disease, drug}` + the sub-question. Ambiguous slots
  are surfaced, not guessed.
