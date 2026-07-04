# Eval — target prioritisation on clinical-outcome ground truth

Measures whether a ranker surfaces real drug targets (targets that reached the clinic for a
disease) early in its ranking. Method mirrors **Adaszewski & Schindler** (medRxiv 2025,
`10.64898/2025.12.28.25343106`) — chemical-probe-filtered candidates, AUGC enrichment of
clinical targets — so our numbers sit next to their ~0.72. See
[OPENTARGETS_HARNESS.md](OPENTARGETS_HARNESS.md) for the data design and
[CLAUDE_SCIENCE_BASELINE.md](CLAUDE_SCIENCE_BASELINE.md) for the arena-vs-baseline comparison.

## The flow

```
 Open Targets API
        │  tools/opentargets.py   (candidates = probe-filtered assoc; ground truth = drug-in-clinic)
        ▼
 eval/build_dataset.py           ── freeze a disease to JSON ──►  eval/data/<disease>.candidates.json
                                                                  eval/data/<disease>.labels.json
        │
        ▼
 a ranker (arena / Claude Science / OT score)  ── emits ──►  <disease>.<ranker>_ranking.json
        │                                                     (format: RANKING_FORMAT.md)
        ▼
 eval/augc.py --ranking ... --labels ...       ── scores ──►  AUGC + gain curve + hits@k
```

The **candidates/labels snapshot** and the **ranking format** are the two stable seams: the
arena is built and iterated behind the ranking format; the ground truth is frozen behind the
snapshot. Neither can drift under the other.

## Files

| file | role |
|---|---|
| [../tools/opentargets.py](../tools/opentargets.py) | Open Targets GraphQL client (search, candidates, ground truth) |
| [build_dataset.py](build_dataset.py) | freeze one disease → `candidates.json` + `labels.json` |
| [augc.py](augc.py) | score a ranking → normalised AUGC, gain curve, hits@k |
| [plot_gain_curves.py](plot_gain_curves.py) | plot gain curves for one+ rankings → self-contained SVG (or PNG with `--mpl`) |
| [RANKING_FORMAT.md](RANKING_FORMAT.md) | the JSON contract a ranker emits for scoring |
| [CLAUDE_PRIORS_PROMPT.md](CLAUDE_PRIORS_PROMPT.md) | prompt for the **judgment-only** baseline (`claude_priors`) — no experiments run |
| [OPENTARGETS_HARNESS.md](OPENTARGETS_HARNESS.md) | data design + verified OT schema fields |
| [CLAUDE_SCIENCE_BASELINE.md](CLAUDE_SCIENCE_BASELINE.md) | arena (pairwise) vs Claude Science (pointwise) comparison |
| `data/*.json` | frozen snapshots + produced rankings |

## Datasets (melanoma, built)

Cutaneous melanoma (`MONDO_0005012`), **89 probe-filtered candidates**. Two label thresholds:

| label set | positives | rate | when to use |
|---|---|---|---|
| `melanoma_anyclin` | 16 / 89 | 18% | **headline** — closest to the paper's ~8% rate, most discriminative AUGC |
| `melanoma` (≥Phase 2) | 9 / 89 | 10% | robustness check — stricter "seriously pursued" positives |

## Reference numbers (verified)

The **Open Targets association score** is the trivial reference ranker — the number the arena
must beat:

| ranker | `melanoma_anyclin` AUGC | `melanoma` (≥Ph2) AUGC |
|---|---|---|
| Perfect (positives first) | 1.00 | 1.00 |
| **Claude priors** (judgment only, no experiments) | **0.53** | **0.51** |
| **OT association score** | **0.45** | **0.53** |
| Random | 0.00 | 0.00 |
| Worst (positives last) | −1.00 | −1.00 |

`claude_priors` is the **judgment-only** baseline — a pure prior ranking with **no experiments,
tool calls, or lookups**; see [CLAUDE_PRIORS_PROMPT.md](CLAUDE_PRIORS_PROMPT.md). Its edge over
OT is **threshold-dependent**:

- **`melanoma_anyclin` (PRECLINICAL, permissive, 16 pos):** claude_priors **0.531** vs OT 0.452
  (`hits@k`: @5=4, @10=7, @20=9) — the prior wins by +0.08.
- **`melanoma` (≥Phase 2, strict, 9 pos):** claude_priors **0.506** vs OT **0.531**
  (`hits@k`: @5=3, @10=3, @20=5) — OT narrowly wins; the prior's advantage doesn't survive the
  stricter "seriously pursued" bar.

Both are the numbers the evidence-gathering arena should beat. Gain curves for all four
(ranker × label set) are in
[`data/melanoma_anyclin.gain_curves.svg`](data/melanoma_anyclin.gain_curves.svg) — **colour =
ranker, dash = label set** (solid = preclinical, dashed = phase 2).

(Paper reference: web-augmented LLM ≈ 0.72, matching OT, on their AD set.)

## Rebuild / re-score

```bash
# rebuild a disease snapshot (any-clinical positives)
python eval/build_dataset.py --efo MONDO_0005012 --name melanoma_anyclin \
       --min-phase PRECLINICAL --outdir eval/data

# score the OT reference
python eval/augc.py --ot-baseline eval/data/melanoma_anyclin.candidates.json \
                    --labels      eval/data/melanoma_anyclin.labels.json

# score a produced ranking (arena output, claude_priors, etc.)
python eval/augc.py --ranking eval/data/melanoma_anyclin.claude_priors_ranking.json \
                    --labels  eval/data/melanoma_anyclin.labels.json

# plot gain curves — colour = ranker, dash = label set (repeat --labels to overlay both)
python eval/plot_gain_curves.py \
       --labels "preclinical:eval/data/melanoma_anyclin.labels.json" \
       --labels "phase2:eval/data/melanoma.labels.json" \
       --ranking eval/data/melanoma_anyclin.claude_priors_ranking.json \
       --ranking eval/data/melanoma_anyclin.opentargets_ranking.json \
       --out eval/data/melanoma_anyclin.gain_curves.svg
```
