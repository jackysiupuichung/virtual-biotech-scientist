---
name: virtual-biotech-cso
description: Multi-agent therapeutic-target-assessment orchestrator — a Chief-of-Staff briefing, decomposition + routing across four scientific divisions, a Scientific-Reviewer audit that can re-route to fill a gap, and a synthesized report; reproduces the loop from The Virtual Biotech (Zhang et al. 2026) over ClawBio skills. The skill makes no LLM call; reasoning is delegated to the driving agent.
license: MIT
metadata:
  version: "0.1.0"
  role: orchestrator  # routes to and synthesizes capability skills (not a leaf skill)
  author: Jacky Siu
  domain: orchestration
  tags:
    - orchestration
    - multi-agent
    - target-assessment
    - drug-discovery
    - target-prioritization
    - reviewer-loop
    - virtual-biotech
  inputs:
    - name: query
      type: string
      format:
        - txt
      description: A therapeutic-target-assessment question, e.g. "Assess B7-H3 as a target in lung cancer".
      required: false
  outputs:
    - name: report
      type: file
      format:
        - md
      description: Synthesized assessment — recommendation, briefing, evidence chain, liabilities, residual uncertainty.
    - name: result
      type: file
      format:
        - json
      description: Machine-readable envelope — briefing, routing plan, per-step evidence, reviewer verdict, agent reasoning tasks.
  dependencies:
    python: ">=3.10"
    packages:
      - pyyaml
  endpoints:
    cli: python skills/virtual-biotech-cso/cso.py --query {query} --output {output_dir}
  openclaw:
    requires:
      bins:
        - python3
    always: false
    emoji: "🧬"
    homepage: https://github.com/ClawBio/ClawBio
    os:
      - darwin
      - linux
    install:
      - kind: uv
        package: pyyaml
    trigger_keywords:
      - therapeutic target assessment
      - assess target
      - target nomination
      - is this a good drug target
      - virtual biotech
      - multi-agent target assessment
      - CSO orchestrator
      - evaluate target
---

# 🧬 Virtual-Biotech CSO

You are the **Virtual-Biotech CSO**, a ClawBio orchestration agent for therapeutic-target assessment. Your role is to run the *Virtual Biotech* (Zhang et al. 2026) loop end-to-end: brief, decompose, route to specialist skills, audit with a reviewer, and synthesize a recommendation — without doing any of the underlying biology, and without calling an LLM from inside the skill.

## Trigger

**Fire this skill when the user asks for a target-level go/no-go assessment, e.g.:**
- "Assess B7-H3 as a therapeutic target in lung cancer"
- "Is <gene> a good drug target? Run the full evaluation."
- "Nominate / prioritise <gene> as a target and tell me the liabilities."
- "Run the virtual-biotech / CSO workflow on <target>."

**Do NOT fire when:**
- The user hands you a **file and wants it routed by type** (VCF, FASTQ, h5ad) → that is `bio-orchestrator`.
- The user wants a **single analysis** (just specificity, just trials, just GWAS) → call that one skill directly (`celltype-specificity-profiler`, `clinical-trial-finder`, `gwas-lookup`).
- The user wants to **run a single-cell pipeline** (clustering, markers) → `scrna-orchestrator`.

**Design note:** This is the *strategic* orchestrator (briefing → divisions → reviewer audit → synthesis), distinct from `bio-orchestrator` (the file/keyword router). `bio-orchestrator` routes target-assessment queries here.

## Why This Exists

ClawBio has the specialist skills (genetics, single-cell, safety, clinical) but no agent that runs the paper's *organisation*: a planning layer over them plus a review loop.

- **Without it**: Users manually pick skills, run them, eyeball the outputs, and decide if anything is missing — no briefing, no audit, no re-route.
- **With it**: One query yields a routed evidence chain plus a structured scaffold for the briefing, reviewer audit, and synthesis — in the standard `report.md` + `result.json` contract.
- **Why ClawBio**: Routing stays declarative (`routing.yaml`), execution stays in the validated skills, and — like `lit-synthesizer` — the skill itself calls no model. The reasoning roles are delegated to the **driving agent** (e.g. Claude Code), which can fan them out into subagents using the prompts in `prompts/`. No API key, no fabricated biology.

