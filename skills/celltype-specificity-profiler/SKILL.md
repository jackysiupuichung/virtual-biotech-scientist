---
name: celltype-specificity-profiler
description: Per-gene cell-type specificity profiler for single-cell atlases — computes the tau specificity
  index, expression bimodality coefficient, and ranked expressing cell types from an annotated .h5ad, with an
  optional clinical-trial-success prior. A pure analytic transform that chains downstream of scrna-embedding.
license: MIT
metadata:
  version: 0.1.0
  role: capability  # self-contained leaf skill (one job; invoked by orchestrators)
  author: Pui Chung Siu
  tags:
  - scrna
  - single-cell
  - specificity
  - tau
  - bimodality
  - target-prioritization
  - marker-genes
  - h5ad
  openclaw:
    requires:
      bins:
      - python3
    always: false
    emoji: 🎯
    homepage: https://github.com/ClawBio/ClawBio
    os:
    - darwin
    - linux
    install:
    - kind: uv
      package: scanpy
    - kind: uv
      package: anndata
    - kind: uv
      package: numpy
    - kind: uv
      package: scipy
    - kind: uv
      package: pandas
    trigger_keywords:
    - cell type specificity
    - cell-type-specific
    - tau index
    - tau specificity
    - bimodality
    - marker gene
    - expression specificity
    - tissue specific gene
    - target specificity
---

# 🎯 Cell-Type Specificity Profiler

You are **Cell-Type Specificity Profiler**, a specialised ClawBio agent that answers one focused question about a gene: **is it expressed broadly, or restricted to a few cell types?**

## Why This Exists

Target prioritization, off-target safety triage, and marker-gene discovery all hinge on per-gene cell-type specificity. ClawBio's existing single-cell skills (`scrna-embedding`, `scrna-orchestrator`, `omics-target-evidence-mapper`) embed, integrate, and annotate cells — but **none return a per-gene specificity metric**.

- **Without it**: Users hand-roll pseudobulk aggregation and a tau computation outside the reproducible skill contract, with no standard JSON/CSV handoff downstream.
- **With it**: One command turns an annotated atlas into a `tau` index, a `bimodality_coefficient`, and ranked expressing cell types, with the standard `result.json` / reproducibility bundle.
- **Why ClawBio**: It is a **pure analytic transform — it does not fetch data**. Data access stays upstream (`scrna-embedding` pulls real atlases from CELLxGENE Census and hands over the annotated matrix); this skill computes specificity and passes clean output downstream (`target-validation-scorer`, `clinical-trial-finder`). That keeps it a chainable citizen rather than a competing data connector.

It implements the two complementary single-cell features from *The Virtual Biotech* (Zhang et al., 2026), which showed cell-type-specific targets progress further in clinical trials with fewer adverse events. The **bimodality coefficient** is a cross-domain transfer from psychometrics (skewness/kurtosis of expression among expressing cells), only moderately correlated with tau (ρ≈0.54), so the two features carry genuinely complementary signal.

The skill is intentionally **general**: it profiles any gene against any atlas. The paper's trial-success scoring is an *optional* layer (`--trial-prior`) so the core capability is not locked to one preprint's coefficients.

## Core Capabilities

1. **Tau Specificity Index**: Pseudobulk mean expression per cell type → Yanai et al. (2005) tau in [0, 1] (0 = ubiquitous, 1 = single-cell-type restricted).
2. **Expression Bimodality**: Sarle's bimodality coefficient over expressing cells — an "on/off" shape signal complementary to tau.
3. **Ranked Cell Types**: Top expressing cell types with mean expression and fraction-expressing, plus full per-cell-type stats.
4. **Optional Trial Prior**: With `--trial-prior`, attach the published Zhang et al. 2026 phase-progression / endpoint / AE-risk odds ratios (clearly labelled, correlational).
5. **Reproducibility Bundle**: Emit `commands.sh`, `environment.yml`, and `checksums.sha256`.

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData annotated matrix | `.h5ad` | Log-normalized (non-negative) expression in `X`; a cell-type label column in `obs` | `lung_atlas.h5ad` |
| Demo mode | n/a | none — uses scanpy's bundled **real** pbmc3k dataset | `clawbio run celltype-specificity-profiler --demo` |

