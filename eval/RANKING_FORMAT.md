# Ranking format — the pipeline contract

Every ranker (the **arena**, the **Claude Science** baseline, the raw **OT association**
reference) emits its result as a single JSON file in this shape. `eval/augc.py` reads it and
scores it against the frozen labels. This is the one seam between "producing a ranking" and
"evaluating a ranking" — keep it stable.

## Schema

```json
{
  "meta": {
    "disease": "melanoma",
    "efo_id": "MONDO_0005012",
    "ranker": "arena",
    "label_set": "melanoma_anyclin"
  },
  "ranking": ["BRAF", "MAP2K1", "MAP2K2", "KDR", "..."]
}
```

| field | required | meaning |
|---|---|---|
| `meta.disease` | no | disease short name (display only) |
| `meta.efo_id` | no | Open Targets id the pool came from (provenance) |
| `meta.ranker` | no | who produced this order — `arena`, `claude_science`, `opentargets_score`, … |
| `meta.label_set` | no | which `labels.json` this is meant to be scored against (display only; the actual labels are passed to `augc.py` via `--labels`) |
| `ranking` | **yes** | ordered list of **target symbols**, **best first** |

## Rules `augc.py` applies

- **Symbols, not Ensembl ids.** `ranking` uses `approvedSymbol` (e.g. `BRAF`) — the same key as
  `labels.json`. (Candidate files also carry `ensembl_id` if a ranker prefers to join on that,
  but the scored key is the symbol.)
- **Best → worst**, index 0 is rank 1.
- **Partial rankings are allowed.** Any pool target missing from `ranking` is appended at the
  bottom (arbitrary order) and a warning is printed — so an incomplete arena run still scores,
  it just can't earn credit for the targets it never placed.
- **Extras are ignored.** Symbols in `ranking` that aren't in the pool are dropped.
- **Ties:** emit your best guess of order; AUGC has no tie handling — equal-merit targets should
  just be adjacent.

## How each ranker fills it

- **Arena (ours):** after the Pareto/rank step, flatten to a total order (e.g. by Pareto rank,
  then a tie-break) and write the symbols in that order.
- **Claude Science (baseline):** transcribe the ranking it produces into `ranking`; for the
  pairwise-consistency probe, that's a separate artifact (see
  [CLAUDE_SCIENCE_BASELINE.md](CLAUDE_SCIENCE_BASELINE.md)).
- **OT reference:** `eval/augc.py --ot-baseline <candidates.json>` generates this order for you
  from the association score — no file to hand-write.

## Score it

```bash
# a produced ranking:
python eval/augc.py --ranking eval/data/melanoma.example_ranking.json \
                    --labels  eval/data/melanoma_anyclin.labels.json

# the OT association reference (no ranking file needed):
python eval/augc.py --ot-baseline eval/data/melanoma_anyclin.candidates.json \
                    --labels      eval/data/melanoma_anyclin.labels.json

# full result incl. gain curve (for plotting):
python eval/augc.py --ranking ... --labels ... --json
```

`eval/data/melanoma.example_ranking.json` is a working sample (it is the OT-score order).
