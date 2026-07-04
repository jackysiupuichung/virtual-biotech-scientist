# Claude priors ranking prompt (melanoma / `melanoma_anyclin`)

This is the **judgment-only** baseline: the ranking is produced from prior
biological/clinical knowledge alone — **no experiments, no tool calls, no data lookups
were run**. It measures what an informed prior orders the pool as, before any arena
evidence-gathering. Ranker id: `claude_priors`; output:
[`melanoma_anyclin.claude_priors_ranking.json`](data/melanoma_anyclin.claude_priors_ranking.json).

Paste the block below into a fresh Claude session. It pins the fixed 89-target pool and the
exact output schema so the reply scores directly through [`augc.py`](augc.py) under the same
[ranking contract](RANKING_FORMAT.md) as the arena and OT baseline.

- The scorer reads **only** `ranking` (a bare ordered symbol list; index 0 = rank 1).
- `scores` is an optional reasoning aid — `augc.py` ignores extra keys, so it never affects
  the metric. It exists so the ranking is derived from a considered priority score and so you
  can audit tie-breaks after the fact. **The order is authoritative; the score just derives it.**

---

## Prompt to paste

You are ranking drug targets for **melanoma** (EFO/MONDO_0005012) by how promising they are as
therapeutic targets — best (most promising) first.

Rank **from your own knowledge and judgment only**: do **not** run any experiments, tool calls,
web searches, or data lookups, and do not echo any external association score. This is a
pure-prior ranking.

Below is a fixed candidate pool of 89 targets. Rank **all 89** of them using your
biological/clinical judgment (mechanism, known melanoma drivers, druggability, clinical
precedent).

**Candidate pool (89 target symbols, unordered):**
BRAF, MAP2K1, MAP2K2, ATM, CDK4, KDR, MET, AKT1, ERBB2, TERT, SETD2, MTOR, CDK6, SMARCA4,
PDGFRB, NTRK1, FGFR2, GRIN2A, ATR, FGFR1, KAT6A, EP300, CD274, AR, FGFR4, AKT2, SYK, NTRK2,
IKBKB, PTPN11, MDM2, CDK12, POLQ, ESR1, DDR2, NTRK3, LCK, CREBBP, ACVR1B, PBRM1, KAT6B, MAP2K4,
CHEK2, SMO, IDH1, NCOR1, BRD3, WRN, PIK3CA, BTK, FAS, BRD4, JAK1, JAK2, EGFR, FLT3, RET, ABL1,
ALK, PTK6, EZH2, STAT3, JAK3, KRAS, CTSS, PARP1, PIK3CB, KDM6A, KEAP1, NSD2, FGFR3, IDH2, BCL6,
AKT3, PPARG, SOS1, MAPK1, VHL, NSD3, TRIM24, PPM1D, ACVR1, MALT1, GRM5, SRC, BCL2, EPAS1, PIM1,
RXRA

**Output requirements — read carefully:**
- First assign each of the 89 targets a **priority score in [0, 1]** (1 = most promising
  melanoma target). Then set `ranking` to those symbols sorted by score, highest first. If two
  targets tie on score, break the tie by your judgment so the order is still total.
- The `ranking` order is what gets evaluated; the score is only your reasoning aid.
- Return **only** a single JSON object — nothing before or after it (no prose, no markdown
  fences, no explanation).
- Use exactly this schema and these field names:

```json
{
  "meta": {
    "disease": "melanoma",
    "efo_id": "MONDO_0005012",
    "ranker": "claude_priors",
    "label_set": "melanoma_anyclin"
  },
  "ranking": ["<symbol1>", "<symbol2>", "..."],
  "scores": { "<symbol1>": 0.0, "<symbol2>": 0.0 }
}
```

- `ranking` is an ordered list of **target symbols, best → worst** (index 0 = rank 1).
- `scores` maps **every** pool symbol to its priority score.
- Use the symbols **exactly** as spelled in the pool above. Include all 89, no additions, no
  omissions, no duplicates. `ranking` must contain all 89 symbols and be exactly the
  score-sorted order of `scores`.

---

## Save & score the reply

Save the JSON reply to `eval/data/melanoma_anyclin.claude_priors_ranking.json`, then:

```bash
# Claude Science ranking:
python3 eval/augc.py --ranking eval/data/melanoma_anyclin.claude_priors_ranking.json \
                     --labels  eval/data/melanoma_anyclin.labels.json

# OT association baseline, for comparison (same labels):
python3 eval/augc.py --ot-baseline eval/data/melanoma_anyclin.candidates.json \
                     --labels      eval/data/melanoma_anyclin.labels.json
```

Pool = 89 targets, 16 positives. Both rankers score against the same
`melanoma_anyclin.labels.json`, so the two AUGC numbers are directly comparable.