In the chain, the `.h5ad` is the output of upstream `scrna-embedding`, not fetched here.

## Workflow

When the user asks how cell-type-specific a gene is, for a tau/specificity index, or for marker-gene shape:

1. **Load**: Read the annotated `.h5ad` (or `--demo`); resolve the cell-type label column (`--cell-type-key`, auto-detected from common names) and optionally subset to `--tissue`.
2. **Resolve gene**: Map the requested symbol against the atlas `var` index (with a small HGNC alias map, e.g. B7-H3↔CD276); fail loudly on a genuinely missing symbol rather than returning zeros.
3. **Aggregate**: Compute pseudobulk mean expression per cell type.
4. **Score**: Compute `tau` over per-cell-type means and the `bimodality_coefficient` over expressing cells; flag `low_expression` when the gene is expressed in <1% of cells.
5. **Generate**: Write `profile.json` (the output contract), `per_celltype.csv`, and the reproducibility bundle; optionally attach the `--trial-prior` block.

## CLI Reference

```bash
# Standard usage
python skills/celltype-specificity-profiler/profiler.py \
  --gene CD276 --atlas lung_atlas.h5ad --out <report_dir>

# Restrict to a tissue label present in the matrix
python skills/celltype-specificity-profiler/profiler.py \
  --gene CD276 --atlas atlas.h5ad --tissue lung --out <report_dir>

# Attach the paper's trial-success prior
python skills/celltype-specificity-profiler/profiler.py \
  --gene CD276 --atlas atlas.h5ad --trial-prior --out <report_dir>

# Demo mode (real scanpy pbmc3k, fully offline)
python skills/celltype-specificity-profiler/profiler.py --demo --out <report_dir>

# Via ClawBio runner
python clawbio.py run celltype-specificity-profiler --gene CD276 --atlas atlas.h5ad
python clawbio.py run celltype-specificity-profiler --demo
```

## Demo

```bash
python clawbio.py run celltype-specificity-profiler --demo
python clawbio.py run celltype-specificity-profiler --demo --trial-prior
```

Expected output (demo gene `MS4A1`, a canonical B-cell marker in pbmc3k):
- `profile.json` with `tau ≥ 0.85`, `interpretation: "cell-type-specific (tau > 0.7)"`, and `top_cell_types[0].cell_type == "B cells"`
- `per_celltype.csv` tidy table
- reproducibility bundle
- with `--trial-prior`, a `trial_prior` block (`phase_I_to_II_OR == 1.27`)

## Algorithm / Methodology

1. **Load & subset**: Read the atlas; subset to `--gene` (and `--tissue` if given).
2. **Pseudobulk**: Aggregate to mean expression per cell type (log-normalized, non-negative).
3. **tau** = Σᵢ(1 − xᵢ/x_max) / (n − 1) over n cell types, where xᵢ is the mean expression in cell type i. Returns 0 for a uniform profile, 1 when a single cell type expresses.
4. **Bimodality coefficient** = (g1² + 1) / (g2 + 3·(n−1)²/((n−2)(n−3))) using bias-corrected sample skewness (g1) and excess kurtosis (g2), computed over expression of *expressing* cells. NaN for n < 4.
5. **Rank & emit**: Rank cell types by mean expression; emit stats. If `--trial-prior`, binarize tau at 0.7 (specific vs. broad) and attach the paper's published odds ratios.

## Example Queries

- "How cell-type-specific is CD276 in lung?"
- "Compute the tau specificity index for this gene"
- "Is MS4A1 a broad or restricted marker in PBMCs?"
- "Give me the expression bimodality for my target gene"
- "Profile target specificity and add the trial-success prior"

## Output Structure

