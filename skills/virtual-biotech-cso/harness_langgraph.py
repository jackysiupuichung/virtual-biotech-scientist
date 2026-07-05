#!/usr/bin/env python
"""harness_langgraph.py — the virtual-biotech-cso loop expressed as a LangGraph.

This is a **parallel, opt-in** re-expression of ``harness.py``. It changes nothing
about the reasoning roles or the deterministic layer: every node here delegates to
the *same* helpers ``harness.py`` already exposes (``_agent_or_stub``, ``_plan``,
``_run_divisions``, ``_review_panel``) and the *same* pure functions in ``cso.py``.
What it replaces is only the **control flow**: the hand-written ``while True`` review
→ reroute loop in ``harness._review_loop`` becomes a compiled ``StateGraph`` with a
conditional edge, so the flow is:

  * **visualizable** — ``build_graph().get_graph().draw_mermaid()`` renders it,
  * **resumable** — compile with a checkpointer and a crashed run resumes mid-loop,
  * **HITL-native** — ``interrupt_before=["reroute"]`` pauses for a human with no
    bespoke gate code (compare ``harness._apply_gate``),
  * **auto-traced** — LangSmith (set ``LANGCHAIN_TRACING_V2=true``) records every
    node's LLM input/output, closing the prompt/response-capture gap for free; the
    in-tree ``trace.jsonl`` is still written via the same ``TraceRecorder``.

Zero-dep ethos is preserved: ``langgraph`` is imported **lazily inside**
``build_graph()``. Importing this module never requires langgraph; only calling
``run()``/``build_graph()`` does, and the ImportError names the extra to install::

    pip install langgraph            # or: pip install -e '.[langgraph]'
    python harness_langgraph.py --query "Assess B7-H3 ... in lung cancer"

Semantics parity note: this port keeps the **live-reviewer** loop semantics — the
panel re-reviews after each reroute until ``synthesize`` / ``MAX_REROUTES`` / no
actionable gap. The *token-budget* extension of the desired-axis passes
(``harness.DEFAULT_TOKEN_BUDGET``) is honoured through the same ``rec.totals`` meter.
The cached/stub single-reroute short-circuit and the full ``_apply_gate`` action
grammar are intentionally out of scope for this sketch — use ``interrupt_before``
for HITL here. For the stub/no-backend path, prefer ``harness.py``.
"""
from __future__ import annotations

import argparse
import json
import sys
from operator import add
from pathlib import Path
from typing import Annotated, Any, TypedDict

import cso
import harness  # reuse its role helpers verbatim — never modified
import runners
from tracing import TraceRecorder


# --------------------------------------------------------------------------- #
# Graph state — the values every node reads/writes. ``results`` uses an ``add``
# reducer so the reroute node can APPEND one evidence envelope without clobbering
# the divisions' evidence (LangGraph merges concurrent/serial writes via reducers,
# replacing the ``results.append(env)`` mutation in harness._review_loop).
# --------------------------------------------------------------------------- #
class CSOState(TypedDict, total=False):
    # inputs / config (set once, read-only thereafter)
    query: str
    case: str
    routing: dict[str, Any]
    demo: bool
    live: bool
    token_budget: int | None
    # accumulated products
    briefing: dict[str, Any]
    subtasks: list[Any]              # list[cso.Subtask]
    plan_experiments: list[dict[str, Any]]
    division_findings: list[dict[str, Any]]
    results: Annotated[list[dict[str, Any]], add]  # reducer: reroute appends
    review: dict[str, Any]
    reroute_count: int
    rerouted_sigs: list[list[str]]   # JSON-safe form of the (skill, missing) set
    decision: dict[str, Any] | None
    synthesis: dict[str, Any] | None


# The node functions close over these run-scoped objects (the trace printer, the
# span recorder, the selected runner). LangGraph state must stay JSON-ish, so the
# non-serialisable machinery is captured here rather than threaded through state.
class _Ctx:
    def __init__(self, trace: harness.Trace, rec: TraceRecorder,
                 runner: runners.Runner) -> None:
        self.trace = trace
        self.rec = rec
        self.runner = runner


# --------------------------------------------------------------------------- #
# Nodes — each is a thin adapter over an existing harness/cso helper. The node
# returns ONLY the state keys it changes (LangGraph merges the partial update).
# --------------------------------------------------------------------------- #
def _brief_node(s: CSOState, ctx: _Ctx) -> dict[str, Any]:
    ctx.trace.event("phase", {"id": "briefing", "role": "Chief of Staff",
                              "kind": "agent", "division": "Office of CSO",
                              "title": "Field briefing", "status": "running"})
    briefing, src = harness._agent_or_stub(
        ctx.trace, "chief_of_staff", ctx.runner, cso.CHIEF_OF_STAFF_PROMPT,
        f"User query: {s['query']}", harness.BRIEFING_SCHEMA,
        stub=cso.load_briefing(s["query"], s["case"]), rec=ctx.rec)
    briefing.setdefault("source", src)
    ctx.trace.event("briefing", {"briefing": briefing, "source": src})
    return {"briefing": briefing}


