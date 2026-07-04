# Eval harness: Open Targets candidates + ground truth

How we build the **candidate set** and the **clinical-outcome ground truth** for the
prioritisation eval, live from the Open Targets Platform GraphQL API — the same *method* as
Adaszewski & Schindler (medRxiv 2025), but on **smaller diseases** better suited to a demo.

All fields below were **verified against the live API** (`api.platform.opentargets.org/api/v4/graphql`,
Platform v4) while writing this doc. The API moves; re-verify field names at build time.

---

## 1. The two queries (both confirmed working)

### Candidate definition — mirror the paper's chemical-probe filter

The paper (Adaszewski & Schindler) starts from **~12,000 AD-associated targets** — literally *all*
targets with any genetics/literature association to AD in Open Targets, **no score threshold** —
then applies a **single filter** to reach their 522: **`hasHighQualityChemicalProbes`**. Positives
(their 44) come from an external curated trial list (Cummings et al. 2025), not Open Targets.

**We mirror the candidate filter exactly** but take ground truth from Open Targets (no per-disease
curated list exists for melanoma/IPF): a candidate is a target that (a) is associated with the
disease and (b) has **≥1 high-quality chemical probe** — `Target.chemicalProbes` with
`isHighQuality: true`. This makes our candidate set *methodologically identical* to their 522; only
the disease and the ground-truth source differ (say so when comparing AUGC).

**Probe-filtered pools + positives (verified live, from top-500 associations):**

| Disease | id | Probe pool | Positives (any clinical) | Rate | ≥Ph2 |
|---|---|---|---|---|---|
| Cutaneous melanoma | `MONDO_0005012` | 89 | 17 | 19% | 9 |
| Idiopathic pulmonary fibrosis | `EFO_0000768` | 55 | 28 | 50% | 18 |
| Psoriasis | `MONDO_0005083` | 45 | 26 | 57% | 15 |

Melanoma (89 pool / 17 positives, ~19%) is the closest analogue to the paper's 522/44 (~8%). Raise
the association cap (`size`) if you want the *complete* probe set; top-500 captures the head that
matters for a demo.

```graphql
# probe-filtered candidate pool (filter isHighQuality client-side)
query($efo:String!, $size:Int!){
  disease(efoId:$efo){
    associatedTargets(page:{index:0, size:$size}){
      rows{ score target{ id approvedSymbol chemicalProbes{ isHighQuality } } }
    }
  }
}
# keep rows where any chemicalProbes[].isHighQuality == true
```

