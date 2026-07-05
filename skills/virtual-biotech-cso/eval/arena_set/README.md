# Arena evaluation set — melanoma, 10 targets

A 10-target set of **5R hypothesis cards** to exercise the arena's qualitative
pairwise-comparison → Pareto-front pipeline (`docs/method/COMPARISON_PARETO_SYSTEM.md`)
and score the result with AUGC against known labels.

## Contents

- `melanoma_10.json` — the target list (3 ground-truth positives + 7 negatives),
  drawn from `eval/data/melanoma.labels.json` (OpenTargets drug-in-clinic ground
  truth, EFO `MONDO_0005012`, PHASE_2 positive threshold).
- `cards/<SYMBOL>.json` — one 5R hypothesis card per target, each axis populated
  from **live ToolUniverse** data (OpenTargets, GWAS Catalog, CellMarker,
  ClinicalTrials.gov, Pharos, Thera-SAbDab). Schema: `CARD_SCHEMA.md`.
- `CARD_SCHEMA.md` — the card shape the arena's axis-judges read.

## The targets

| Target | Label | Why chosen |
| --- | --- | --- |
| BRAF   | **positive** | validated melanoma driver (vemurafenib/dabrafenib), Tclin |
| MAP2K1 | **positive** | MEK1, trametinib target, Tclin |
| KDR    | **positive** | VEGFR2, drug-in-clinic (lenvatinib); has a real safety liability |
| ATM    | negative | druggable (Tchem) but no ATM-in-clinic for melanoma |
| CDK4   | negative | Tclin, but melanoma programs terminated (below threshold) |
| AKT1   | negative | high evidence *count* but literature co-mentions, not causal |
| ERBB2  | negative | "strong target, wrong disease" — HER2 validated in breast/gastric |
| TERT   | negative | strong target genetics (5p15.33) but clinically untranslatable |
| SETD2  | negative | modest driver; absent clinical/commercial axes |
| MTOR   | negative | strong target + Tclin, but no active melanoma clinic |

## Why this set is a good arena test

The discriminating signal is **not** `right_target` or `tractability` — several
negatives (CDK4, MTOR, TERT, ERBB2) match the positives on target biology and/or
druggability. The separation lives in **`right_patient` + `right_commercial`**
(clinical translation): positives grade strong there, negatives grade weak/absent.

So a naive single-axis ranker (best target score, or most tractable) ranks TERT /
MTOR / ERBB2 high and **loses AUGC**. The arena's multi-axis dominance rule should
catch that those targets are dominated on the clinical axes — this set is designed
to reward the comparison-based approach over a scalar one.

## How the cards were produced

One subagent per target ran a 5R assessment via the ToolUniverse MCP tools and
wrote its card. All findings are live tool output; a tool error / empty result is
recorded honestly as grade `absent` with a reason — never fabricated.

## Next step (not yet built)

Feed `cards/*.json` into the arena's axis-judge → dominance → Pareto machinery,
flatten the front to `{meta, ranking:[symbols]}`, and score:

```bash
python eval/augc.py --ranking <arena_ranking>.json --labels eval/data/melanoma.labels.json
```
