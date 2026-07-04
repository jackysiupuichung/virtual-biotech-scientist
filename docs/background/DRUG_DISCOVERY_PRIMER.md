# Drug discovery primer (for non-scientists)

A plain-English orientation for teammates coming from software/ML without a biology background.
It explains **what drug discovery is**, the **standard pipeline**, and **what "target
identification" and "prioritisation" actually mean** — then maps those ideas onto the concrete
[ToolUniverse hypercholesterolemia case study](REFERENCES.md#reference-case-study-reviewed) so the
abstract terms have a worked example. This is the domain context behind
[DESIGN.md](../design/DESIGN.md).

---

## 1. The one-paragraph mental model

A disease happens because some biological process goes wrong. Somewhere in that process is a
**target** — usually a specific protein — that, if you nudge it with a **drug** (often a small
molecule that binds to it), brings the process back toward normal. Drug discovery is the long,
expensive search for *(a)* the right target and *(b)* a molecule that acts on it safely and
effectively. Most attempts fail, so the entire game is **de-risking decisions as early and as
cheaply as possible**.

Two jargon words you'll hear constantly:

- **Target** — the thing the drug acts on (e.g. the protein **HMGCR**).
- **Compound / ligand / molecule** — the candidate drug (e.g. **lovastatin**, a statin).

---

## 2. The standard pipeline

Left to right, decisions get more expensive and failure gets more painful. The whole industry is
shaped like a funnel: many ideas in, very few drugs out.

```
Target ID → Target validation → Hit ID (screening) → Hit-to-lead → Lead optimisation
   → Preclinical / ADMET (cells + animals) → Clinical trials (Phase I/II/III) → Approval
```

| Stage | Plain definition | Software analogy |
| --- | --- | --- |
| **Target identification** | Pick the biological "switch" (protein) worth drugging for this disease. | Choosing *what problem* to solve. |
| **Target validation** | Build confidence that hitting this target actually changes the disease. | Proving the problem is real and worth it. |
| **Hit identification** | Screen large chemical libraries to find molecules that affect the target. | Brute-force search for *any* working solution. |
| **Hit-to-lead** | Refine the few promising hits into better, more selective "leads." | Turning a hacky prototype into something viable. |
| **Lead optimisation** | Improve potency, selectivity, stability, oral bioavailability. | Hardening + optimising for production. |
| **Preclinical / ADMET** | Test in cells and animals; predict Absorption, Distribution, Metabolism, Excretion, Toxicity. | Staging/QA before real users. |
| **Clinical Phase I/II/III** | Test in humans: safety → efficacy → large confirmatory trials. | Beta → GA → scaled rollout, but each step costs years and \$\$\$. |
| **Approval** | Regulator (FDA/EMA) allows marketing. | Launch. |

### Why it's brutal (rough industry figures — orders of magnitude, not exact)

- **~10–15 years** from target to approved drug.
- **~\$1–2.5 billion** all-in cost per approved drug (a large share is paying for the failures).
- **~90%+ attrition** for candidates that *enter clinical trials* — and far more die earlier.

The takeaway for an AI scientist project: **the earliest decisions (which target? which lead?)
determine most of the downstream cost.** Getting target identification and prioritisation right is
where AI can move the needle most.

---

## 3. Target identification — what it really involves

You rarely have *one* obvious target. You have a **list of candidate proteins** plausibly linked to
the disease, and you must decide which to pursue. The evidence you weigh:

- **Genetic / causal evidence** — do mutations in this gene cause or modify the disease?
- **Biological role** — does the protein sit at a control point in the relevant pathway?
- **Tractability / druggability** — is it physically possible to drug? (Does it have a binding
  "pocket"? Is there a known modality — small molecule, antibody?)
- **Precedent** — have drugs hit this target before (validates feasibility but may mean a crowded field)?
- **Safety** — is the protein also doing essential jobs elsewhere in the body (→ side effects)?

## 4. Prioritisation — turning a list into a decision

Target identification gives you a *list*. **Prioritisation** is the act of **ranking that list and
committing** to one (or a few). This is the high-leverage judgement call: pick wrong and you may
burn years and hundreds of millions before you find out.

Good prioritisation is **comparative and multi-axis**: you score every candidate on the same axes
(genetics, tractability, safety, novelty, chemical matter, competition/IP), then rank them — ideally
with a written rationale a domain expert can audit.

> This is exactly the step our project focuses on. See [DESIGN.md §3](../design/DESIGN.md#3-methods-prioritisation).

### Prioritisation vs. validation

These are distinct but interlocking steps, and our system's value-of-information loop unifies the
*mechanism* behind both:

- **Prioritisation is the filter.** Hundreds of candidate genes/markers come out of sequencing; you
  rank them to decide *which deserve time and budget*. Cheap, mostly computational/retrieval evidence.
- **Validation is the go/no-go.** The top-ranked candidates undergo rigorous **functional** experiments
  (chemical or genetic modulation, in vitro/in vivo) to confirm the target is real and druggable —
  a *commit-or-kill* decision. Expensive, experimental.
- **They inform each other.** Targets with strong functional validation rank higher; and the
  prioritisation step is what flags *which* target is missing the key piece of evidence that would be
  worth validating next.

Our project treats both as one **value-of-information** process — spend the next (cheap or expensive)
action where it most changes the decision — while respecting that the two differ in cost, evidence
type, and stakes. See [INFORMATION_MAXIMISATION.md](../design/INFORMATION_MAXIMISATION.md).

---

## 5. Worked example: the hypercholesterolemia case study

Hypercholesterolemia = chronically high blood cholesterol → cardiovascular disease. Here's how the
[reference ToolUniverse case study](REFERENCES.md#reference-case-study-reviewed) walks the pipeline,
with the jargon translated:

| Pipeline stage | What happened in the case study | Tools used |
| --- | --- | --- |
| **Target identification** | Pulled the top ~10 candidate proteins associated with the disease (LDLR, PCSK9, APOB, **HMGCR**, NPC1L1, …). | Open Targets (disease→target associations) |
| **(light) validation + prioritisation** | For each candidate: checked **tractability** (druggable pockets? approved drugs?) and ran a **literature** search; summarised a dossier per target; **a human expert then picked HMGCR**. | Open Targets tractability, EuropePMC; `expert_consult_human_expert` |
| **Drug selection** | HMGCR is the target of **statins**; selected an existing statin (**lovastatin**) to optimise. | knowledge retrieval |
| **Lead optimisation (in silico)** | Found ~100 structural **analogs** of lovastatin (similar molecules) and predicted which avoid the brain (blood-brain-barrier penetrance) to reduce side effects. | ChEMBL similarity search, **ADMET-AI** |
| **Binding check (in silico)** | Predicted how strongly each analog binds HMGCR. | **Boltz-2** (binding affinity) |
| **IP review** | Checked patent/freedom-to-operate considerations for the final analog. | patent tools |

Two things to notice — they are the openings our project targets:

1. **The final prioritisation was made by a human**, not the AI (`expert_consult_human_expert →
   "Use HMGCR"`). The AI gathered evidence but **deferred the decision**.
2. **No experimental data was generated** — everything is database retrieval or in-silico
   *prediction* (ADMET-AI, Boltz-2 are ML models, not lab assays). The pipeline **predicts and
   stops**; it never tests a hypothesis and loops back.

Our project addresses exactly these gaps: a CSO + scientist-division architecture
([DESIGN.md](../design/DESIGN.md)) feeding a **prioritisation arena** ([ARENA.md](../design/ARENA.md)) that makes
competing hypotheses **compete head-to-head** and ranks them as a multi-objective optimisation —
a quantified, reproducible decision instead of a narrative dossier or a deferral to a human.

---

## 6. Glossary (quick reference)

- **Target** — protein (usually) a drug acts on.
- **Ligand / compound / small molecule** — the candidate drug.
- **Druggability / tractability** — how feasible it is to drug a target.
- **Hit / lead** — a molecule that works on the target (hit), refined into a serious candidate (lead).
- **SAR (structure-activity relationship)** — how tweaking a molecule's structure changes its activity.
- **Analog** — a structurally similar molecule (a variation on a known drug).
- **ADMET** — Absorption, Distribution, Metabolism, Excretion, Toxicity — does it behave like a drug in the body?
- **Tanimoto similarity** — a 0–1 score for how chemically similar two molecules are.
- **BBB penetrance** — whether a molecule crosses the blood-brain barrier (often want to *avoid*, to reduce CNS side effects).
- **In silico** — done by computer/simulation (vs. *in vitro* = in a dish, *in vivo* = in a living organism).
- **Binding affinity** — how tightly a molecule sticks to its target.
- **Attrition** — the rate at which candidates fail and drop out of the pipeline.
