# References: tools, models, and data sources

This project is an **agentic layer** over existing scientific tools. This document records what
each tool/model is, how we use it, and its citation. Verify version-specific details (tool counts,
endpoints) at build time — the ecosystem moves fast.

---

## Foundation: ToolUniverse

- **What:** An ecosystem for building AI scientist systems from any LLM. Standardises how an agent
  identifies and calls tools, integrating **580+** ML models, datasets, APIs, and scientific
  packages (count per the hypercholesterolemia case-study notebook; the project advertises 1000+
  models/tools overall — confirm current figure at build time).
- **Interfaces:** native **MCP server** (with configurable transport and tool selection),
  Python SDK, and a `tu` CLI. **Compact mode** reduces 1000+ tools to a few discovery tools to
  conserve context window.
- **From:** Zitnik Lab, Harvard (mims-harvard).
- **Use here:** our evidence + prediction layer (we do not reimplement data access).
- **Paper:** "Democratizing AI scientist systems using ToolUniverse" (preprint).
- **Links:** https://github.com/mims-harvard/ToolUniverse · https://aiscientist.tools

### Reference case study reviewed
We reviewed the official **hypercholesterolemia** Colab (ToolUniverse + Gemini 2.5 Pro). Its
target-selection flow: get associated targets (Open Targets) → tractability per target → EuropePMC
literature per target → narrate dossiers → **`expert_consult_human_expert` picks HMGCR**. Downstream
sections use ChEMBL similarity, ADMET-AI (BBB penetrance), and Boltz-2 (binding affinity). It is
in-silico and open-loop (no experimental data generated, final prioritisation deferred to a human) —
which is precisely the surface this project extends.

## Related agent system: TxAgent

- **What:** An AI agent for **therapeutic reasoning** over a toolbox of ~211 tools; does multi-step
  reasoning with real-time biomedical retrieval and *iterative* refinement of treatment
  recommendations.
- **Note:** its iteration is for drug–drug interactions / patient-level contraindications, **not**
  target prioritisation — complementary to, not overlapping with, our prioritisation loop.
- **Links:** https://github.com/mims-harvard/TxAgent

---

## Data / retrieval tools (via ToolUniverse)

- **Open Targets** — disease↔target associations and **target tractability** (pockets, modality,
  precedent). Core inputs to the genetic/causal and tractability axes. https://www.opentargets.org
- **ChEMBL** — bioactivity database; we use similarity search (e.g. Tanimoto) to find chemical
  matter / structural analogs. https://www.ebi.ac.uk/chembl/
- **EuropePMC / PubMed** — literature search for the novelty/literature axis.
  https://europepmc.org · https://pubmed.ncbi.nlm.nih.gov

## Prediction models (via ToolUniverse)

- **ADMET-AI** — ML prediction of ADMET properties (e.g. blood-brain-barrier penetrance) from SMILES;
  feeds the safety/off-target axis and the experiment/readout step.
- **Boltz-2** — open biomolecular foundation model predicting **complex structure and binding
  affinity**; reported to approach FEP accuracy ~1000× faster. MIT-licensed (academic + commercial).
  A candidate **readout source** for closing the loop.
  bioRxiv 2025, doi:10.1101/2025.06.14.659707 · https://github.com/jwohlwend/boltz

---

## Reasoning engine

- **Claude (Anthropic)** — the LLM driving all agents (target-ID, prioritisation, critic,
  experiment-design). ToolUniverse supports Claude natively via MCP. Anthropic is a hackathon
  co-host/sponsor. Use the latest, most capable Claude models for the reasoning layer.

---

## A note on "experimental data"

None of the foundation tools generate **wet-lab** data; they retrieve knowledge or run in-silico
predictions. Our closed loop therefore treats a **readout source** as pluggable — a simulated
oracle, an in-silico prediction (Boltz-2 / ADMET-AI) used *as* a result, or a projected real
dataset. See [DESIGN.md §4](DESIGN.md#4-methods-closing-the-loop-pluggable-readout).
