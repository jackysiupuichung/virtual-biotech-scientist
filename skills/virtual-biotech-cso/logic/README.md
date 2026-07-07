# Logic layer — symbolic grounding of the CSO loop and report

A small **stratified Datalog** engine (pure Python, no external dependency) that
grounds the CSO in inspectable, replayable rules over the evidence. It occupies the
two seats the harness already wires for it:

- `harness._engine_gaps` → `cso.aggregate_panel_review(extra_gaps=…)` — **loop grounding**
- `harness._engine_decision` → `cso.synthesize_report(decision_engine=…)` — **report + decision grounding**

Both read **one shared fact base**, derived once per loop pass (memoised on the
`results` identity), so the loop and the report reason over the same facts.

## Non-silenceable floor

Two derived facts are a floor the LLM cannot lift; everything above it stays LLM
judgment:

- `force_reroute(axis, skill)` — a *required* axis with no graded evidence. Emitted as
  a gap with `forces_reroute=True`, which `aggregate_panel_review` honours regardless
  of the lens vote count.
- `floor_nogo` — a serious safety signal on the safety axis. Clamps the decision tier
  to `NO_GO` regardless of coverage and regardless of the synthesis agent's proposal
  (the report renders the divergence rather than silently overriding).

Both are pure functions of the evidence — no LLM output feeds them — which is what
makes them a *deductive* floor rather than another opinion.

## Fact contract

Facts are `Fact(pred, args)` tuples; the base is a `set[Fact]`. Evidence envelopes
`{step, division, skill, question, result, source}` (from `cso.execute_skill`) project
into the EDB; the rules derive the IDB.

### EDB (base facts)

| Predicate | Meaning |
| --- | --- |
| `evidence(step, axis, skill, source)` | one per envelope |
| `graded(step, axis, grade)` | grade ∈ `strong \| supporting \| absent`, from `cso._evidence_grade` |
| `executed(step, source)` | source ∈ `cso.EXECUTED_SOURCES` |
| `nonempty(step)` | the result carries real content |
| `safety_signal(step, kind)` | `boxed_warning` / `serious_ae` on a safety row |
| `required_axis(axis)` | a core forcing axis (`CORE_AXES`) |
| `scored_axis(axis)` | an axis in the coverage score (`ALL_AXES`, all 6) |
| `safety_axis(axis)` | the hard-gate axis (`right_safety`) |
| `route_skill(axis, skill)` | reroute target skill for that axis |

`CORE_AXES` (forcing) = `right_target, right_tissue, right_safety, right_patient`.
`right_commercial` (landscape) and `tractability` are scored but **non-forcing** — their
absence never forces control flow (the LLM lenses may still flag them).

### IDB (derived)

`axis_covered`, `axis_attempted`, `axis_score(axis, 0|1|2)`, `axis_unassessed`,
`force_reroute(axis, skill)`, `safety_fail(axis)`, `floor_nogo`,
`report_downgrade(step, from, to)`, `report_reject(step)`.

`axis_covered` (has *non-absent* evidence, used for scoring) is deliberately distinct
from `axis_attempted` (has *any* evidence row, used for forcing): a required axis
forces a re-route only when it was **never attempted** — a structural gap. An axis
that ran but returned weak/absent evidence is a coverage question for the LLM lenses,
not an engine-forced re-route.

## Rule set

```prolog
% stratum 1 — positive over EDB
axis_covered(A)    :- graded(_, A, G), G != "absent".
axis_attempted(A)  :- evidence(_, A, _, _).
axis_score(A, 2)   :- scored_axis(A), graded(_, A, "strong").
safety_fail(A)     :- safety_axis(A), safety_signal(_, "boxed_warning").
safety_fail(A)     :- safety_axis(A), safety_signal(_, "serious_ae").

% stratum 2 — negation over the saturated stratum 1 (stratified → deterministic)
axis_score(A, 1)   :- scored_axis(A), graded(_, A, "supporting"), not axis_score(A, 2).
axis_score(A, 0)   :- scored_axis(A), not axis_covered(A).
axis_unassessed(A) :- required_axis(A), not axis_attempted(A).
force_reroute(A,S) :- axis_unassessed(A), route_skill(A, S).           % non-silenceable gap
floor_nogo         :- safety_fail(_).                                  % non-silenceable NO_GO
report_downgrade(S,"strong","supporting")
                   :- graded(S,_,"strong"), executed(S,_), not nonempty(S).
report_reject(S)   :- graded(S,_,"strong"), not executed(S,_).
```

## Decision tier

`score = Σ_axis best axis_score` over the 6 scored axes (strong=2 > supporting=1 >
absent=0); `max_score = 12`. Bands: `≥0.66·max → GO`, `≥0.40·max → CONDITIONAL_GO`,
else `REVIEW`. `floor_nogo` overrides to `NO_GO`.

## Report grounding

`validate_report` returns `{step: {grade, reject}}`. `synthesize_report` consults it
(carried on the decision dict under `_grounding`): a `report_downgrade` row renders
`supporting` instead of `strong`; a `report_reject` row (a `strong` grade with no
executed source — a fabricated claim) is dropped from the evidence table.

## Swapping in a real Vadalog backend

`default_engine()` returns the pure-Python `PyDatalogEngine`. Any class implementing
the `LogicEngine` ABC (`derive_facts`, `gaps`, `decision`, `validate_report`) can
replace it there — the harness seams and this fact vocabulary stay unchanged.
