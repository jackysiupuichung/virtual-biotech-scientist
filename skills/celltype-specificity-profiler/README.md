# celltype-specificity-profiler

> A ClawBio skill: given a gene, report how cell-type-specific its expression is across a single-cell atlas — tau specificity index, expression bimodality, and the cell types that drive it.

**Status:** candidate upstream PR to [ClawBio](https://github.com/ClawBio/ClawBio) · built at the ClawBio Hackathon (Agentic Genomics @ King's, 18 Jun 2026).

---

## Why this exists

Target prioritization, off-target safety triage, and marker-gene discovery all hinge on one question: **is this gene expressed broadly, or restricted to a few cell types?** ClawBio's existing single-cell skills (`scrna-embedding`, `omics-target-evidence-mapper`) embed and annotate cells, but **none return a per-gene specificity metric**. This skill fills that gap.

**It is a pure analytic transform — it does not fetch data.** Data access stays where it belongs: an upstream ClawBio skill (`scrna-embedding`, which pulls real atlases from CELLxGENE Census) hands this skill the annotated expression matrix, and this skill computes the specificity metrics and passes them downstream (`target-validation-scorer`, `clinical-trial-finder`). That keeps it a clean, chainable ClawBio citizen rather than a competing data connector.

It implements the two complementary single-cell features from *The Virtual Biotech* (Zhang et al., 2026), which showed that cell-type-specific targets progress further in clinical trials with fewer adverse events. The **bimodality coefficient** in particular is a cross-domain transfer from psychometrics (skewness/kurtosis of expression among expressing cells) that is only moderately correlated with tau (ρ≈0.54) — so the two features carry genuinely complementary signal.

The skill is intentionally **general**: it profiles any gene against any atlas. The paper's trial-success scoring is an *optional* layer (`--trial-prior`), so the core capability isn't locked to one preprint's coefficients.

## What it computes

| Output | Meaning |
|---|---|
| `tau` | Cell-type specificity index, 0 (ubiquitous) → 1 (restricted to one cell type) |
| `bimodality_coefficient` | "On/off" expression shape among expressing cells (from skewness + kurtosis) |
| `top_cell_types` | Ranked cell types by mean expression, with fraction-expressing |
| `per_celltype_stats` | Mean/median expression, % expressing, n cells, per cell type |
| `trial_prior` *(optional)* | Phase-progression / endpoint / AE-risk odds ratios from Zhang et al. 2026 |

## Inputs

| Field | Required | Notes |
|---|---|---|
| `--gene` | yes | HGNC symbol (e.g. `CD276`) |
| `--atlas` | yes* | `.h5ad` annotated expression matrix — **in the chain this is the output of upstream `scrna-embedding`**, not fetched here |
| `--cell-type-key` | no | `obs` column holding cell-type labels (default `cell_type`) |
| `--tissue` | no | Restrict to a tissue label present in the matrix |
| `--trial-prior` | no | Also emit clinical-trial-success priors (labeled, citation-attached) |
| `--demo` | no | Run on a small **real** public fixture (a downloaded slice / scanpy `pbmc3k`) standing in for upstream output — no synthetic data |

\* required unless `--demo`.

## Usage

```bash
# Offline demo (bundled B7-H3 / CD276 data) — no inputs needed
clawbio run celltype-specificity-profiler --demo

# Profile a gene against your own atlas
clawbio run celltype-specificity-profiler --gene CD276 --atlas lung_atlas.h5ad

# Add the paper's trial-success prior
clawbio run celltype-specificity-profiler --gene CD276 --trial-prior

# As a Python library
from clawbio import run_skill
run_skill("celltype-specificity-profiler", gene="CD276", demo=True)
```

## Example output (`--demo`, abbreviated)

```json
{
  "gene": "CD276",
  "atlas": "tabula-sapiens-v2 (demo subset)",
  "tau": 0.78,
  "bimodality_coefficient": 0.61,
  "interpretation": "cell-type-specific (tau > 0.7)",
  "top_cell_types": [
    {"cell_type": "fibroblast", "mean_expr": 2.41, "pct_expressing": 0.63},
    {"cell_type": "endothelial cell", "mean_expr": 1.12, "pct_expressing": 0.29}
  ],
  "trial_prior": {
    "note": "Odds ratios from Zhang et al. 2026 (bioRxiv 10.64898/2026.02.23.707551)",
    "phase_I_to_II_OR": 1.27,
    "primary_endpoint_OR": 1.11,
    "lower_AE_rate": true
  }
}
```

## Algorithm (replicable without this code)

1. Load the atlas; subset to `--gene` (and `--tissue` if given).
2. Aggregate to **pseudobulk mean expression per cell type** (log-normalized).
3. **tau** = Σ(1 − xᵢ/x_max) / (n − 1), over n cell types, where xᵢ is mean expression in cell type i.
4. **Bimodality coefficient** = (skew² + 1) / (kurtosis + 3·(n−1)²/((n−2)(n−3))), computed over expression of *expressing* cells.
5. Rank cell types; emit stats. If `--trial-prior`, binarize tau (specific vs. broad) and attach the paper's published ORs.

## Chains with

`omics-target-evidence-mapper` → **`celltype-specificity-profiler`** → `target-validation-scorer` → `clinical-trial-finder`

Output is clean JSON/CSV so downstream skills (or the `bio-orchestrator`) can consume it directly.

## Gotchas

- **Sparse genes:** a gene expressed in <1% of cells gives an unstable bimodality coefficient — the skill flags `low_expression: true` and you should treat the BC as unreliable.
- **Atlas cell-type granularity drives tau:** coarse annotations (e.g. "immune cell") inflate apparent ubiquity; fine annotations raise tau. Always report the annotation level — don't compare tau across atlases with different ontologies.
- **Symbol/Ensembl mismatch:** the gene must resolve in the atlas's `var` index; aliases (CD276 vs B7-H3) are mapped via HGNC, but novel/retired symbols fail loudly rather than returning zeros.
- **`--trial-prior` is correlational, not causal:** the ORs come from one observational study; don't present them as a guarantee of success.

## Output structure

```text
output/
├── profile.json              # the contract above
├── per_celltype.csv          # tidy table for plotting
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Dependencies

`scanpy`, `anndata`, `numpy`, `scipy`, `pandas` (Python ≥3.10). No network access required in `--demo` mode.

## Citations

- Zhang H.G., Eckmann P., Miao J., Mahon A.B., Zou J. *The Virtual Biotech: A Multi-Agent AI Framework for Therapeutic Discovery and Development.* bioRxiv 2026. [doi:10.64898/2026.02.23.707551](https://www.biorxiv.org/content/10.64898/2026.02.23.707551v1)
- Yanai I. et al. *Genome-wide midrange transcription profiles…* (tau specificity index), Bioinformatics 2005.
- Tabula Sapiens Consortium. *Tabula Sapiens v2.* CZ CELLxGENE Census.

## License

MIT (to match ClawBio contribution guidelines).
