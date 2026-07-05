#!/usr/bin/env python
"""harness.py — run virtual-biotech-cso as a LIVE multi-agent loop.

``cso.py`` is a deterministic orchestrator that plans, routes to ClawBio skills,
and assembles a report — but it makes no LLM call. Its three reasoning roles
(Chief of Staff, Scientific Reviewer, CSO synthesis) are emitted as delegation
stubs for a *driving agent* to fill. This harness IS that driving agent.

It reuses cso.py's pure functions for everything deterministic (decompose/route,
execute routed skills, render the report, write the output contract) and
replaces only the three reasoning slots with live agent calls via ``runners.py``
— a pluggable backend (Anthropic SDK primary, OpenAI-compatible fallback) that
runs in any environment, not only where Claude Code is installed.

The defining behaviour cso.py could not show on its own: the **live reviewer
verdict drives control flow** — when the reviewer returns ``re-route``, the
harness executes one real follow-up step before synthesis. When no backend is
configured it degrades to cso.py's honest stubs (never fabricates) and says so.

Usage:
    python harness.py --query "Assess B7-H3 ... in lung cancer" [--out ./output]
                      [--backend auto|anthropic|openai] [--model NAME]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

# Structured phase-event sink: emit(event_name, payload). The frontend supplies
# one to stream the live loop as SSE; the CLI leaves it unset (console only).
Emit = Callable[[str, dict[str, Any]], None]

# Human-in-the-loop gate. Called once per review-loop pass *after* the reviewer
# panel votes and a candidate follow-up is resolved, but *before* the loop acts on
# it. Receives a checkpoint payload (verdict, panel, gaps, the proposed re-route)
# and returns a decision dict the loop applies — letting a human approve, override
# the verdict, redirect the re-route, or inject a gap. Returning ``None`` (or a
# falsy/`{"action": "approve"}` value) keeps the autonomous behaviour unchanged.
# When no gate is supplied the loop runs fully autonomously exactly as before, so
# HITL is purely additive — the CLI and every existing test are unaffected.
Gate = Callable[[dict[str, Any]], "dict[str, Any] | None"]

import cso  # sibling module — reused, never modified
import runners
from tracing import TraceRecorder

# --- JSON schemas per role (harvested from prompts/*.md) -------------------- #
BRIEFING_SCHEMA = {
    "context": "string",
    "data_availability": [{"source": "string", "relevance": "high|medium|low", "note": "string"}],
    "priority_questions": ["string"],
    "feasibility_flags": ["string"],
}
REVIEW_SCHEMA = {
    "verdict": "synthesize|re-route",
    "scores": {"relevance": "1-5", "evidence": "1-5", "thoroughness": "1-5"},
    "gaps": [{"missing": "string", "route_to": "skill-name", "why": "string"}],
    "experiments": [{"missing": "string", "proposed_experiment": "string",
                     "route_to": "skill-name", "expected_readout": "string", "why": "string"}],
}
PLAN_SCHEMA = {
    "subtasks": [{"division": "string (a routing.yaml division)",
                  "intent": "string (an intent under that division)",
                  "question": "string", "depends_on": ["step_NN_intent"]}],
}
# Hybrid planner: first reason freely about the ideal investigation, THEN bind each
# question to a functional (division, intent) — or leave it unbound (→ a proposed
# experiment). The reasoning is streamed so the UI shows the agent deciding what to ask.
HYBRID_PLAN_SCHEMA = {
    "reasoning": "string (1-3 sentences: how you're approaching this target assessment)",
    "questions": [{
        "question": "string (a scientific sub-question worth answering for this target)",
        "rationale": "string (why this question matters to the go/no-go decision)",
        "division": "string (the best-fit routing division, or null if none fits)",
        "intent": "string (the best-fit intent under that division, or null if none fits)",
        "depends_on": ["step_NN_intent (earlier bound questions only)"],
    }],
}
DIVISION_FINDING_SCHEMA = {
    "division": "string",
    "interpretation": "string (cite [step_NN])",
    "confidence": "high|medium|low",
    "caveats": ["string"],
    "evidence_grade": "strong|supporting|weak",
}
SYNTHESIS_SCHEMA = {
    "decision": "GO|CONDITIONAL_GO|REVIEW|NO_GO",
    "confidence": "high|medium|low",
    "recommendation": "string (cite evidence steps e.g. [step_03])",
    "target_overview": "string",
    "liabilities": [{"risk": "string", "mitigation": "string"}],
    "evidence_gaps": ["string"],
    "proposed_experiments": [{"experiment": "string", "expected_readout": "string",
                              "rationale": "string"}],
}

AGENT_SOURCE = "agent (live)"  # provenance tag for agent-produced slots
MAX_REROUTES = 3  # change #2: bound the review→reroute loop (avoid unbounded recursion)

# Token budget for the review→reroute loop. The loop always runs its core passes
# (up to MAX_REROUTES, forced by the load-bearing core axes); beyond that it keeps
# chasing the broader *desired* axes (prometheux_reason.REQUIRED_AXES minus
# CORE_AXES) only while the run's accumulated token spend (rec.totals) is under this
# ceiling. So a thin run converges on the core four, a budget-rich run fills the
# broader axes, and the bound is tokens — not a magic pass count. Overridable per
# run via the ``token_budget`` arg to ``_review_and_reroute`` (0/None → core only).
DEFAULT_TOKEN_BUDGET = 60_000


def _read_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _usage_of(runner: runners.Runner) -> dict[str, int]:
    """Token usage from the runner's last call, tolerant of runners that omit it.

    ``last_usage`` is an optional part of the Runner protocol — a custom or test
    runner need not set it. Missing/empty → no tokens recorded for that span."""
    return getattr(runner, "last_usage", None) or {}


def _evidence_context(results: list[dict[str, Any]]) -> str:
    """Compact JSON of the routed evidence for the reviewer / synthesis agent."""
    slim = [{"step": e["step"], "division": e["division"], "skill": e["skill"],
             "question": e["question"], "result": e.get("result", {})} for e in results]
    return json.dumps(slim, indent=2, default=str)


class Trace:
    """Prints a per-step trace so the multi-agent loop is visible in the console.

    Also carries an optional structured ``emit(event, payload)`` callback. The CLI
    leaves it None (console only); the frontend passes one so the SAME loop streams
    per-phase events to the UI — keeping one source of truth for the multi-agent
    loop instead of a re-implementation that drifts. ``event`` is a no-op when no
    emitter is set, so threading it through the helpers costs the CLI nothing.
    """

    def __init__(self, backend: str, model: str,
                 emit: "Emit | None" = None, *, quiet: bool = False) -> None:
        self._emit = emit
        self._quiet = quiet
        if not quiet:
            print("┌─ virtual-biotech CSO · live multi-agent loop")
            print(f"│  backend: {backend}  model: {model}\n│")

    def step(self, icon: str, msg: str) -> None:
        if not self._quiet:
            print(f"│  {icon} {msg}")

    def event(self, name: str, payload: dict[str, Any]) -> None:
        """Emit a structured phase event to the UI (no-op without an emitter)."""
        if self._emit is not None:
            self._emit(name, payload)

    def done(self, report: str) -> None:
        if not self._quiet:
            print(f"│\n└─ wrote {report}")


def _agent_or_stub(trace: Trace, role: str, runner: runners.Runner, prompt: Path,
                   context: str, schema: dict[str, Any], stub: dict[str, Any],
                   rec: TraceRecorder) -> tuple[dict[str, Any], str]:
    """Run a reasoning role live; on any failure fall back to cso's honest stub.

    Returns (payload, source) where source is AGENT_SOURCE or cso's DELEGATE.
    Each call opens a ``rec`` span tagged with the backend, status (ok/stub), and
    token usage — the degradation moments land as ``status="stub"`` spans.
    """
    with rec.span(role, kind="agent", backend=runner.name, model=runner.model) as sp:
        try:
            payload = runners.run_with_retry(runner, _read_prompt(prompt), context, schema)
            sp.record_usage(**_usage_of(runner)).set(source=AGENT_SOURCE)
            trace.step("🤖", f"{role}: live agent ({runner.name})")
            return payload, AGENT_SOURCE
        except runners.NoBackendError as exc:
            sp.status = "stub"
            sp.set(source=cso.DELEGATE, degraded="no-backend", reason=str(exc))
            trace.step("⚪", f"{role}: {exc}")
            return stub, cso.DELEGATE
        except Exception as exc:  # noqa: BLE001 — degrade, never fabricate
            sp.status = "stub"
            sp.set(source=cso.DELEGATE, degraded="agent-failed", reason=str(exc))
            trace.step("⚠️", f"{role}: agent failed ({exc}); using honest stub")
            return stub, cso.DELEGATE


def _plan(trace: Trace, runner: runners.Runner, query: str, briefing: dict[str, Any],
          case: str, routing: dict[str, Any], rec: TraceRecorder
          ) -> tuple[list[cso.Subtask], list[dict[str, Any]], str]:
    """Hybrid planner: reason up the ideal investigation, then ground it.

    The planning agent first reasons *freely* — it lists the scientific questions it
    would ask to make the go/no-go call, each with a rationale — then binds each to the
    best functional (division, intent). ``cso.bind_questions`` splits the result:
    questions that route to a runnable skill become executed subtasks; the rest become
    **proposed experiments** (the agent knew what it wanted, but no tool answers it yet).
    The planner's reasoning + the bound/unbound split stream to the UI, so the agent is
    seen *deciding what to investigate*, not silently emitting a list.

    Returns ``(subtasks, experiments, source)``. Any backend failure (or an empty/
    invalid result) degrades to the deterministic plan with no extra experiments.
    """
    catalog = cso._routable_intents(routing)
    menu = "\n".join(f"- {div}: {', '.join(sorted(ix))}" for div, ix in catalog.items())
    context = (
        f"User query: {query}\n\nBriefing:\n{json.dumps(briefing, default=str)}\n\n"
        "You are the CSO planning this target assessment. First, in `reasoning`, say "
        "briefly how you'll approach it. Then in `questions`, list the scientific "
        "sub-questions you'd answer to reach a go/no-go decision — reason about what "
        "actually matters for THIS target, don't just fill slots. For each question, "
        "pick the best-fit (division, intent) from the menu below; if none fits, set "
        "them to null (it becomes a proposed experiment). Prefer questions you can "
        f"ground in the menu, but include the key open questions even if unbindable:\n{menu}\n\n"
        "depends_on may reference earlier bound questions as step_NN_<intent>."
    )
    with rec.span("planner", kind="agent", backend=runner.name, model=runner.model) as sp:
        try:
            payload = runners.run_with_retry(
                runner, _read_prompt(cso.ORCHESTRATOR_PROMPT), context, HYBRID_PLAN_SCHEMA)
            subtasks, experiments = cso.bind_questions(payload.get("questions", []), routing)
            if not subtasks:  # nothing bound → fall back so the run still produces evidence
                raise cso.PlanValidationError("no question bound to a functional skill")
            reasoning = str(payload.get("reasoning", "")).strip()
            sp.record_usage(**_usage_of(runner)).set(
                source=AGENT_SOURCE, n_steps=len(subtasks), n_experiments=len(experiments))
            trace.step("🧠", f"planner reasoning: {reasoning[:120]}" if reasoning else
                       "planner: (no reasoning text)")
            trace.step("🗺️", f"planner: {len(subtasks)} grounded step(s), "
                       f"{len(experiments)} open question(s) → proposed experiments")
            trace.event("planner_reasoning", {
                "reasoning": reasoning,
                "grounded": [{"step": t.step, "skill": t.skill, "question": t.question}
                             for t in subtasks],
                "open_questions": experiments,
            })
            return subtasks, experiments, AGENT_SOURCE
        except runners.NoBackendError:
            subtasks = cso.decompose_and_route(query, case, routing)
            sp.status = "stub"
            sp.set(source=cso.DELEGATE, degraded="no-backend", n_steps=len(subtasks))
            trace.step("⚪", f"planner: no backend → deterministic plan ({len(subtasks)} steps)")
            return subtasks, [], cso.DELEGATE
        except Exception as exc:  # noqa: BLE001 — degrade, never fabricate
            subtasks = cso.decompose_and_route(query, case, routing)
            sp.status = "stub"
            sp.set(source=cso.DELEGATE, degraded=type(exc).__name__,
                   reason=str(exc), n_steps=len(subtasks))
            trace.step("⚠️", f"planner: {type(exc).__name__} → deterministic plan ({exc})")
            return subtasks, [], cso.DELEGATE


def _review_panel(trace: Trace, runner: runners.Runner, results: list[dict[str, Any]],
                  routing: dict[str, Any], rec: TraceRecorder,
                  query: str = "") -> dict[str, Any]:
    """Fan out N lens-specialised reviewers concurrently, then aggregate (panel).

    Each lens is an independent agent call with the shared reviewer prompt plus its
    own focus; they run in a thread pool (true concurrent multi-agent). A lens that
    fails abstains honestly (synthesize, no gaps) rather than crashing the panel.
    The deterministic cso.aggregate_panel_review folds them into one verdict the
    loop consumes unchanged. Only invoked on a live backend (stub keeps 1 reviewer).
    """
    prompt = _read_prompt(cso.REVIEWER_PROMPT)
    evidence = _evidence_context(results)

    # Announce the panel: one running phase per lens (concurrent reviewer agents).
    trace.event("phase", {"id": "review", "role": "Scientific Reviewer panel",
                          "kind": "agent", "division": "Audit loop",
                          "title": f"{len(cso.REVIEWER_LENSES)} lens reviewers audit evidence",
                          "status": "running",
                          "lenses": [l["key"] for l in cso.REVIEWER_LENSES]})

    def _one(lens: dict[str, str]) -> tuple[str, dict[str, Any]]:
        ctx = f"## Your review lens: {lens['key']}\nFocus on: {lens['focus']}\n\n{evidence}"
        with rec.span(f"reviewer:{lens['key']}", kind="agent",
                      backend=runner.name, model=runner.model) as sp:
            try:
                payload = runners.run_with_retry(runner, prompt, ctx, REVIEW_SCHEMA)
                sp.record_usage(**_usage_of(runner)).set(source=AGENT_SOURCE,
                                                         verdict=payload.get("verdict"))
                return lens["key"], payload
            except Exception as exc:  # noqa: BLE001 — a lens abstains, never fabricates
                sp.status = "stub"
                sp.set(degraded="lens-failed", reason=str(exc))
                return lens["key"], {"verdict": "synthesize", "scores": {}, "gaps": [],
                                     "experiments": []}

    with rec.span("review_panel", kind="loop", n_lenses=len(cso.REVIEWER_LENSES)) as panel_sp:
        with ThreadPoolExecutor(max_workers=len(cso.REVIEWER_LENSES)) as pool:
            lens_reviews = list(pool.map(_one, cso.REVIEWER_LENSES))
        engine_gaps = _engine_gaps(trace, results, rec, query)
        review = cso.aggregate_panel_review(lens_reviews, routing, extra_gaps=engine_gaps)
        panel = review["panel"]
        panel_sp.set(verdict=review["verdict"], reroute_votes=panel["reroute_votes"],
                     forced_by_engine=panel.get("forced_by_engine", False),
                     scores=review.get("scores", {}))
    review["source"] = AGENT_SOURCE
    forced = " (engine-forced)" if panel.get("forced_by_engine") else ""
    trace.step("👥", f"reviewer panel: {panel['reroute_votes']}/{panel['n_lenses']} lenses "
               f"flag re-route → verdict {review['verdict']}{forced}")
    # Per-lens verdicts so the UI can render the panel vote, then the engine's
    # structural gaps as a distinct (non-silenceable) voice, then the folded review.
    trace.event("panel", {"lenses": [{"key": k, "verdict": r.get("verdict"),
                                      "scores": r.get("scores", {})}
                                     for k, r in lens_reviews],
                          "reroute_votes": panel["reroute_votes"],
                          "n_lenses": panel["n_lenses"]})
    trace.event("engine_gaps", {"gaps": engine_gaps,
                                "forced": any(g.get("forces_reroute") for g in engine_gaps)})
    trace.event("review", {"review": review})
    return review


def _engine_gaps(trace: Trace, results: list[dict[str, Any]],
                 rec: TraceRecorder, query: str = "") -> list[dict[str, Any]]:
    """Prometheux gap-detector: derive *structural* gaps as a non-silenceable vote.

    The reviewer panel's LLM lenses catch semantic gaps; the Vadalog engine catches
    structural ones — a required prioritization axis with no graded evidence at all —
    as a derived fact with a replayable explanation. Such a gap carries
    ``forces_reroute`` so it re-routes on its own (the engine is load-bearing here).
    NOTE: the Prometheux/Vadalog engine is stripped from this lean CSO build, so
    this returns no structural gaps — the reviewer panel's LLM lenses are the sole
    gap source. Re-add ``prometheux_reason`` (and restore the engine call here) to
    bring back the structural-gap vote.
    """
    with rec.span("prometheux_gaps", kind="agent", backend="prometheux") as sp:
        sp.status = "stub"
        sp.set(degraded="engine-stripped", reason="prometheux_reason not bundled")
        return []


def _engine_decision(trace: Trace, results: list[dict[str, Any]],
                     rec: TraceRecorder, query: str = "") -> dict[str, Any] | None:
    """Prometheux decision layer: derive a quantitative, replayable GO/NO-GO tier.

    Runs the same graded evidence the gap-detector sees through the decision rules —
    a weighted per-axis coverage score plus a non-negotiable safety hard-gate. The
    derived tier is *authoritative* for the report's Decision field; the synthesis
    agent's free-text becomes rationale (logic decides, the agent explains). Import
    is local + guarded so a missing module never breaks synthesis — returns None.

    NOTE: stripped in this lean CSO build — returns None, so ``decision_source``
    falls back to ``"agent"`` and the synthesis agent's free-text is authoritative
    for the report's Decision field. Re-add ``prometheux_reason`` to restore the
    quantitative GO/NO-GO tier.
    """
    with rec.span("prometheux_decision", kind="agent", backend="prometheux") as sp:
        sp.status = "stub"
        sp.set(degraded="engine-stripped", reason="prometheux_reason not bundled")
        return None


def _project_decision_facts(trace: Trace, decision: dict[str, Any] | None,
                            target: str, out_dir: Path, run_id: str) -> Path | None:
    """Project the run's verdict into decision facts on every run (local-only).

    Writes ``<out_dir>/run_decision.facts.csv`` — the final-overall tier + per-axis
    subreport conclusions in the dataset-projection Fact contract — so the verdict is
    durable as facts, ready to reason over next to PrimeKG via run_decision_live.py.
    This is the *projection* (cheap, dependency-light, no engine call); the live join
    stays an explicit step. Guarded: a missing extractor never breaks a finished run.
    """
    if decision is None or out_dir is None:
        return None
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                               / "dataset-projection" / "extractors"))
        from run_decision import _decision_facts  # noqa: E402
        from facts import write_facts  # noqa: E402
        out = out_dir / "run_decision.facts.csv"
        n = write_facts(_decision_facts(decision, target, run_id), out)
        trace.step("🗄️", f"projected {n} decision facts → {out.name} "
                          f"(bind via run_decision_live.py)")
        return out
    except Exception as exc:  # noqa: BLE001 — projection is best-effort, never fatal
        trace.event("decision_facts", {"degraded": str(exc)})
        return None


def _apply_gate(gate: "Gate | None", trace: Trace, *, verdict: str,
                review: dict[str, Any], followup: "cso.Subtask | None",
                gap: dict[str, Any] | None, iteration: int,
                routing: dict[str, Any], executed: set[str], step_n: int
                ) -> tuple[str, "cso.Subtask | None", dict[str, Any] | None]:
    """Pause for a human at one review-loop checkpoint; apply their decision.

    Called after the panel has voted and the loop has resolved its *proposed*
    follow-up, but before anything executes. The gate (supplied by the UI) blocks
    until the human responds, then returns a decision dict the loop honours:

    - ``approve`` / falsy / no gate → keep the autonomous (verdict, followup).
    - ``override_verdict`` + ``verdict`` → force ``synthesize`` or ``re-route``.
    - ``redirect`` + ``route_to`` (and optional ``missing``/``why``) → re-route to
      a human-chosen skill instead of the panel's pick.
    - ``add_gap`` + ``missing``/``route_to`` → inject a new gap to chase; implies
      ``re-route``.

    Returns the (possibly amended) ``(verdict, followup, gap)``. With no gate this
    is a pure pass-through, so the autonomous loop is unchanged.
    """
    if gate is None:
        return verdict, followup, gap
    checkpoint = {
        "iteration": iteration,
        "verdict": verdict,
        "panel": review.get("panel", {}),
        "scores": review.get("scores", {}),
        "gaps": review.get("gaps", []),
        "proposed_reroute": (
            {"skill": followup.skill, "question": followup.question,
             "missing": (gap or {}).get("missing", "")} if followup else None),
    }
    trace.event("checkpoint", checkpoint)
    trace.step("⏸️", f"human checkpoint (pass {iteration + 1}): "
               f"awaiting reviewer decision on verdict '{verdict}'")
    decision = gate(checkpoint) or {}
    action = decision.get("action", "approve")
    if action == "approve" or not action:
        return verdict, followup, gap
    if action == "override_verdict":
        new_verdict = decision.get("verdict", verdict)
        trace.step("🧑‍⚖️", f"human override: verdict '{verdict}' → '{new_verdict}'")
        if new_verdict != "re-route":
            return new_verdict, None, None  # synthesize: drop any follow-up
        # Forcing a re-route: if the panel proposed no follow-up (it had voted
        # synthesize), build one from the human's route_to so the loop has a target.
        if followup is None and decision.get("route_to"):
            new_gap = {"missing": decision.get("missing") or "human-directed re-route",
                       "route_to": decision["route_to"],
                       "why": decision.get("why", "human-directed")}
            followup = cso._reroute_task(new_gap, routing, step_n=step_n, executed=executed)
            gap = new_gap
        return new_verdict, followup, gap
    if action in ("redirect", "add_gap"):
        new_gap = {
            "missing": decision.get("missing") or (gap or {}).get("missing", "human gap"),
            "route_to": decision.get("route_to") or (gap or {}).get("route_to"),
            "why": decision.get("why") or (gap or {}).get("why", "human-directed"),
        }
        new_followup = cso._reroute_task(new_gap, routing, step_n=step_n, executed=executed)
        trace.step("🧑‍🔬", f"human {action} → {new_followup.skill} "
                   f"({new_gap['missing']})")
        return "re-route", new_followup, new_gap
    trace.step("⚠️", f"human checkpoint: unknown action {action!r} → proceeding")
    return verdict, followup, gap


def _review_loop(trace: Trace, runner: runners.Runner, query: str, case: str,
                 routing: dict[str, Any], results: list[dict[str, Any]],
                 live: bool, rec: TraceRecorder,
                 token_budget: int | None = DEFAULT_TOKEN_BUDGET,
                 gate: "Gate | None" = None) -> dict[str, Any]:
    """Run reviewer→reroute until `synthesize`, the budget, or MAX_REROUTES.

    Each iteration re-runs the reviewer over the *current* evidence (so a re-route's
    new step is itself reviewable), and on a `re-route` verdict executes one follow-up
    bound to the reviewer's chosen skill — validated against the catalog, with a
    numbered step id so successive re-routes don't collide. Returns the *last*
    reviewer payload (the one the synthesis sees), with its source tag set.

    A follow-up is actionable if it runs an un-run skill, OR asks a question-sensitive
    skill (the live search) a *new* question — a deeper probe for the specific gap,
    steered via ``focus``. A deterministic gene-DB skill, or an identical (skill,
    question) repeat, is skipped: re-running it can't add evidence, so the loop
    synthesizes with the residual gap instead of thrashing.

    The loop runs its core passes (``MAX_REROUTES``, forced by the load-bearing core
    axes) and then keeps chasing the broader *desired* axes while accumulated token
    spend (``rec.totals``) stays under ``token_budget`` — so a budget-rich run fills
    the broader evidence axes while a thin run still converges on the core four.
    """
    panel_capable = runner.name != "stub"  # a live backend → fan out the reviewer panel
    review: dict[str, Any] = {}
    with rec.span("review_loop", kind="loop", mode="panel" if panel_capable else "single"
                  ) as loop_sp:
        # Core passes: initial review + up to MAX_REROUTES forced follow-ups. Past
        # that, the loop continues only while the token budget has room (to chase the
        # broader *desired* axes). ``i`` keeps numbering re-route steps uniquely.
        def _budget_room() -> bool:
            # Chase the broader desired axes only when there is a *measured* token
            # spend below the budget. A run with no token telemetry (stub/test, or a
            # runner that doesn't report usage) reads as spent==0 — treat that as "no
            # budget signal" and fall back to the core cap rather than "infinite
            # room". On live runs rec.totals is the same meter Langfuse mirrors.
            spent = rec.totals.get("total_tokens", 0)
            return bool(token_budget) and 0 < spent < token_budget

        i = 0
        # Signatures of re-routes already executed this loop, as (skill, missing).
        # A re-route is actionable if it either runs an un-run skill OR asks the
        # same skill a *different* question (a new ``missing``) — a deeper follow-up
        # that can surface evidence the first, shallower pass did not. Only an
        # identical (skill, missing) repeat is blocked, since re-running a
        # deterministic skill on the same question cannot add anything.
        rerouted_sigs: set[tuple[str, str]] = set()
        while True:
            within_core = i <= MAX_REROUTES
            if not within_core and not _budget_room():
                trace.step("🧾", f"token budget {token_budget} reached after core passes "
                           "→ synthesize with residual desired-axis gaps")
                break
            if panel_capable:
                review = _review_panel(trace, runner, results, routing, rec, query)
                review_src = AGENT_SOURCE
            else:
                trace.event("phase", {"id": "review", "role": "Scientific Reviewer",
                                      "kind": "agent", "division": "Audit loop",
                                      "title": "Audit evidence", "status": "running"})
                review, review_src = _agent_or_stub(
                    trace, "scientific_reviewer", runner, cso.REVIEWER_PROMPT,
                    _evidence_context(results), REVIEW_SCHEMA,
                    stub=cso.load_review(query, case, results), rec=rec)
                # The Prometheux gap-detector is deterministic — it runs on the stub
                # path too, and a forcing structural gap re-routes even when no live
                # reviewer panel is available (the engine is the non-silenceable voter).
                engine_gaps = _engine_gaps(trace, results, rec, query)
                if engine_gaps:
                    merged = cso.aggregate_panel_review(
                        [("scientific_reviewer", review)], routing, extra_gaps=engine_gaps)
                    review = {**review, "verdict": merged["verdict"],
                              "gaps": merged["gaps"], "panel": merged["panel"]}
                trace.event("engine_gaps", {
                    "gaps": engine_gaps,
                    "forced": any(g.get("forces_reroute") for g in engine_gaps)})
                trace.event("review", {"review": review})
            review.setdefault("source", review_src)
            autonomous_verdict = review.get("verdict", "synthesize")

            # Convergence: a reroute adds evidence if it runs an un-run skill, OR
            # asks an already-run skill a *new* question (a deeper follow-up the
            # first pass didn't pose). Resolve each gap to its *actual* skill (via
            # _reroute_task, which validates the reviewer's route_to and falls back
            # to the catalog reroute target for an invalid/missing one). Forcing
            # engine gaps sort first, so a required uncovered axis is always
            # preferred. Only an *identical* (skill, missing) repeat is skipped —
            # re-running a deterministic skill on the same question cannot improve,
            # and looping on it was the loop's old failure. If every gap is such a
            # repeat, stop and synthesize with the residual gaps.
            executed = {e.get("skill") for e in results if e.get("skill")}
            followup = gap = None
            for g in review.get("gaps") or []:
                cand = cso._reroute_task(g, routing, step_n=6 + i, executed=executed)
                missing = (g.get("missing") or "").strip()
                sig = (cand.skill, missing)
                # New skill → always actionable. Already-run skill → actionable only
                # as a *deeper follow-up*: a question-sensitive skill (live search)
                # asked a new, non-empty question it hasn't been asked yet. A
                # deterministic gene-DB skill can't yield new evidence from a reworded
                # question, and a question-less repeat adds nothing — both are skipped,
                # so the loop never thrashes re-running a covered lookup.
                deeper = (cand.skill in cso.QUESTION_SENSITIVE_SKILLS
                          and bool(missing) and sig not in rerouted_sigs)
                if cand.skill not in executed or deeper:
                    gap, followup = g, cand
                    break

            # HUMAN-IN-THE-LOOP checkpoint. Fires every pass — after the panel votes
            # and the autonomous follow-up is resolved, before anything executes — so
            # a human can approve, override the verdict (even force a re-route off a
            # `synthesize`), redirect the skill, or inject a gap. No gate → pure
            # pass-through (autonomous loop unchanged).
            verdict, followup, gap = _apply_gate(
                gate, trace, verdict=autonomous_verdict, review=review,
                followup=followup, gap=gap, iteration=i, routing=routing,
                executed=executed, step_n=6 + i)
            # A human decision is the verdict of record: reflect it in ``review`` so
            # the report / result.json carry the human-amended verdict, not the
            # panel's superseded autonomous one.
            if verdict != autonomous_verdict:
                review["verdict"] = verdict
                review["human_override"] = {"from": autonomous_verdict, "to": verdict}

            if verdict != "re-route":
                trace.step("✅", f"reviewer verdict: {verdict}")
                break
            # At the core cap, stop unless the budget still has room to chase the
            # broader desired axes — the top-of-loop check then bounds those passes.
            if i >= MAX_REROUTES and not _budget_room():
                trace.step("🛑", f"reviewer still re-routing after {MAX_REROUTES} passes; "
                           "synthesizing with residual gaps")
                break
            if followup is None:
                trace.step("✅", "no actionable gap left (every gap repeats a covered "
                           "skill+question) → synthesize with residual gaps")
                break
            rerouted_sigs.add((followup.skill, (gap.get("missing") or "").strip()))
            cap = MAX_REROUTES if within_core else "budget"
            trace.step("🔁", f"reroute {i + 1}/{cap} → {followup.skill} "
                       f"({gap.get('missing', 'gap')})")
            trace.event("phase", {"id": followup.step, "role": followup.skill,
                                  "kind": "skill", "division": followup.division + " (re-route)",
                                  "title": followup.question, "status": "running",
                                  "reroute": True, "why": gap.get("missing", "")})
            with rec.span(f"reroute:{followup.skill}", kind="tool", iteration=i + 1,
                          missing=gap.get("missing")):
                # pass the query as the live target so a reroute to lit-synthesizer
                # runs a real-time Tavily search for this target.
                # On a *deeper* repeat (same skill, new question) pass the gap's
                # ``missing`` as ``focus`` so the search chases the specific gap.
                focus = gap.get("missing") if followup.skill in executed else None
                env = cso.execute_skill(followup, case, live, target=query, focus=focus)
                results.append(env)
            trace.event("evidence", {**_evidence_event(env), "reroute": True})

            # A cached/stub reviewer can't re-evaluate the new evidence — its verdict is
            # fixed, so looping would just append duplicate re-routes. Only a *live*
            # reviewer genuinely re-reviews; honor exactly one re-route otherwise.
            if review_src != AGENT_SOURCE:
                trace.step("✅", "reviewer (cached/stub) → one re-route, then synthesize")
                break
            i += 1
        loop_sp.set(verdict=review.get("verdict", "synthesize"))
    return review


def run(query: str, out_dir: Path | None, *, backend: str, model: str | None,
        live: bool, argv: list[str], emit: "Emit | None" = None,
        quiet: bool = False, token_budget: int | None = DEFAULT_TOKEN_BUDGET,
        gate: "Gate | None" = None) -> dict[str, Any]:
    """Run the live multi-agent loop.

    ``emit`` is an optional structured-event sink: when set (the frontend supplies
    one), each phase pushes an event the UI streams as SSE — so the browser shows
    the SAME loop the CLI prints, not a re-implementation. ``quiet`` suppresses the
    console trace (the server doesn't want it). ``out_dir=None`` skips writing the
    report/result files (the streaming caller renders from the events + final dict).

    ``gate`` is an optional human-in-the-loop callback: when set, the review loop
    pauses at each pass (after the panel votes, before it acts) and applies the
    human's decision — approve, override the verdict, redirect the re-route, or
    inject a gap. Unset → the loop runs fully autonomously, unchanged.
    """
    case = cso.case_key(query)
    routing = cso.load_routing()
    runner = runners.select_runner(backend, model)
    trace = Trace(runner.name, runner.model, emit=emit, quiet=quiet)
    rec = TraceRecorder(out_dir, run_name=case, backend=runner.name, model=runner.model)

    calls_llm = runner.name != "stub"
    trace.event("start", {
        "query": query, "case": case,
        "backend": runner.name if calls_llm else "none",
        "model": runner.model if calls_llm else "none",
        "calls_llm": calls_llm,
        "mode": "live" if live else "default",
    })

    # 1 — BRIEF (live agent role) ------------------------------------------- #
    trace.event("phase", {"id": "briefing", "role": "Chief of Staff", "kind": "agent",
                          "division": "Office of CSO", "title": "Field briefing",
                          "status": "running"})
    briefing, brief_src = _agent_or_stub(
        trace, "chief_of_staff", runner, cso.CHIEF_OF_STAFF_PROMPT,
        f"User query: {query}", BRIEFING_SCHEMA,
        stub=cso.load_briefing(query, case), rec=rec)
    briefing.setdefault("source", brief_src)
    trace.event("briefing", {"briefing": briefing, "source": brief_src})

    # 2 — PLAN (live agent role; validated against routing.yaml, else deterministic) #
    subtasks, plan_experiments, plan_src = _plan(
        trace, runner, query, briefing, case, routing, rec)
    trace.step("🧭", f"plan → {len(subtasks)} routed sub-tasks ({plan_src})")
    trace.event("plan", {"subtasks": [t.as_plan_entry() for t in subtasks],
                         "source": plan_src})

    # 3 — DIVISION SCIENTISTS (one agent per division; runs its skills + interprets) #
    #     Virtual-Biotech structure: the CSO delegates each division to a domain
    #     scientist agent, run concurrently. division_findings carry their reasoning.
    with rec.span("execute", kind="tool", n_subtasks=len(subtasks)):
        results, division_findings = _run_divisions(
            subtasks, runner, query, case, live, trace, rec, target=query)

    # 4 — REVIEW → RE-ROUTE loop (change #2: bounded; verdict drives control flow) #
    #     The reviewer re-runs after each re-route until it returns `synthesize` or
    #     MAX_REROUTES is hit. Each re-route target is the reviewer's *chosen* skill,
    #     validated against the catalog (change #3) before execution.
    review = _review_loop(trace, runner, query, case, routing, results, live, rec,
                          token_budget=token_budget, gate=gate)

    # 4b — DECISION (Prometheux): derive the GO/NO-GO tier deductively from the final
    #      evidence. Authoritative for the report's Decision field; the agent narrates.
    decision = _engine_decision(trace, results, rec, query)

    # 5 — SYNTHESIZE (CSO integrates the division scientists' findings + review) -- #
    decision_ctx = (f"\n\nDeductive decision (Prometheux, authoritative tier):\n"
                    f"{json.dumps(decision, default=str)}\n"
                    "Write your recommendation consistent with this tier; it is the "
                    "Decision of record. If you disagree, argue it in the rationale."
                    if decision else "")
    open_q_ctx = (f"\n\nOpen questions the planner wanted answered but no tool could "
                  f"(fold these into proposed experiments):\n"
                  f"{json.dumps(plan_experiments, default=str)}" if plan_experiments else "")
    syn_context = (
        f"User query: {query}\n\nBriefing:\n{json.dumps(briefing, default=str)}\n\n"
        f"Division scientist findings:\n{json.dumps(division_findings, default=str)}\n\n"
        f"Evidence:\n{_evidence_context(results)}\n\n"
        f"Reviewer:\n{json.dumps(review, default=str)}{decision_ctx}{open_q_ctx}"
    )
    trace.event("phase", {"id": "synth", "role": "CSO Orchestrator", "kind": "agent",
                          "division": "Synthesis", "title": "Synthesize recommendation",
                          "status": "running", "terminal": True})
    synthesis: dict[str, Any] | None
    synthesis, _ = _agent_or_stub(
        trace, "cso_synthesis", runner, cso.ORCHESTRATOR_PROMPT,
        syn_context, SYNTHESIS_SCHEMA, stub={}, rec=rec)
    if not synthesis:  # stub path returns {} → let the report show "pending"
        synthesis = None
    trace.event("synthesis", {"synthesis": synthesis})

    # The derived tier is the Decision of record; the agent's free-text is rationale.
    agent_decision = (synthesis or {}).get("decision")
    decision_tier = (decision or {}).get("tier") or agent_decision or "REVIEW"
    trace.event("decision", {
        "decision": decision_tier,
        "decision_source": "prometheux" if decision else "agent",
        "agent_decision": agent_decision,
        "engine": decision,
        "diverges": bool(decision and agent_decision
                         and agent_decision != decision["tier"]),
        "confidence": (synthesis or {}).get("confidence", "n/a"),
    })

    # 6 — ASSEMBLE (reuse cso's renderer + output contract) ----------------- #
    report_md = cso.synthesize_report(query, case, briefing, results, review, synthesis,
                                      decision_engine=decision)
    report_path = result_path = None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / "report.md"
        report_path.write_text(report_md, encoding="utf-8")

        summary, data = _build_envelope(query, case, briefing, subtasks, results, review,
                                        synthesis, runner, backend, live,
                                        division_findings=division_findings,
                                        decision_engine=decision,
                                        plan_experiments=plan_experiments)
        result_path = cso._write_result_json(out_dir, summary, data)
        cso._write_reproducibility(out_dir / "reproducibility", argv,
                                   [report_path, result_path])
        # Project the verdict into decision facts every run (same target derivation
        # as _engine_decision), so the run's conclusion is durable as facts.
        import re as _re
        _m = _re.search(r"\b([A-Z][A-Z0-9]{1,6}(?:-[A-Z0-9]+)?)\b", query or "")
        _target = _m.group(1) if _m else (query or "target")
        _project_decision_facts(trace, decision, _target, out_dir, out_dir.name)
    else:
        summary, data = _build_envelope(query, case, briefing, subtasks, results, review,
                                        synthesis, runner, backend, live,
                                        division_findings=division_findings,
                                        decision_engine=decision,
                                        plan_experiments=plan_experiments)

    # Finalise the execution trace (span tree + timing + token totals).
    trace_path = rec.close(query=query, decision=summary.get("decision"),
                           reviewer_verdict=summary.get("reviewer_verdict"),
                           calls_llm=summary.get("calls_llm"))
    if trace_path is not None:
        tok = rec.totals.get("total_tokens", 0)
        trace.step("🧾", f"trace: {tok} tokens across spans → {trace_path.name}")
    summary["trace_tokens"] = rec.totals.get("total_tokens", 0)

    trace.event("done", {
        "report_md": report_md,
        "decision": summary.get("decision"),
        "decision_source": summary.get("decision_source"),
        "confidence": summary.get("confidence"),
        "n_steps": summary.get("n_steps"),
        "reviewer_verdict": summary.get("reviewer_verdict"),
    })
    if report_path is not None:
        trace.done(str(report_path))
    return {"report": str(report_path) if report_path else None,
            "result": str(result_path) if result_path else None,
            "trace": str(trace_path) if trace_path else None,
            "summary": summary, "data": data, "report_md": report_md,
            "decision_engine": decision}


def _execute_steps(subtasks: list[cso.Subtask], case: str, live: bool,
                   target: str | None) -> dict[str, dict[str, Any]]:
    """Run a division's routed steps respecting depends_on; independent ones parallel.

    Returns {step_id: evidence_envelope}. This is the *tool layer* a division
    scientist agent drives — the deterministic data acquisition, no interpretation."""
    done: dict[str, dict[str, Any]] = {}
    remaining = list(subtasks)
    while remaining:
        ready = [t for t in remaining if all(d in done for d in t.depends_on)]
        if not ready:  # safety: break dependency deadlock by running the rest
            ready = remaining
        with ThreadPoolExecutor(max_workers=max(1, len(ready))) as pool:
            for task, env in zip(ready, pool.map(
                    lambda t: cso.execute_skill(t, case, live, target=target), ready)):
                done[task.step] = env
        remaining = [t for t in remaining if t.step not in done]
    return done


def _run_divisions(subtasks: list[cso.Subtask], runner: runners.Runner, query: str,
                   case: str, live: bool, trace: Trace, rec: TraceRecorder,
                   target: str | None = None
                   ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Virtual-Biotech structure: one **division scientist agent** per division.

    The CSO delegates each division to a domain-specialised scientist agent that
    (1) runs its routed skills (its tools, via _execute_steps) and (2) interprets the
    raw output into a division finding. Divisions run **concurrently** — N parallel
    scientist agents, mirroring the paper's cross-functional R&D org. Without a live
    backend the interpretation degrades to an honest stub (raw evidence still flows).

    Returns (evidence_steps, division_findings) — evidence preserves the existing
    per-step contract the reviewer/report consume; findings are the agents' reasoning.
    """
    groups = cso.group_by_division(subtasks)
    prompt = _read_prompt(cso.DIVISION_SCIENTIST_PROMPT)

    # Announce every routed skill as a running phase up front (in plan order), so
    # the UI shows the full division roster before the concurrent agents report back.
    for t in subtasks:
        trace.event("phase", {"id": t.step, "role": t.skill, "kind": "skill",
                              "division": t.division, "title": t.question,
                              "status": "running"})

    def _scientist(division: str, tasks: list[cso.Subtask]
                   ) -> tuple[str, dict[str, dict[str, Any]], dict[str, Any]]:
        with rec.span(f"scientist:{division}", kind="agent", backend=runner.name,
                      model=runner.model, n_skills=len(tasks)) as sp:
            t0 = time.perf_counter()
            done = _execute_steps(tasks, case, live, target)  # the agent's tools
            sp.set(exec_ms=round((time.perf_counter() - t0) * 1000.0, 2))
            evidence_ctx = _evidence_context([done[t.step] for t in tasks])
            ctx = (f"Your division: {division}\nUser query: {query}\n\n"
                   f"Raw skill output for your division:\n{evidence_ctx}")
            try:
                finding = runners.run_with_retry(
                    runner, prompt, ctx, DIVISION_FINDING_SCHEMA)
                finding["division"] = division
                finding["source"] = AGENT_SOURCE
                sp.record_usage(**_usage_of(runner)).set(
                    grade=finding.get("evidence_grade"))
            except Exception as exc:  # noqa: BLE001 — degrade, never fabricate
                sp.status = "stub"
                sp.set(degraded="no-backend" if isinstance(exc, runners.NoBackendError)
                       else "agent-failed", reason=str(exc))
                finding = {"division": division, "interpretation": None,
                           "confidence": "n/a", "caveats": [], "evidence_grade": None,
                           "source": cso.DELEGATE}
            return division, done, finding

    with rec.span("divisions", kind="loop", n_divisions=len(groups)):
        with ThreadPoolExecutor(max_workers=max(1, len(groups))) as pool:
            results = list(pool.map(lambda g: _scientist(*g), groups))

    merged: dict[str, dict[str, Any]] = {}
    findings: list[dict[str, Any]] = []
    for division, done, finding in results:
        merged.update(done)
        findings.append(finding)
        live_tag = "🧪 stub" if finding.get("source") == cso.DELEGATE else \
            f"{finding.get('evidence_grade', '?')}"
        trace.step("🔬", f"division scientist [{division}]: {len(done)} skill(s) "
                   f"→ {live_tag}")
        trace.event("division_finding", {"division": division, "finding": finding,
                                         "n_skills": len(done)})
    # Stream each completed step's evidence in stable plan order (the work ran
    # concurrently; ordered emission keeps the SSE stream + graph build deterministic).
    evidence = [merged[t.step] for t in subtasks]
    for env in evidence:
        trace.event("evidence", _evidence_event(env))
    return evidence, findings


def _evidence_event(env: dict[str, Any]) -> dict[str, Any]:
    """Normalize one routed-step result into a graph/report-ready event payload.

    Shared by the streaming UI (graph ingestion) and any caller that wants the
    graded, provenance-tagged view of a step without reaching into cso internals."""
    prov_icon, prov_note = cso._provenance(env)
    return {
        "step": env["step"], "division": env["division"], "skill": env["skill"],
        "question": env.get("question", ""), "result": env.get("result", {}),
        "grade": cso._evidence_grade(env), "provenance": prov_icon,
        "provenance_note": prov_note, "reference": cso._evidence_reference(env),
        "digest": cso._result_digest(env), "source": env.get("source", ""),
    }


def _build_envelope(query, case, briefing, subtasks, results, review, synthesis,
                    runner, backend, live, division_findings=None,
                    decision_engine=None, plan_experiments=None
                    ) -> tuple[dict[str, Any], dict[str, Any]]:
    """Mirror cso.run()'s result.json envelope, marking the live-agent loop."""
    syn = synthesis or {}
    references = [
        {"n": i, "skill": e["skill"], "provenance": cso._provenance(e)[0],
         "grade": cso._evidence_grade(e), "source": cso._evidence_reference(e), "step": e["step"]}
        for i, e in enumerate(results, 1)
    ]
    evidence_gaps = (
        [f"{e['division']}/{e['skill']} ({e['step']}): {cso._provenance(e)[1]}"
         for e in results if cso._evidence_grade(e) == "absent"]
        + [g.get("missing") for g in review.get("gaps", [])]
        + list(syn.get("evidence_gaps", []))
    )
    # Proposed experiments = synthesis + reviewer + the planner's unbindable open
    # questions (the agent knew what it wanted but no functional tool answered it).
    proposed = (list(syn.get("proposed_experiments", []))
                + list(review.get("experiments", []))
                + list(plan_experiments or []))
    calls_llm = runner.name != "stub"
    summary = {
        "query": query, "case": case,
        "mode": "live" if live else "default",
        "loop": "live-agent-harness",
        "backend": runner.name if calls_llm else "none",
        "model": runner.model if calls_llm else "none",
        "n_steps": len(results),
        "reviewer_verdict": review.get("verdict", "synthesize"),
        "n_executed": len([e for e in results if e.get("source") == "clawbio"]),
        # Derived tier is the decision of record when the engine ran; the agent's
        # free-text is kept alongside so a divergence is auditable, not erased.
        "decision": (decision_engine or {}).get("tier") or syn.get("decision", "REVIEW"),
        "decision_source": "prometheux" if decision_engine else "agent",
        "agent_decision": syn.get("decision"),
        "decision_engine": decision_engine,
        "confidence": syn.get("confidence", "n/a"),
        "calls_llm": calls_llm,
    }
    data = {
        "briefing": briefing,
        "plan": [t.as_plan_entry() for t in subtasks],
        "division_findings": division_findings or [],
        "evidence": results,
        "review": review,
        "synthesis": synthesis,
        "references": references,
        "evidence_gaps": evidence_gaps,
        "proposed_experiments": proposed,
        "disclaimer": cso.DISCLAIMER,
    }
    return summary, data


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="harness.py",
        description="Run virtual-biotech-cso as a live multi-agent loop "
        "(Chief of Staff · division scientists · Scientific Reviewer · CSO synthesis).")
    p.add_argument("--query", type=str, default=cso.DEFAULT_QUERY,
                   help=f"Target-assessment query (default: {cso.DEFAULT_QUERY!r})")
    p.add_argument("--backend", choices=["auto", "anthropic", "openai", "gemini", "claude-cli"],
                   default="auto",
                   help="Agent backend (default: auto — Anthropic/OpenAI key, else claude CLI)")
    p.add_argument("--model", type=str, default=None, help="Override the model id")
    p.add_argument("--live", action="store_true",
                   help="Execute routed skills via the ClawBio runtime")
    p.add_argument("--output", "--out", dest="out", type=str, default="./output",
                   help="Output directory")
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out).expanduser().resolve()
    summary = run(args.query, out_dir, backend=args.backend, model=args.model,
                  live=args.live, argv=argv)
    print("\n" + json.dumps(summary["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
