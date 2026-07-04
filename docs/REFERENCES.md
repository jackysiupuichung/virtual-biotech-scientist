# References: tools, models, and data sources

This project is an **agentic layer** over existing scientific tools. This document records what
each tool/model is, how we use it, and its citation. Verify version-specific details (tool counts,
endpoints) at build time — the ecosystem moves fast.

---

## Framework we extend: The Virtual Biotech

- **What:** A multi-agent AI framework for therapeutic discovery that mirrors a human research org —
  a **CSO agent** receives queries, delegates to **domain-specialist scientist-agent divisions**
  (statistical genetics, functional genomics, pathways/interactions, chemoinformatics, disease
  biology, clinical), and integrates their outputs via data-driven reasoning; human-in-the-loop
  throughout.
- **Showcased on:** clinical-trial genomic-feature analysis (out of scope for us), a **B7-H3 lung
  cancer** target evaluation proposing an ADC strategy, and an **OSMRβ** terminated-trial failure
  analysis.
- **Key limitation we address:** its assessment is **absolute and per-hypothesis** — each candidate
  gets a narrative evidence dossier weighed in isolation; **there is no head-to-head comparison or
  reproducible ranking.** Our [prioritisation arena](ARENA.md) supplies exactly that.
- **From:** Zhang, Eckmann, Miao, Mahon, Zou — Stanford (James Zou lab).
- **Cite:** Zhang H.G., Eckmann P., Miao J., Mahon A.B., Zou J. "The Virtual Biotech: A Multi-Agent AI
  Framework for Therapeutic Discovery and Development." bioRxiv 2026, doi:10.64898/2026.02.23.707551.
  https://www.biorxiv.org/content/10.64898/2026.02.23.707551v1

## Ranking precedents the arena builds on

- **AI Co-Scientist (Google, 2025)** — multi-agent system whose **Ranking agent** runs an
  **Elo tournament** of hypotheses via pairwise LLM "scientific debates"; the closest precedent for
  our arena. Gottweis, Natarajan et al., arXiv:2502.18864. *(Confirm Elo constants from the PDF
  before citing exact numbers.)*
- **LMArena / Chatbot Arena** — Elo for live ranking, **Bradley–Terry** for the stable published
  board with confidence intervals; the pattern we follow for the final leaderboard.
  Chiang et al., arXiv:2403.04132.
- **LLM pairwise target prioritisation — our closest eval precedent (Adaszewski & Schindler,
  medRxiv 2025)** — Gemini 2.5 Pro ranks **522 AD targets** across **6 criteria** by **pairwise
  comparison** (QuickSort with the LLM as comparator), integrated via **Pareto fronts + a
  utopia-point** ranking. Validates against **known clinical-trial targets** (44 of the 522) via
  **AUGC** (area under the gain curve): web-augmented **AUGC ≈0.72**, matching Open Targets;
  **pairwise beats pointwise** with large effect sizes. We adopt their **ground-truth design (AUGC
  enrichment of clinical-trial targets)** and their **pairwise-vs-pointwise** axis directly.
  **What they leave open — our contribution:** (1) they do *not* measure pairwise
  **transitivity/consistency** (only randomise order across 16 runs); (2) no **budgeted VoI**
  evidence loop (one-shot sort); (3) safety & competitive-landscape were their weakest, unstable
  criteria (they recommend hybrid LLM + structured data — what our ToolUniverse layer provides).
  Cite: Adaszewski S., Schindler T. "Large Language Model-Driven Prioritization of Alzheimer's
  Disease Drug Targets Across Multidimensional Criteria." medRxiv 2025,
  doi:10.64898/2025.12.28.25343106.
  https://www.medrxiv.org/content/10.64898/2025.12.28.25343106v1
- **Multi-objective / VoI foundations** — Pareto optimality; Value of Information (Howard 1966);
  Bayesian optimal experimental design (Chaloner & Verdinelli 1995; Rainforth et al. 2024). These
  ground the multi-objective ranking and the compute-budgeted loop.

---

## Tool layer: ToolUniverse

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

- **Claude (Anthropic)** — the LLM driving all agents (CSO, scientist divisions, Scientific Reviewer,
  arena judges). ToolUniverse supports Claude natively via MCP. Anthropic is a hackathon
  co-host/sponsor. Use the latest, most capable Claude models for the reasoning layer.

---

## A note on "experimental data"

None of the foundation tools generate **wet-lab** data; they retrieve knowledge or run in-silico
predictions. Our closed loop therefore treats a **readout source** as pluggable — a simulated
oracle, an in-silico prediction (Boltz-2 / ADMET-AI) used *as* a result, or a projected real
dataset. See [DESIGN.md §4](DESIGN.md#4-closing-the-loop-with-experiments).