## Architecture (Virtual Biotech org chart)

This skill is the **CSO orchestrator**, not a peer of the leaf skills it calls. It mirrors the
Virtual Biotech (Zhang et al. 2026) organisation: a CSO delegates to **domain-specialised
scientist agents**, each of which runs its capability skills *and interprets* their output; a
**panel of reviewers** audits the findings; the CSO integrates. Agents run concurrently where free.

```
                          ┌─────────────────────────┐
   query ───────────────► │  Chief of Staff (agent)  │  briefing
                          └────────────┬─────────────┘
                          ┌────────────▼─────────────┐
                          │   Planner (agent)        │  proposes plan,
                          │   → validate vs routing  │  validated to real skills
                          └────────────┬─────────────┘
        ┌──────────────── division scientists (parallel agents) ───────────────┐
        │  Target ID 🧬     Target Safety 🛡     Modality 💊     Clinical 🩺     │
        │  each agent: run its capability skills (tools) → interpret → finding  │
        └──────────────────────────────┬───────────────────────────────────────┘
                          ┌─────────────▼────────────┐
                          │  Reviewer PANEL (4 agents)│  safety · genetics ·
                          │  parallel, ≥2 votes → loop│  specificity · clinical
                          └─────────────┬────────────┘ re-route → live Tavily, etc.
                          ┌─────────────▼────────────┐
                          │   CSO synthesis (agent)  │  integrate findings → GO/NO_GO
                          └──────────────────────────┘
   capability skills (leaf, no agents): gwas-lookup · celltype-specificity-profiler ·
   lit-synthesizer (live Tavily) · openfda-safety · tcga-somatic-profiler · … (the tools)
```

**Two kinds of thing, deliberately:** *capability skills* are pure tools (input→data→output, no
agents, callable standalone); this *orchestrator* has the agents and the control loop and consumes
those tools. They share the `skills/` directory but are not the same level — `role: orchestrator`
marks the distinction.

## Core Capabilities

1. **Chief-of-Staff briefing**: structures the pre-analysis briefing (field context, data availability, priority sub-questions); the driving agent fills it from `prompts/chief_of_staff.md`.
2. **Decompose & route**: split the query into division sub-questions (Target ID, Target Safety, Modality, Clinical) and bind each to a skill via `routing.yaml`.
3. **Execute (delegate)**: obtain each step's result from a routed ClawBio skill — real `clawbio run` in `--live`, else an honest "not executed" stub.
4. **Scientific-Reviewer audit**: structures the audit; the agent scores relevance / evidence / thoroughness and, on a gap, sets `re-route` — the skill then runs **one** follow-up step.
5. **Reviewer panel drives re-routes**: the LLM reviewer lenses vote on whether the evidence chain has a gap worth filling; a re-route verdict sends a follow-up sub-task to the `routing.yaml` skill bound to the missing axis (safety / specificity / genetics / tractability), and the loop converges once the panel is satisfied. *(This lean build omits the Prometheux/Vadalog structural gap-detector that also cast a non-silenceable engine vote; re-add `prometheux_reason.py` and restore the `_engine_gaps`/`_engine_decision` calls in `harness.py` to bring it back.)*
6. **Synthesis scaffold**: assembles the recommendation/liabilities scaffold for the agent to complete, and writes the `report.md` + `result.json` + `reproducibility/` bundle.

## Scope

**One skill, one task: orchestrating a target assessment.** It plans, routes, runs routed skills, and assembles the report scaffold. It performs no data fetch, no analysis, and no LLM call itself — every sub-question is delegated to another ClawBio skill, and every reasoning role is delegated to the driving agent.

## Workflow

1. **Brief** *(delegated)*: emit the Chief-of-Staff briefing slot; the driving agent runs `prompts/chief_of_staff.md`.
2. **Decompose & route** *(prescriptive)*: build the division sub-questions and resolve each skill from `routing.yaml` — do not invent skills or routes.
3. **Execute** *(prescriptive)*: obtain each step's result (ClawBio runtime with `--live`; else an honest "not executed" stub).
4. **Review** *(delegated)*: the agent runs `prompts/reviewer.md`; if the verdict is `re-route`, the skill executes exactly one follow-up step from the first gap, then stops looping.
5. **Synthesize** *(delegated)*: the agent writes the recommendation from `prompts/orchestrator.md`; the skill writes `report.md` + `result.json` (incl. an `agent_tasks` list naming each role + prompt) + a `reproducibility/` bundle.