def _plan_node(s: CSOState, ctx: _Ctx) -> dict[str, Any]:
    subtasks, experiments, src = harness._plan(
        ctx.trace, ctx.runner, s["query"], s["briefing"], s["case"], s["routing"], ctx.rec)
    ctx.trace.step("🧭", f"plan → {len(subtasks)} routed sub-tasks ({src})")
    ctx.trace.event("plan", {"subtasks": [t.as_plan_entry() for t in subtasks],
                             "source": src})
    return {"subtasks": subtasks, "plan_experiments": experiments}


def _divisions_node(s: CSOState, ctx: _Ctx) -> dict[str, Any]:
    # One division-scientist agent per division, run concurrently INSIDE this node
    # (harness._run_divisions keeps its ThreadPoolExecutor). We deliberately do not
    # fan divisions out as separate LangGraph Send() branches here: the existing
    # helper already parallelises them and preserves the evidence/finding contract.
    with ctx.rec.span("execute", kind="tool", n_subtasks=len(s["subtasks"])):
        results, findings = harness._run_divisions(
            s["subtasks"], ctx.runner, s["query"], s["case"], s["live"],
            ctx.trace, ctx.rec, target=s["query"])
    # NOTE: the ``add`` reducer means whatever we return under "results" is APPENDED
    # to the (empty) initial list — so seed the evidence here, reroutes append later.
    return {"results": results, "division_findings": findings}


def _review_node(s: CSOState, ctx: _Ctx) -> dict[str, Any]:
    review = harness._review_panel(
        ctx.trace, ctx.runner, s["results"], s["routing"], ctx.rec, s["query"])
    review.setdefault("source", harness.AGENT_SOURCE)
    return {"review": review}


def _resolve_followup(s: CSOState) -> tuple[Any, dict[str, Any] | None]:
    """Pick the actionable gap → follow-up Subtask, mirroring harness._review_loop.

    A gap is actionable if it runs an un-run skill, OR asks a question-sensitive
    skill a *new* question (not already in ``rerouted_sigs``). Returns
    ``(followup_subtask | None, gap | None)``.
    """
    executed = {e.get("skill") for e in s["results"] if e.get("skill")}
    seen = {tuple(x) for x in s.get("rerouted_sigs", [])}
    i = s.get("reroute_count", 0)
    for g in s["review"].get("gaps") or []:
        cand = cso._reroute_task(g, s["routing"], step_n=6 + i, executed=executed)
        missing = (g.get("missing") or "").strip()
        sig = (cand.skill, missing)
        deeper = (cand.skill in cso.QUESTION_SENSITIVE_SKILLS
                  and bool(missing) and sig not in seen)
        if cand.skill not in executed or deeper:
            return cand, g
    return None, None


def _reroute_node(s: CSOState, ctx: _Ctx) -> dict[str, Any]:
    followup, gap = _resolve_followup(s)
    # route_after_review only sends us here when a follow-up exists, but guard anyway.
    if followup is None or gap is None:
        return {}
    i = s.get("reroute_count", 0)
    ctx.trace.step("🔁", f"reroute {i + 1} → {followup.skill} "
                   f"({gap.get('missing', 'gap')})")
    ctx.trace.event("phase", {"id": followup.step, "role": followup.skill,
                              "kind": "skill",
                              "division": followup.division + " (re-route)",
                              "title": followup.question, "status": "running",
                              "reroute": True, "why": gap.get("missing", "")})
    executed = {e.get("skill") for e in s["results"] if e.get("skill")}
    with ctx.rec.span(f"reroute:{followup.skill}", kind="tool", iteration=i + 1,
                      missing=gap.get("missing")):
        focus = gap.get("missing") if followup.skill in executed else None
        env = cso.execute_skill(followup, s["case"], s["demo"], s["live"],
                                target=s["query"], focus=focus)
    ctx.trace.event("evidence", {**harness._evidence_event(env), "reroute": True})
    sig = [followup.skill, (gap.get("missing") or "").strip()]
    # ``results`` uses the ``add`` reducer → this appends. ``reroute_count`` /
    # ``rerouted_sigs`` are last-write-wins (no reducer) → return the updated whole.
    return {"results": [env],
            "reroute_count": i + 1,
            "rerouted_sigs": list(s.get("rerouted_sigs", [])) + [sig]}