### (fallback) Candidate pool by association only — `disease.associatedTargets`
```graphql
query($efo:String!, $size:Int!){
  disease(efoId:$efo){
    id name
    associatedTargets(page:{index:0, size:$size}){
      count
      rows{ score target{ id approvedSymbol } }   # score = overall OT association score
    }
  }
}
```
Take the top-`N` rows as the candidates to rank. Their `score` is the **Open Targets benchmark**
we compare against (the paper's ~0.72 competitor).

### Ground truth — `disease.drugAndClinicalCandidates`
```graphql
query($efo:String!){
  disease(efoId:$efo){
    drugAndClinicalCandidates{                     # NOTE: no args; returns all rows
      count
      rows{
        maxClinicalStage                           # "PHASE_1".."PHASE_4","PRECLINICAL",...
        drug{
          name drugType
          mechanismsOfAction{ rows{ targets{ approvedSymbol } } }   # nullable — guard it
        }
      }
    }
  }
}
```
Collapse rows to **{target → max clinical phase}** via the drug's mechanism-of-action targets.
A candidate is a **positive** if it appears here (optionally thresholded, e.g. ≥ Phase 1, or
≥ Phase 2 for a stricter label). This is the retrospective ground truth: *did a drug against
this target enter the clinic for this disease.*

> **Schema gotchas found the hard way (all corrected above):** `knownDrugs` does **not** exist on
> `Target` or `Disease` anymore — the field is `drugAndClinicalCandidates` on `Disease`, returning
> `ClinicalIndicationFromDisease` with `maxClinicalStage` (a **string**, not `phase`). It takes **no
> `page`/`size` args**. The drug→target link is `drug.mechanismsOfAction.rows[].targets[]` (there is
> no `drug.linkedTargets`). `mechanismsOfAction` can be null — guard before indexing.

### Disease id lookup
```graphql
query($q:String!){ search(queryString:$q, entityNames:["disease"]){ hits{ id name } } }
```
IDs are `MONDO_/EFO_/...`. Confirm the exact id before running — e.g. "melanoma" resolves to the
broad `MONDO_0005105`; use the specific subtype you mean.

---

## 2. Suggested diseases — smaller than the paper's 522, sized for a demo

The paper ranked **522** AD targets (44 positives) — too big to watch a pairwise arena run live,
and its 44/522 ≈ 8% positive rate makes AUGC noisy to move. For a **demo** you want a pool of
**~20–40 candidates** with a **healthy positive rate (~25–45%)** so the gain curve is legible and a
few good/bad placements visibly move AUGC. Pick the disease, then set `N` (candidate count) so the
pool is demo-sized.

**Recommended (well-studied → clean positives, tractable size at small N):**

| Disease | Example EFO/MONDO id | Why it's a good demo | Notes |
|---|---|---|---|
| **Cutaneous melanoma** | `MONDO_0005012` | **Verified live: 84 targets with clinical-stage drugs.** Rich, well-annotated immuno-oncology + kinase story (BRAF, MEK, PD-1…) — positives are unambiguous and *interpretable* to a judge. | Set `N≈30` for a demo-sized pool; strong positive density. |
| **Type 2 diabetes** | look up (`search "type 2 diabetes"`) | Very well-drugged; many clear clinical targets → high positive rate, easy to reason about. | Broad; keep `N` small. |
| **Psoriasis** | look up | Compact, immunology-driven target set (IL-17, IL-23, TNF…); positives are famous drugs → great narrative. | Naturally smaller pool. |

**Also good, more "novel/unmet-need" flavour (fewer positives — harder, more differentiating):**

| Disease | Why | Watch-out |
|---|---|---|
| **Idiopathic pulmonary fibrosis (IPF)** | Small, well-defined; only a couple approved targets → tests whether the arena *ranks the rare positives high*. | Low positive rate → AUGC noisier; use as the "hard" case, not the headline. |
| **Amyotrophic lateral sclerosis (ALS)** | Famously few validated targets; a good stress test. | Very sparse positives; report with care. |

**Recommendation for the demo:** lead with **cutaneous melanoma** (`MONDO_0005012`, positives
verified, interpretable) at `N≈25–30` candidates. Keep **IPF** as a second "harder, sparser" case
to show the method isn't just riding an easy positive rate. This gives a legible headline + a
credibility check, both far smaller than 522.

---

## 3. Where this plugs into the code (design-stage repo)

Matches the planned layout — a thin Open Targets client under `tools/`, consumed by `eval/`:

```
tools/opentargets.py        # (new) GraphQL client: search_disease(), candidates(efo,N),
                            #        ground_truth(efo) -> {symbol: max_phase}
eval/build_dataset.py       # (new) efo + N -> candidates.json (id,symbol,ot_score)
                            #        + labels.json (symbol -> phase, positive flag)
eval/augc.py                # (new) gain curve + normalised AUGC given a ranking + labels
```

- **Endpoint:** `POST https://api.platform.opentargets.org/api/v4/graphql`, JSON body
  `{"query":..., "variables":...}`. No auth/key. Be polite (cache responses; the set is static per
  disease/date).
- **Via ToolUniverse instead of raw HTTP:** the same data is reachable through the MCP tool
  `OpenTargets_get_associated_diseases` and siblings (see [docs/SETUP.md](../docs/SETUP.md)). Prefer
  the raw client for the eval (deterministic, snapshot-able); the MCP tools are what the *arena
  agents* call during ranking. Keeping the eval's ground truth on a **separate raw pull** avoids the
  agents' tool access contaminating the labels.
- **Leakage note (unchanged from the baseline doc):** ground truth is *drug-in-clinic*, which the
  model may already know. AUGC measures whether the *ranking* surfaces positives early from the
  criteria — snapshot candidates + labels to JSON once, and rank against the frozen snapshot so the
  eval is reproducible and the label set can't drift under you.

## 4. AUGC (same metric as the paper, so numbers are comparable)

Given a ranking of the `N` candidates and the positive set `P`:
1. Walk the ranking top→bottom; gain curve `y = (# positives seen so far)/|P|` vs `x = rank/N`.
2. `A_actual` = area under that curve. `A_perfect` = all positives ranked first.
   `A_random` = diagonal (0.5).
3. **AUGC = (A_actual − A_random)/(A_perfect − A_random)** ∈ ~[0,1]; report for the arena, the
   Claude-Science pointwise baseline, and the raw OT association score. See
   [eval/CLAUDE_SCIENCE_BASELINE.md](CLAUDE_SCIENCE_BASELINE.md) for the full comparison design.
