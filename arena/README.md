# Arena — the prioritisation arena (and its synthetic fixture)

This folder is the **seam between two people**:

- **Fixture owner** (this folder as it stands): owns the **hypothesis cards** — what a
  hypothesis looks like, which axes it carries, what's real vs synthetic. Everything the arena
  *consumes* is defined here.
- **Arena builder** (adds the code): consumes `fixtures/melanoma.hypotheses.json`, runs
  matches / Pareto / rating, and emits a **ranking** in the eval's format. Should not need to
  touch how cards are built — only read them.

> Migration note: this fixture currently lives in `virtual-biotech-scientist`. It will migrate
> into `virtual-biotech-agents` (where the arena code lives) later. It is here **now** so both
> people share one concrete, agreed framing before that move — the card contract is the thing to
> agree on, not the repo it sits in.

---

## The contract (what the arena reads)

`fixtures/melanoma.hypotheses.json` — **15 melanoma hypotheses**, 3 positive (20%, matching the
eval pool). Each hypothesis is a **target × disease × modality** card:

```jsonc
{
  "id": "H6",
  "target":   { "symbol": "ERBB2", "ensembl_id": "ENSG00000141736" },
  "disease":  { "name": "cutaneous melanoma", "efo_id": "MONDO_0005012" },
  "modality": "ADC",
  "narrative": {            // report-style block, like a Virtual-Biotech dossier
    "target_overview": "...", "pathways": [...],
    "liabilities": [...], "evidence_gaps": [...], "proposed_experiments": [...]
  },
  "axes": {                 // one evidence entry per 5R axis (+ Tractability)
    "right_target":     { ...evidence entry... },
    "right_tissue":     { ... },
    "right_safety":     { ... },
    "right_patient":    { ... },
    "right_commercial": { ... },
    "tractability":     { ... }
  },
  "label": { "positive": false, "max_clinical_phase": null }  // eval ground truth (do NOT feed to judges)
}
```

Every **axis evidence entry** has the same shape — the keystone the arena and VoI loop rely on:

```jsonc
{
  "value": 0.80,            // normalised [0,1] — the yardstick Pareto/judges compare on
  "confidence": 0.4,        // how much to trust the value
  "cost": 3,                // discrete tier (1 cheap lookup · 2 synthesis · 3 run_experiment)
  "direction": "supports",  // supports | refutes | neutral
  "strength": "strong",     // strong | moderate | weak (qualitative)
  "data_origin": "synthetic",   // opentargets (real) | hybrid | synthetic  <-- read this
  "finding": "…prose the judge panel can argue over…",
  "interpretation": "…what it means for the go/no-go…",
  "source": { "db": "...", "fields": [...], "synthetic_parts": [...] }
}
```

### `data_origin` — the honesty flag (read before trusting a value)

| value | meaning | axes |
|---|---|---|
| `opentargets` | real per-target Open Targets field | Right Target, Right Safety, Tractability |
| `hybrid` | real OT signal + a synthesised judgment | Right Patient, Right Commercial |
| `synthetic` | **not in OT** — a designed prior, not measured | Right Tissue |

**Right Tissue is deliberately the only fully-synthetic axis** (single-cell tau / malignant
fraction aren't in OT). That is the point: it is the **highest-value action for the VoI loop** to
resolve via a tier-3 `run_experiment`. Its values carry `designed_tradeoff: true` and are set so
the **Pareto front is non-trivial** — 9 of 15 cards are non-dominated, with real corners:

- **ERBB2 (ADC), NTRK1, FGFR2** — tissue-strong but tractability/safety-weaker
- **MTOR, AKT1, ATM/ATR** — tractable/druggable but tissue-non-specific
- **MAP2K2** — safety-dominant, mid elsewhere

A ranker that just sorts on one axis will be wrong; the trade-offs are what the arena must arbitrate.

## What the arena must emit (the other seam)

A ranking in the eval's format so it can be scored by AUGC against the melanoma labels — see
[../eval/RANKING_FORMAT.md](../eval/RANKING_FORMAT.md):

```json
{ "meta": { "disease": "melanoma", "efo_id": "MONDO_0005012",
            "ranker": "arena", "label_set": "melanoma_anyclin" },
  "ranking": ["ERBB2", "BRAF", "..."] }
```

Then: `python eval/augc.py --ranking <arena_ranking>.json --labels eval/data/melanoma_anyclin.labels.json`.
Reference to beat: OT association score = **0.45**. (Paper reference ≈ 0.72.)

## Files

| file | role |
|---|---|
| [fixtures/melanoma.hypotheses.json](fixtures/melanoma.hypotheses.json) | the 15 cards — the arena's input |
| [build_hypotheses.py](build_hypotheses.py) | regenerates the fixture from real OT + designed trade-offs |

## Rebuild

```bash
python arena/build_hypotheses.py   # live OT pull per target; deterministic; runs from any cwd
```

The real OT portions (`data_origin: opentargets`) are pulled live per target; the synthetic
portions are designed (see `MODALITY` and `TRADEOFF` in the script) — edit those to reshape the
slate or the trade-offs.