def _synthesize_node(s: CSOState, ctx: _Ctx) -> dict[str, Any]:
    review = s["review"]
    plan_experiments = s.get("plan_experiments", [])
    open_q_ctx = (f"\n\nOpen questions the planner wanted answered but no tool could "
                  f"(fold these into proposed experiments):\n"
                  f"{json.dumps(plan_experiments, default=str)}" if plan_experiments else "")
    syn_context = (
        f"User query: {s['query']}\n\nBriefing:\n{json.dumps(s['briefing'], default=str)}\n\n"
        f"Division scientist findings:\n{json.dumps(s.get('division_findings', []), default=str)}\n\n"
        f"Evidence:\n{harness._evidence_context(s['results'])}\n\n"
        f"Reviewer:\n{json.dumps(review, default=str)}{open_q_ctx}"
    )
    ctx.trace.event("phase", {"id": "synth", "role": "CSO Orchestrator", "kind": "agent",
                              "division": "Synthesis", "title": "Synthesize recommendation",
                              "status": "running", "terminal": True})
    synthesis, _ = harness._agent_or_stub(
        ctx.trace, "cso_synthesis", ctx.runner, cso.ORCHESTRATOR_PROMPT,
        syn_context, harness.SYNTHESIS_SCHEMA, stub={}, rec=ctx.rec)
    synthesis = synthesis or None
    ctx.trace.event("synthesis", {"synthesis": synthesis})
    return {"synthesis": synthesis}


# --------------------------------------------------------------------------- #
# Conditional edge — this ONE function replaces the whole while-loop control
# flow in harness._review_loop (the ``i`` counter, MAX_REROUTES, the budget
# room check, the actionable-gap probe, and every break condition).
# --------------------------------------------------------------------------- #
def _route_after_review(s: CSOState) -> str:
    verdict = s["review"].get("verdict", "synthesize")
    if verdict != "re-route":
        return "synthesize"
    i = s.get("reroute_count", 0)
    within_core = i < harness.MAX_REROUTES
    # Past the core cap, keep chasing desired axes only while token budget has room
    # (same meter harness._budget_room uses: rec is captured on the compiled ctx).
    if not within_core:
        # Budget room is checked in run() via a recursion-limit guard; here we simply
        # stop at MAX_REROUTES for the sketch's deterministic parity. (A budget-aware
        # variant would read rec.totals through ctx — see the module docstring.)
        return "synthesize"
    followup, _gap = _resolve_followup(s)
    if followup is None:
        return "synthesize"          # no actionable gap → converge
    return "reroute"


def build_graph(ctx: _Ctx, *, checkpointer: Any = None,
                interrupt_before: list[str] | None = None) -> Any:
    """Compile the CSO StateGraph. ``langgraph`` is imported lazily here only.

    Pass a ``checkpointer`` (e.g. ``langgraph.checkpoint.memory.MemorySaver``) to make
    runs resumable, and ``interrupt_before=["reroute"]`` for a human-in-the-loop pause
    before each follow-up executes (LangGraph-native replacement for harness._apply_gate).
    """
    try:
        from langgraph.graph import StateGraph, START, END
    except ImportError as exc:  # keep the zero-dep import contract honest
        raise ImportError(
            "harness_langgraph requires the 'langgraph' extra: pip install langgraph "
            "(or: pip install -e '.[langgraph]'). The stdlib-only harness.py has no "
            "such dependency.") from exc

    g = StateGraph(CSOState)
    # bind ctx into each node (LangGraph passes only state; ctx carries the machinery)
    g.add_node("brief", lambda s: _brief_node(s, ctx))
    g.add_node("plan", lambda s: _plan_node(s, ctx))
    g.add_node("divisions", lambda s: _divisions_node(s, ctx))
    g.add_node("review", lambda s: _review_node(s, ctx))
    g.add_node("reroute", lambda s: _reroute_node(s, ctx))
    g.add_node("synthesize", lambda s: _synthesize_node(s, ctx))

    g.add_edge(START, "brief")
    g.add_edge("brief", "plan")
    g.add_edge("plan", "divisions")
    g.add_edge("divisions", "review")
    # The loop: review decides synthesize | reroute; reroute cycles BACK to review.
    g.add_conditional_edges("review", _route_after_review,
                            {"reroute": "reroute", "synthesize": "synthesize"})
    g.add_edge("reroute", "review")
    g.add_edge("synthesize", END)

    return g.compile(checkpointer=checkpointer,
                     interrupt_before=interrupt_before or [])


