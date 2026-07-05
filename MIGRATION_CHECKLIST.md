# Migration & Scaffolding Checklist

Tracks standing up the **Virtual Biotech Scientist** framework by (A) migrating reusable
code from the sibling repo `virtual-biotech-agents`, and (B) scaffolding the new
arena / VoI / experiment layers that repo does not have.

- **Source repo (migrate FROM):** `../virtual-biotech-agents`
- **This repo (migrate INTO):** `virtual-biotech-scientist`
- **Legend:** `[ ]` todo · `[~]` in progress · `[x]` done
- **"Migrate" = real working code copied/adapted.** **"Scaffold" = interfaces + dataclasses
  + docstrings + `TODO` markers, importable but not yet implemented — fill in later.**

Package root for new code: **`vbs/`**. Already-present code (`tools/`, `eval/`) is left in place.

---

## Part A — Migrate (reusable 1-8 from virtual-biotech-agents)

| # | Item | From | To | Kind | Status |
|---|------|------|----|------|--------|
| A1 | CSO orchestration spine (brief→decompose→route→divisions→reviewer→reroute) | `skills/virtual-biotech-cso/cso.py`, `harness.py` | `vbs/cso/cso.py`, `vbs/cso/harness.py` | migrate shape → scaffold specifics | [x] |
| A2 | Multi-backend LLM runner (Anthropic→OpenAI→Gemini→Claude CLI + StubRunner) | `.../runners.py` | `vbs/runners.py` | migrate verbatim | [x] |
| A3 | Tracing (trace.jsonl + optional Langfuse mirror) | `.../tracing.py` | `vbs/tracing.py` | migrate verbatim | [x] |
| A4 | Reviewer panel + reroute / gap-detection loop | `.../prompts/reviewer.md`, harness reviewer logic | `vbs/cso/reviewer.py`, `vbs/cso/prompts/` | migrate shape → scaffold | [x] |
| A5 | Information-maximisation loop skeleton (budget gate, gap ranking, no-thrash executed-set) | harness info-max logic | `vbs/voi/selector.py` (budget skeleton) | migrate skeleton → upgrade to VoI (see B3) | [x] |
| A6 | `celltype-specificity-profiler` skill (τ specificity, offline demo, tests) | `skills/celltype-specificity-profiler/` | `skills/celltype-specificity-profiler/` | migrate verbatim | [x] |
| A7 | Offline-first `--demo` + B7-H3 case fixtures | `.../demo_data/b7h3/` | `demo_data/b7h3/` | migrate verbatim | [x] |
| A8 | Division prompts (chief_of_staff, orchestrator, division_scientist) as axis evidence roles | `.../prompts/` | `vbs/cso/prompts/` | migrate verbatim | [x] |

## Part B — New (build the arena / VoI / experiment framework — scaffold now, fill later)

| # | Item | To | Kind | Status |
|---|------|----|------|--------|
| B1a | Hypothesis **card** schema `{value, axis, confidence, cost}` over AZ 5R + Tractability | `vbs/arena/card.py` | implement (load-bearing, small) | [x] |
| B1b | **Pareto front** sort (weight-free primary ranking) | `vbs/arena/pareto.py` | implement (pure fn) | [x] |
| B1c | Pairwise **tournament** — LLM-judge match + Elo + Bradley–Terry | `vbs/arena/tournament.py` | Elo/BT math real; judge scaffold | [x] |
| B1d | Match **scheduler** (round-robin ≤10 / Swiss 12–15) | `vbs/arena/scheduler.py` | round-robin real; Swiss scaffold | [x] |
| B2 | Competing **hypothesis** framing (target×disease×modality×mechanism×stratum), 5–15/disease | `vbs/arena/hypothesis.py` | dataclass real; generation scaffold | [x] |
| B3 | **VoI / netEVPI** selector (info value − cost, discrete cost tiers 1/10/100) | `vbs/voi/selector.py` | scaffold on the A5 skeleton | [x] |
| B4 | MCP **`run_experiment`** interface + pluggable backends (Boltz-2 live, single-cell + DNA/RNA-LM stubs) | `vbs/experiments/` | registry real; backends scaffold | [x] |
| B5 | **ToolUniverse** MCP integration (client + compact-mode tool select + output→card adapter) | `vbs/tooluniverse/` | scaffold | [x] |
| B6 | Self-improving **hypotheses** (mutate losers: swap modality / narrow stratum / flip mechanism) | `vbs/arena/mutate.py` | scaffold | [x] |
| B7 | Self-improving **toolkit** (one scripted ToolUniverse tool-composition instance) | `vbs/toolkit/compose.py` | scaffold | [x] |
| B8 | **Leaderboard UI** (Streamlit: Elo animation + Pareto view + provenance) | `ui/leaderboard.py` | scaffold | [x] |

