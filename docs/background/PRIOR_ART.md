---
name: prior-art-llm-target-prioritization
description: Prior art for LLM-based therapeutic target prioritization + Pareto fronts; what is taken vs. still open for a publishable claim (as of 2026-07)
metadata: 
  node_type: memory
  type: reference
  originSessionId: 11d80c3a-46ef-4a99-af24-69e54a83e23c
---

Lit review (2026-07-04) for the comparison-based multi-agent Pareto-front target-prioritization system in `comparison_based_multi_agent_pareto_system.md`. Question was whether "iterative LLM loop proposing experiments to break the Pareto front" is novel, and whether it's been applied to target prioritization.

## Verdict: core mechanism NOT novel; the specific closed-loop is still open

### Prior art that IS taken (do not claim these as novel)
- **Closed-loop propose→experiment→refine LLM scientists**: Dolphin (arXiv:2501.03916, ACL 2025), LLM-AutoSciLab (arXiv:2605.24043 — explicitly "hypothesis-conditioned experiment selection to resolve uncertainty"), InternAgent (arXiv:2505.16938).
- **Value-of-Information / Expected Information Gain** for choosing experiments = Bayesian Optimal Experimental Design (decades old); active learning for drug discovery is the applied form.
- **Pairwise > absolute LLM scoring** (calibration drift): arXiv:2403.16950, LLM-as-jury 2602.16610, Bradley-Terry/Elo aggregation, Pair2Score.
- **LLM target prioritization is a CROWDED 2025-26 space**: TargetBench 1.0 (biorxiv 2025.06.10.658988) multi-axis scoring; multi-agent debate/majority-voting/adjudication prioritization (medRxiv 2025.08.11.25333429); OriGene self-evolving multi-agent target ID; two-stage prioritize→validate (biorxiv 2025.09.17.676837).

### NEAREST NEIGHBOR (the paper a reviewer will use to reject) — AD-Pareto
"LLM-Driven Prioritization of Alzheimer's Disease Drug Targets Across Multidimensional Criteria", medRxiv 2025.12.28.25343106 (Dec 2025). VERY close:
- Gemini 2.5 Pro + web search over 522 AD targets.
- BOTH large-scale **pairwise comparative evaluation** AND pointwise scoring. (So pairwise+multi-axis is already published.)
- **Six criteria**: biological confidence, technical feasibility, clinical developability, patient impact, competitive landscape, safety — almost 1:1 with our six axes.
- **Uses Pareto fronts + utopia-point scoring (TOPSIS-like scalarization)** for multi-objective integration.
- Authors: Adaszewski & Schindler, **Roche** Pharma R&D Basel. Local copy: `docs/background/papers/2025.12.28.25343106v1.full.pdf`.
- Ground truth = known AD clinical-trial targets (OpenTargets). Metric = **normalized Area Under the Gain Curve (AUGC)** = early-recall of trial targets. 16 replicate runs/criterion. (Note: our repo eval already uses AUGC + gain curves — SAME metric family.)
- Pairwise implemented as **LLM-driven QuickSort** (LLM = comparative oracle, O(n log n) calls). Pairwise beat pointwise on 5/6 criteria (big Cohen's d); competitiveness & safety were the weak/noisy criteria.
- Pareto = classic dominance (non-dominated across all 6); front is large so they add **utopia-point/TOPSIS scalarization** (Euclidean distance to ideal percentile vector) to force a total order. Plus a "Pareto efficiency score."

CONFIRMED after reading full text (23pp): **produces a STATIC ranking and STOPS.** No closed loop, no experiment proposal, no VoI-driven acquisition, no evidence-gap-vs-genuine-tradeoff distinction. Their front is a means to a total ranking, NOT something to actively collapse.
- Their Future Work explicitly LISTS these as open (so they're claimable, but you're now on record they thought of the directions):
  - "future work might explore **active-learning strategies to select only the most informative comparisons**" (about comparison efficiency, NOT about experiments to resolve dominance — subtle but important gap remains ours);
  - "Iterative co-evaluation with experts" (human adjudication, not experiment proposal);
  - "Automated portfolio simulation ... go/no-go decision support" (named, not built).
- They FLATTEN the front with a scalarizer (utopia point). We do the OPPOSITE: keep the partial order and break ties with experiments. That contrast is the cleanest framing for a paper.

Second neighbor (more distant): PMC12637838 — AD drug repurposing via LLM sentiment over PubMed + ensemble model aggregation; NO Pareto, NO closed loop, static.

### What is STILL OPEN (the defensible novelty budget), ranked
1. **Comparison-native VoI / active front-collapse** (strongest — nobody closes this loop): treat the unresolved Pareto front as information-acquisition decisions; propose+rank experiments by expected probability of flipping a specific axis-level dominance ambiguity; metric = dominance edges resolved per unit experiment cost.
2. **Evidence-gap vs. genuine-trade-off routing** (strong): only `insufficient_evidence` ties are breakable by experiments; `genuine trade-off` ties never are. Route only the former into the loop. Our current §9 collapses both into `tradeoff_or_unresolved` — fixing that split IS part of the contribution.
3. **Auditable experiment→resolved-edge provenance graph** (weak as research; engineering value).

### Publishability bar (method paper, not architecture paper)
Accepted on a BENCHMARK, not the design. Need a **retrospective eval**: targets with known validation outcomes, hide evidence, show VoI loop reaches correct front in FEWER proposed experiments than (a) random experiment choice, (b) static-front baseline (= the AD-Pareto approach), (c) naive absolute scoring. Headline metric = experiments-to-resolution / front-collapse efficiency, NOT accuracy. Plus an ablation proving the evidence-gap/trade-off split matters. Without the benchmark it's a workshop/systems paper.

### Rank-first vs dominance-first front construction (verified 2026-07-04, run wf_7bf6d238-988)
Considered switching the arena from dominance-first (Pareto from noisy per-pair verdicts, front bloats) to rank-first (rank each axis to a total order, then Pareto on rank vectors). Deep-research verdict: **rank-first is fully anticipated, adopt it as the standard choice, don't claim it.**
- General MCDA/MOO primitive: **ranking-dominance** (Kukkonen & Lampinen, IEEE CEC 2007, doc 4424990) — rank per objective to beat curse-of-dimensionality / front bloat; **COPA** (arXiv 2503.14321) — per-axis CDF/rank-normalization to make axes comparable before Pareto.
- Pairwise→ranking→Pareto hybrid also published: **MO-IRL** (arXiv 2505.11864) uses Bradley-Terry/Plackett-Luce preferences → vector rewards → Pareto front.
- AD-Pareto already IS rank-first-from-pairwise (QuickSort oracle) in our exact application → switching toward it moves us CLOSER to the nearest neighbor, not away. So spend novelty budget entirely on the VoI loop + evidence-gap/trade-off split (the parts AD-Pareto lacks). Note: AD-Pareto uses QuickSort verdict-splitting, NOT a rigorous BT/Elo win-matrix fit — a BT-aggregated per-axis ranking is a marginally less-occupied variant but not a real novelty claim.
- Full write-up: `docs/method/RANK_FIRST_VS_DOMINANCE_FIRST.md`.

See also [[comparison-pareto-system-design]] if/when that project memory is written.