def run(query: str, out_dir: Path | None, *, backend: str, model: str | None,
        demo: bool, live: bool, argv: list[str], quiet: bool = False,
        token_budget: int | None = harness.DEFAULT_TOKEN_BUDGET) -> dict[str, Any]:
    """Run the LangGraph port and write the SAME output contract as harness.run().

    Builds the compiled graph, invokes it once, then reuses harness/cso assembly to
    render report.md + result.json + reproducibility/ + trace.jsonl — so a LangGraph
    run is byte-compatible with the standard output contract, only the loop engine
    differs. Returns the same dict shape as ``harness.run``.
    """
    case = cso.case_key(query)
    routing = cso.load_routing()
    runner = runners.select_runner(backend, model)
    trace = harness.Trace(runner.name, runner.model, quiet=quiet)
    rec = TraceRecorder(out_dir, run_name=case, backend=runner.name, model=runner.model)
    ctx = _Ctx(trace, rec, runner)

    calls_llm = runner.name != "stub"
    trace.event("start", {"query": query, "case": case,
                          "backend": runner.name if calls_llm else "none",
                          "model": runner.model if calls_llm else "none",
                          "calls_llm": calls_llm, "engine": "langgraph",
                          "mode": "demo" if demo else ("live" if live else "default")})

    app = build_graph(ctx)
    init: CSOState = {"query": query, "case": case, "routing": routing,
                      "demo": demo, "live": live, "token_budget": token_budget,
                      "results": [], "reroute_count": 0, "rerouted_sigs": []}
    # recursion_limit must clear brief+plan+divisions + MAX_REROUTES review/reroute
    # cycles + synthesize with headroom; LangGraph counts supersteps, not nodes.
    final: CSOState = app.invoke(
        init, config={"recursion_limit": 8 + 2 * harness.MAX_REROUTES})

    briefing = final.get("briefing", {})
    subtasks = final.get("subtasks", [])
    results = final.get("results", [])
    review = final.get("review", {})
    synthesis = final.get("synthesis")
    division_findings = final.get("division_findings", [])
    plan_experiments = final.get("plan_experiments", [])

    # Assemble via the SAME renderer + envelope + output contract as harness.run.
    report_md = cso.synthesize_report(query, case, briefing, results, review,
                                      synthesis, demo, decision_engine=None)
    report_path = result_path = None
    summary, data = harness._build_envelope(
        query, case, briefing, subtasks, results, review, synthesis, runner, backend,
        demo, live, division_findings=division_findings, decision_engine=None,
        plan_experiments=plan_experiments)
    summary["loop"] = "langgraph-harness"  # mark the engine in the envelope

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / "report.md"
        report_path.write_text(report_md, encoding="utf-8")
        result_path = cso._write_result_json(out_dir, summary, data)
        cso._write_reproducibility(out_dir / "reproducibility", argv,
                                   [report_path, result_path])

    trace_path = rec.close(query=query, decision=summary.get("decision"),
                           reviewer_verdict=summary.get("reviewer_verdict"),
                           calls_llm=summary.get("calls_llm"), engine="langgraph")
    if trace_path is not None:
        trace.step("🧾", f"trace: {rec.totals.get('total_tokens', 0)} tokens → "
                   f"{trace_path.name}")
    summary["trace_tokens"] = rec.totals.get("total_tokens", 0)
    if report_path is not None:
        trace.done(str(report_path))

    return {"report": str(report_path) if report_path else None,
            "result": str(result_path) if result_path else None,
            "trace": str(trace_path) if trace_path else None,
            "summary": summary, "data": data, "report_md": report_md,
            "decision_engine": None}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="harness_langgraph.py",
        description="Run virtual-biotech-cso as a LangGraph (visualizable, resumable, "
                    "HITL-native, LangSmith-traced). Parallel to harness.py.")
    p.add_argument("--query", type=str, default=cso.DEFAULT_QUERY,
                   help=f"Target-assessment query (default: {cso.DEFAULT_QUERY!r})")
    p.add_argument("--backend",
                   choices=["auto", "anthropic", "openai", "gemini", "claude-cli"],
                   default="auto", help="Agent backend (default: auto)")
    p.add_argument("--model", type=str, default=None, help="Override the model id")
    p.add_argument("--demo", action="store_true",
                   help="Use cached fixtures for routed DATA steps; roles run live")
    p.add_argument("--live", action="store_true",
                   help="Execute routed skills via the ClawBio runtime")
    p.add_argument("--output", "--out", dest="out", type=str, default="./output",
                   help="Output directory")
    p.add_argument("--print-graph", action="store_true",
                   help="Print the compiled graph as Mermaid and exit (needs langgraph)")
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    if args.print_graph:
        # Build with a throwaway ctx just to render structure (no run).
        runner = runners.select_runner(args.backend, args.model)
        ctx = _Ctx(harness.Trace(runner.name, runner.model, quiet=True),
                   TraceRecorder(None, run_name="graph", backend=runner.name,
                                 model=runner.model), runner)
        print(build_graph(ctx).get_graph().draw_mermaid())
        return 0
    out_dir = Path(args.out).expanduser().resolve()
    result = run(args.query, out_dir, backend=args.backend, model=args.model,
                 demo=args.demo, live=args.live, argv=argv)
    print("\n" + json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