## Part C — Wiring & verification

| # | Item | Status |
|---|------|--------|
| C1 | `pyproject.toml` — register `vbs` package, add `agents` / `ui` / `mcp` extras | [x] |
| C2 | Package `__init__.py` files + clean import graph | [x] |
| C3 | Smoke test: `python -c "import vbs..."` all modules import; existing eval still runs | [x] |
| C4 | Self-review pass: every checklist row matches a real file; scaffolds have clear TODOs | [x] |

---

## Notes / decisions

- `harness.py`/`cso.py` (2275 lines in source) are deeply coupled to **ClawBio routing** and the
  **Prometheux Vadalog** verdict. We migrate the **loop shape** (the brief→route→reviewer→reroute
  control flow and the info-max convergence rules) but scaffold the ClawBio- and Prometheux-specific
  call sites to point at **ToolUniverse** (tool layer) and the **arena** (verdict layer) instead.
- `runners.py` and `tracing.py` are vendor-neutral and self-contained → copied verbatim.
- The **eval harness** (`eval/`, `tools/opentargets.py`) already lives in this repo and is NOT migrated;
  it is the ground-truth driver the arena must beat (OT baseline AUGC 0.45 on melanoma).
- The card contract is the **keystone** (DESIGN §3.2): the arena and VoI only compose if every evidence
  source emits the same shape. **Decision: we adopt jcaky's fixture schema (PR #1) as the single source
  of truth** — axis keys `right_*`, ordinal cost tiers `1/2/3`, axis-entry fields `{value, confidence,
  cost, direction, strength, data_origin, finding, interpretation, source}`. `vbs/arena/card.py` now
  matches it verbatim, so `arena/fixtures/melanoma.hypotheses.json` loads directly (no adapter).

## Status log

- Created checklist; beginning execution.
- Migrated A1–A8 and scaffolded B1–B8; wired C1–C2.
- Adopted **jcaky's card schema** (PR #1) as canonical in `vbs/arena/card.py`; loaded his melanoma
  fixture and ran the first real closed loop (`scripts/rank_melanoma.py`): fixture → arena → AUGC.
  Result: arena and OT single-axis baseline both AUGC 1.0 on this fixture (the 3 positives are the
  top-3 OT targets → saturated; needs harder cases to discriminate — flagged to jcaky).
- **Verification (C3/C4) — all green:**
  - `python -c "import ..."` — all 19 `vbs` modules import; 3 experiment backends auto-register.
  - `python -m vbs.cso.harness --demo` — runs end-to-end (reviewer → Pareto → Elo/Bradley–Terry → ranking).
  - `pytest -q` — **23 passed** (new arena/VoI/reviewer/mutation tests + scaffold-boundary tests).
  - Migrated `celltype-specificity-profiler --demo` — works (τ = 0.9556 on MS4A1).
  - Pre-existing eval intact — OT baseline AUGC = 0.4521 (matches documented 0.45).
  - `ruff check vbs tests ui` — clean.

## What runs today vs. what to fill in

**Runnable now (real code):** card schema, Pareto fronts + scalarisation, Elo + Bradley–Terry,
round-robin scheduler, VoI budget loop (no-thrash + stop rule), reviewer structural gap-detector,
mutation operators, the multi-backend runner, tracing, and the offline `--demo`.

**Scaffolded (importable, raises `NotImplementedError` with a `TODO(<id>)` pointer):** the LLM judge
panel (B1c), hypothesis-slate generation (B2), the netEVPI estimate `expected_information` (B3), the
three experiment backends' compute (B4), the ToolUniverse client + adapters (B5), tool composition
(B7), and the live-run wiring in `harness.run_live` (A1). Grep `TODO(` across `vbs/` for the list.