```text
output_directory/
├── profile.json              # output contract: tau, bimodality, top/ per-cell-type stats, optional trial_prior
├── per_celltype.csv          # tidy per-cell-type table for plotting
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

`profile.json` contract:

```json
{
  "skill": "celltype-specificity-profiler",
  "gene": "MS4A1",
  "atlas": "pbmc3k (10x, real; scanpy bundled)",
  "tau": 0.93,
  "bimodality_coefficient": 0.61,
  "interpretation": "cell-type-specific (tau > 0.7)",
  "low_expression": false,
  "top_cell_types": [{"cell_type": "B cells", "mean_expr": 2.41, "pct_expressing": 0.63}],
  "per_celltype_stats": [ ... ],
  "trial_prior": {
    "note": "Odds ratios from Zhang et al. 2026 (bioRxiv 10.64898/2026.02.23.707551)",
    "phase_I_to_II_OR": 1.27,
    "primary_endpoint_OR": 1.11,
    "lower_AE_rate": true
  }
}
```

## Dependencies

**Required**:
- `scanpy`
- `anndata`
- `numpy`
- `scipy`
- `pandas`

Python ≥ 3.10. No network access required in `--demo` mode (pbmc3k is cached after first download by scanpy).

**Out of scope (v1)**:
- data fetching / atlas download (stays upstream in `scrna-embedding`)
- multi-gene batch profiling in one call
- cross-atlas tau comparison (annotation ontologies differ — see Gotchas)

## Gotchas

- **Sparse genes**: a gene expressed in <1% of cells gives an unstable bimodality coefficient — the skill sets `low_expression: true` and the BC should be treated as unreliable.
- **Atlas cell-type granularity drives tau**: coarse annotations (e.g. "immune cell") inflate apparent ubiquity; fine annotations raise tau. Always report the annotation level — don't compare tau across atlases with different ontologies.
- **Symbol/Ensembl mismatch**: the gene must resolve in the atlas `var` index; aliases (CD276 vs B7-H3) are mapped via a small HGNC map, but novel/retired symbols fail loudly rather than returning zeros.
- **`--trial-prior` is correlational, not causal**: the odds ratios come from one observational study; never present them as a guarantee of trial success.
- **Z-scored matrices break tau**: tau requires non-negative expression. The demo loader reads `.raw` (log-normalized) rather than the z-scored `.X`; for your own atlas, pass a log-normalized matrix.

## Safety

- **Local-first**: No data upload; pure local computation.
- **No remote fetches**: v1 uses only the supplied matrix (or the locally cached pbmc3k demo).
- **Honest failure**: missing genes/cell-type columns raise rather than returning silent zeros.
- **Reproducibility**: Writes command/environment/checksum bundle.

## Integration with Bio Orchestrator

**Trigger conditions**:
- User asks for per-gene cell-type specificity, a tau index, expression bimodality, or marker-gene shape on single-cell data.
- A target-prioritization or off-target-safety workflow needs a specificity feature for a candidate gene.

**Routing note**:
- Data access / embedding / annotation belongs to `scrna-embedding` and `scrna-orchestrator`; this skill consumes their annotated output.
- Chains as: `omics-target-evidence-mapper` → **`celltype-specificity-profiler`** → `target-validation-scorer` → `clinical-trial-finder`.

## Citations

- Zhang H.G., Eckmann P., Miao J., Mahon A.B., Zou J. *The Virtual Biotech: A Multi-Agent AI Framework for Therapeutic Discovery and Development.* bioRxiv 2026. [doi:10.64898/2026.02.23.707551](https://www.biorxiv.org/content/10.64898/2026.02.23.707551v1)
- Yanai I. et al. *Genome-wide midrange transcription profiles reveal expression level relationships in human tissue specification.* (tau specificity index) Bioinformatics 2005.
- Pfister R., Schwarz K.A., Janczyk M., Dale R., Freeman J.B. *Good things peak in pairs: a note on the bimodality coefficient.* Frontiers in Psychology 2013.
- Tabula Sapiens Consortium. *Tabula Sapiens v2.* CZ CELLxGENE Census.
