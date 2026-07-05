# Tools

`tools/` contains the project evidence runtime:

- [evidence.py](/Users/qp252880/Downloads/work/virtual-biotech-scientist/tools/evidence.py:1): CLI, MCP entrypoints, normalization, aggregation
- [schema.py](/Users/qp252880/Downloads/work/virtual-biotech-scientist/tools/schema.py:1): core dataclasses and enums
- [opentargets.py](/Users/qp252880/Downloads/work/virtual-biotech-scientist/tools/opentargets.py:1): local Open Targets helper

## Quick Use

Run the full BRAF melanoma evidence chain:

```bash
python3 tools/evidence.py \
  --gene BRAF \
  --ensembl-id ENSG00000157764 \
  --disease "cutaneous melanoma" \
  --disease-efo-id MONDO_0005012
```

Generate the checked demo hypothesis card:

```bash
python3 tools/demo/run_tooluniverse_demos.py
```

This writes [demo_hypotheses.json](/Users/qp252880/Downloads/work/virtual-biotech-scientist/tools/demo/demo_hypotheses.json).

## Evidence Table

`score` is the normalized support signal written into each observation as `value` and then aggregated into axis `score`.
`confidence` is adapter-level trust in that score, not a statistical interval.
`cost` is the discrete runtime tier used by planning: `1` cheap, `2` medium, `3` expensive.

| Layer | ToolUniverse MCP tool | Score (`value`) comes from | Confidence comes from | Cost |
| --- | --- | --- | --- | --- |
| `text_knowledge` | `literature_text_mcp` | Europe PMC hit-count heuristic normalized to `support_score` | `0.7` when articles exist, else `0.35` | `1` |
| `knowledge_graph` | `kg_reasoning_mcp` | Monarch associations normalized to `support_score` | `0.75` when associations exist, else `0.4` | `1` |
| `omics` | `hpa_omics_mcp` | Human Protein Atlas disease-vs-normal expression normalized to `score` | fixed `0.65` when returned | `2` |
| `single_cell` | `cellxgene_single_cell_mcp` | PanglaoDB marker/context lookup normalized to `specificity_score` | `0.65` when records exist, else `0.35` | `3` |
| `spatial_omics` | `spatial_omics_stub` | not live yet | not live yet | `2` |
| `perturbation_model` | `lincs_perturbation_model_mcp` | LINCS signature availability normalized to `score` | `0.7` when signatures exist, else `0.35` | `3` |
| `perturbation_experiment` | `lincs_perturbation_experiment_mcp` | LINCS perturbation signatures normalized to `score` | `0.75` when signatures exist, else `0.35` | `3` |
| `genetics` | `opentargets_genetics_mcp` | Open Targets `association_score` | fixed `0.8` | `1` |
| `structure_pharmacology` | `alphafold_tooluniverse_mcp` | AlphaFold summary metadata normalized to `score` | fixed `0.7` | `3` |
| `clinical` | `clinical_trials_mcp` | ClinicalTrials.gov study-count heuristic normalized to `support_score` | `0.7` when studies exist, else `0.35` | `1` |

## Notes

- Axis aggregation lives in [evidence.py](/Users/qp252880/Downloads/work/virtual-biotech-scientist/tools/evidence.py:428) and uses [LAYER_AXIS_MATRIX](/Users/qp252880/Downloads/work/virtual-biotech-scientist/tools/evidence.py:90).
- The MCP public functions are exposed from [evidence.py](/Users/qp252880/Downloads/work/virtual-biotech-scientist/tools/evidence.py:1526): `list_capabilities`, `validate_hypothesis`, `preview_observation`, `run_observation`, `get_observation`, `serve`.