## CLI Reference

```bash
# Assess your own target (default: routed steps left as honest stubs for the agent)
python skills/virtual-biotech-cso/cso.py --query "Assess MET as a target in NSCLC" --output <report_dir>

# Live: execute routed skills via the ClawBio runtime (deterministic; reasoning still delegated)
python skills/virtual-biotech-cso/cso.py --query "Assess B7-H3 ..." --live --output <report_dir>

# Via ClawBio runner
python clawbio.py run virtual-biotech-cso --query "Assess B7-H3 ..."
```

## Algorithm / Methodology

1. `case_key(query)` → `b7h3` for B7-H3, else a slug.
2. `decompose_and_route` builds five division sub-questions and resolves skills from `routing.yaml`.
3. Each step is resolved by `execute_skill`: live ClawBio run → honest stub (no LLM).
4. The reviewer verdict gates a single re-route (`_reroute_task` from the first gap).
5. The briefing / review / synthesis roles are emitted as delegation descriptors (`agent_tasks`) for a subagent-capable harness to execute.

**Key parameters**:
- Reviewer re-route: at most **one** pass (mirrors the paper's loop; avoids unbounded recursion).
- No model: the skill never imports an LLM SDK or reads an API key; reasoning is the agent's job.

## Example Queries

- "Assess B7-H3 potential as a therapeutic target in lung cancer"
- "Is OSMRβ a good target in ulcerative colitis? Run the full assessment."
- "Nominate MET for NSCLC and list the key liabilities"

## Example Output

`report.md` is a **target-identification dossier** with these sections:
Executive summary (Decision GO/CONDITIONAL_GO/REVIEW/NO_GO + Confidence) · Target overview ·
Evidence by division · Evidence strength · Liabilities & risks · **Evidence gaps** ·
**Proposed experiments to strengthen evidence** · **References & data sources** · Reproducibility.

```markdown
# Target Assessment — B7H3 · Assess B7-H3 potential as a therapeutic target in lung cancer

## Executive summary
- **Decision:** CONDITIONAL_GO
- **Confidence:** medium
B7-H3 (CD276) is a credible ADC target ... [step_03] ... advance conditional on the stromal-vs-malignant split.

## Evidence by division
| # | Division | Sub-question | Skill | Provenance | Grade | Key result | Ref |
|---|----------|--------------|-------|------------|-------|------------|-----|
| 3 | target_id | How cell-type-specific? | `celltype-specificity-profiler` | 🔧 live | strong | tau=0.93; cell-type-specific | [3] |

## Evidence gaps
- malignant-cell expression fraction not measured (specificity was stromal)

## Proposed experiments to strengthen evidence
- **spatial / tumour-cell single-cell profiling** — expected readout: B7-H3 on malignant vs stromal cells.

## References & data sources
3. **celltype-specificity-profiler** [🔧 live] — derived: tau + bimodality on the fetched atlas; atlas=CELLxGENE Census ...
```

Provenance markers: 🔧 live skill · 🌐 web · ⚪ absent. Every evidence row carries a `[n]`
reference resolved in the References section. *ClawBio is a research and educational tool; not a medical device.*

## Output Structure

```text
output_directory/
├── report.md                 # target-ID dossier: exec summary, evidence-by-division, gaps, proposed experiments, references
├── result.json               # envelope incl. references, evidence_gaps, proposed_experiments, decision/confidence
├── trace.jsonl               # (harness.py only) execution trace: one span per agent role + routed step,
│                             #   parent-linked, with latency + token usage; root span rolls up totals
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

### Execution trace (observability)

`harness.py` writes a `trace.jsonl` span tree alongside the report (`tracing.py`):
brief → plan → execute (one span per routed step) → review→re-route loop (each
reviewer pass + follow-up nested) → synthesize. Each agent span carries latency
and token usage; degradation moments (no backend / agent failure) land as
`status="stub"` spans, so the honest-fallback behaviour is visible too. Stdlib
only — no dependency, no key, written every run.

**Optional hosted UI (Langfuse):** install the extra and set keys to mirror the
same span tree to Langfuse (SDK v4):

```bash
pip install -e '.[tracing]'          # or: pip install 'langfuse>=4.0'
export LANGFUSE_PUBLIC_KEY=pk-...    # export LANGFUSE_SECRET_KEY=sk-...
export LANGFUSE_HOST=https://...     # optional; self-hosted instance
```

Absent either key the exporter is a silent no-op (≈0.06 ms overhead); the
`trace.jsonl` is written regardless. Agent spans map to Langfuse *generations*
(so token cost renders); loop/step spans map to plain spans.

## Dependencies

**Required**:
- `pyyaml` (routing map)

No LLM SDK and **no API key**. The skill is pure routing + report assembly; the Chief-of-Staff / Reviewer / synthesis reasoning is performed by the driving agent (its own session model), not by this skill.

## Gotchas

- **This skill never calls an LLM.** The model will want to "just call the API" for the briefing/review/synthesis. Do not — those roles are delegated to the driving agent via `prompts/`; the skill emits structured slots (`agent_tasks`).
- **The reviewer re-routes at most once.** The model will want to keep looping until "complete". Do not — one re-route pass is by design; report residual gaps instead of recursing.
- **Trial-success priors are correlational.** The model will want to say cell-type specificity *causes* trial success. Do not — the odds ratios (Zhang et al. 2026) are observational; never present them as a guarantee.
- **This is not the file router.** The model will want to fire this for "annotate my VCF". Do not — that is `bio-orchestrator`; this fires only for target-level assessment.

## Safety

- **Local-first**: routing + report assembly are local; live data access happens inside the validated ClawBio skills, not here.
- **No model, no key, no exfiltration**: the skill imports no LLM SDK and reads no API key; it cannot send data anywhere.
- **Disclaimer**: *ClawBio is a research and educational tool. It is not a medical device and does not provide clinical diagnoses. Consult a healthcare professional before making any medical decisions.*
- **No fabricated science**: missing backends produce honest `not executed` / `delegate-to-agent` stubs; results are never fabricated.
- **Audit trail**: every run writes a `commands.sh` / `environment.yml` / `checksums.sha256` bundle.

## Agent Boundary

The agent (LLM) dispatches this skill, **performs the reasoning roles** (Chief of Staff, Scientific Reviewer, CSO synthesis — ideally one subagent each, using the prompts in `prompts/`), and explains the output. The skill (Python) plans, routes, runs routed skills, and assembles the report — it does **not** call a model, invent skill results, override the reviewer verdict, add re-route passes, or upgrade correlational priors to causal claims.

## Chaining Partners

Routes (via `routing.yaml`) to the division skills and consumes their structured output:
- **Target ID**: `gwas-lookup`, `fine-mapping`, `scrna-embedding`, **`celltype-specificity-profiler`**, `crispr-screen-triage`
- **Target Safety**: `pathway-enricher`, `turingdb-graph`, `clinpgx`, `celltype-specificity-profiler`
- **Modality**: `struct-predictor`, `omics-target-evidence-mapper`
- **Clinical**: `clinical-trial-finder`
- **Re-route / stretch**: `scrna-orchestrator` (spatial), `equity-scorer` (HEIM)

Upstream, `bio-orchestrator` routes target-assessment queries into this skill.

## Maintenance

- **Review cadence**: whenever a routed skill is renamed/added — update `routing.yaml`.
- **Staleness signals**: a `routing.yaml` skill no longer exists in the catalog; the Zhang et al. priors are superseded; a routed skill's CLI contract changes.
- **Deprecation criteria**: retire if ClawBio adds a native multi-agent assessment loop, or fold the divisions into `bio-orchestrator` if it gains a reviewer stage.

## Citations

- Zhang H.G., Eckmann P., Miao J., Mahon A.B., Zou J. *The Virtual Biotech: A Multi-Agent AI Framework for Therapeutic Discovery and Development.* bioRxiv 2026. doi:10.64898/2026.02.23.707551
- Yanai I. et al. *…tissue specification* (tau specificity index). Bioinformatics 2005.
