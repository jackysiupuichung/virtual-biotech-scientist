# Prioritisation Arena — frontend

A single-page, no-build console for the drug-target prioritisation arena. Open
`frontend/index.html` in any browser — no server, no dependencies.

Designed with the Anthropic `frontend-design` methodology (ground-in-subject; one
signature element carries the boldness; monospace as the personality carrier for a
lab-instrument readout).

## Files & how to regenerate the data

```
frontend/
  index.html        the whole app (HTML + CSS + JS inline)
  _data.js          arena cards (10 melanoma targets, ordinal grades)   [WINDOW.ARENA_DATA]
  _loop.js          hand-authored VoI loop trace                        [WINDOW.VOI_LOOP]
  _pairs.js         recorded pairwise match runs                        [WINDOW.RECORDED_PAIRS]
  _collect.js       recorded CSO collection steps (tool calls + grades) [WINDOW.COLLECT_RUNS]
  _graph.js         LangGraph execution graphs (nodes/edges)            [WINDOW.TRACE_GRAPHS]
  data/runs/        raw recorded live runs: collect_<SYM>/{result.json, trace.jsonl}
  tools/            extractors that regenerate _collect.js / _graph.js from data/runs/
```

`_collect.js` and `_graph.js` are **generated, reproducibly**, from the raw runs in
`data/runs/`. To rebuild after adding a run (order matters — graph reads collect's output):

```
python frontend/tools/extract_collect.py     # data/runs/*/result.json  -> _collect.js
python frontend/tools/extract_graph.py        # data/runs/*/trace.jsonl  -> _graph.js
```

To record a **new** target's run first (writes result.json + trace.jsonl):

```
python skills/virtual-biotech-cso/harness.py \
  --query "Assess <SYM> as a therapeutic target in melanoma" \
  --live --backend claude-cli --out frontend/data/runs/collect_<SYM>
```

Three modes, switched from the header toggle:

- **Arena overview** — the ranking, Pareto plot, VoI loop, and dossier (below).
- **Build a card ▸** — pick a target and watch the CSO **evidence-collection** loop build
  its card step by step (below).
- **Live match ▸** — pick two targets and watch the arena judge them **step by step**.

## Build a card (the evidence-collection process, as a LangGraph trace)

Pick a **target to assess** → **Assess target**. This replays a *real* live run of the
`virtual-biotech-cso` harness as an **execution graph**, showing how a bare target becomes
a graded card:

- **The graph** (centre) is the actual LangGraph trace (`trace.jsonl`), drawn as a layered
  left-to-right flow: **Run → Chief of Staff → Planner → 6 Scientists → Review passes →
  Reviewer lenses + Gap finder → Decision → CSO synthesis**. Nodes reveal stage by stage as
  the run "executes". Each scientist node carries the grade it produced.
- **The agent loop is the centrepiece.** When the Scientific Reviewer isn't satisfied it
  **re-routes**: the amber back-arrows loop from one *Review pass* to the next through the
  `re-route` node. BRAF ran 3 passes, TERT ran **6** before the reviewer accepted the
  evidence — straight from the trace, not staged.
- **Click any node or arrow to inspect that step.** A node shows its span detail — stage,
  **duration and token count** from the trace, plus (for scientists) the division question,
  the real **tool call** (`OpenTargets_target_disease_evidence(gene_symbol="BRAF", …) →
  evidences.count=8`), and the interpretation. An **edge** shows what the hand-off is —
  sequential flow, panel fan-out, or a **re-route loop-back**.
- **① Chief-of-Staff briefing** and **③ Scientific Reviewer** (verdict + relevance/evidence/
  thoroughness scores + gaps → re-route targets) flank the graph; **④** shows the card this
  run produced.

The graph is extracted from each run's `trace.jsonl` into `_graph.js` (extractor in git
history); the per-step tool calls/grades come from `_collect.js`. Both are **genuine** —
recorded by actually running:

```
uv run python skills/virtual-biotech-cso/harness.py \
  --query "Assess BRAF as a therapeutic target in melanoma" \
  --live --backend claude-cli --out <dir>
```

then extracting each `<dir>/result.json` into `_collect.js` (extractor in git history).
The runs are honest about their own limits — e.g. BRAF's live run shows a step that queried
OpenFDA with a gene symbol instead of a drug name, which the Reviewer catches and routes to
fix. Recorded targets: BRAF, MAP2K1, KDR, TERT (incl. TERT's live *re-route* run — the Reviewer sends the loop back for 5 follow-up steps). Because these live
runs used a lightweight backend, their grades are more conservative than the arena's
canonical cards — the finished-card panel says so explicitly.

## Live match (the "understand the steps" view)

Pick hypothesis **A vs B** → **Run match**. This replays a *real* recorded run of the
arena's pairwise pipeline, step by step, so the process is legible:

1. Both hypothesis cards slide in side-by-side.
2. **Six axis-judge agents** are dispatched concurrently (spinners), then resolve
   one-by-one — each reveals its **relation** (A better / B better / tie / insufficient
   evidence), **confidence**, **rationale**, and **decisive / missing evidence** (click to
   expand). The contested axis is highlighted on both cards as each judge lands.
3. The **dominance rule** is applied visibly — A dominates B only on unanimity with no
   unresolved axis — with a tally and the final **verdict** (dominates / trade-off).

This mirrors `arena/pareto_agent` exactly: `compare_all_axes` (six concurrent
`compare_axis` LLM calls) → `aggregate_axis_comparisons` (the conservative unanimity rule).

The replays in `_pairs.js` are **genuine outputs** — recorded by actually running
`arena/pareto_agent` over the cards via the `claude` CLI backend (no API key needed).
BRAF vs MAP2K1, e.g., really comes back a *trade-off* because MAP2K1 wins the Safety axis;
BRAF vs TERT is unresolved because TERT has no clinical safety data to compare. Nothing is
invented.

**Recorded pairs:** BRAF vs MAP2K1 · BRAF vs TERT · KDR vs ATM · MAP2K1 vs CDK4 ·
MTOR vs ERBB2. Any other of the 45 possible pairs is selectable but shows a *"not yet
recorded — this pair would dispatch 6 live axis agents"* note (Run is disabled).

### Recording more pairs (or going truly live)

To record another pair, run the arena over the two cards and capture per-axis output into
`_pairs.js` under key `"A__B"` (see git history for the one-off recorder). To make it a
*fresh* live computation instead of a replay, the browser would need a small server
(FastAPI wrapping `arena/pareto_agent`, streaming each axis result over SSE) — a deliberate
non-goal here so the page stays a zero-setup static file.

## What it shows

- **Ranked leaderboard** (left) — 15 melanoma hypotheses ordered by global Pareto front
  then a within-front scalar sum. Ground-truth positives (BRAF, MAP2K1, KDR) are ringed.
- **Pareto trade-off plot** (centre, the hero) — pick any two of the six AZ-5R axes;
  points non-dominated *on those two axes* light up cyan and are joined by the front line.
  **Tractability** is the default x-axis (surfaced as a first-class objective).
- **Value-of-Information loop** (centre, below) — the budget-constrained reasoning loop as
  a timeline: each step shows the action chosen, its cost, the rationale, and how it moved
  the rank (Δ). Steps that resolve a synthetic (unmeasured) axis are the highest-VoI actions.
- **Hypothesis dossier** (right) — per-axis value, confidence, grade, and **provenance**
  (data origin: opentargets / hybrid / synthetic; the DB + fields the value came from).
  Click any axis row to expand its finding, interpretation, and provenance. Proposed
  experiments (with cost tier) are listed as the next VoI actions.

Everything cross-links: click a point, a leaderboard row, or a loop step and all three
panels update to that hypothesis.

## Data

The **real LLM division cards** — `skills/virtual-biotech-cso/eval/arena_set/cards/*.json`
(10 melanoma targets). Each card is what the CSO subagents actually produced: per-axis
`finding` / `grade` / `provenance`, grounded in real OpenTargets / ChEMBL / Pharos /
OpenFDA lookups. **There is no numeric value and no confidence score** — the axes are an
ordinal scale `absent < weak < moderate < supporting < strong`, so the arena computes
Pareto dominance on the grade ranks directly (ties allowed, deterministic jitter on the
plot for overlapping grade-cells). No invented precision.

Ground truth (BRAF, MAP2K1, KDR positive) comes from
`skills/virtual-biotech-cso/eval/arena_set/melanoma_10.json` (OpenTargets drug-in-clinic).

Extracted at build time into `_data.js`. The VoI loop trace (`_loop.js`) is grounded in
each card's real weakest axes (the actual `weak`/`absent` evidence gaps are the highest-VoI
targets to resolve). The loop trace is still hand-authored — no live loop log exists yet.

To regenerate after the cards change, re-run the extraction snippet (in git history) — the
page reads whatever `_data.js` / `_loop.js` provide.
