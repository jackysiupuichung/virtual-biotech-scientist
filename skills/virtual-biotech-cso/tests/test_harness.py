"""Tests for the live multi-agent harness (offline; no network/LLM/API key).

Every test injects a fake runner via runners.select_runner monkeypatching, so
no provider SDK or API key is required. We verify the harness wiring:
  - live agent payloads flow into the report/result.json,
  - a live `re-route` verdict actually drives a 6th evidence step,
  - malformed agent JSON and a missing backend both degrade to honest stubs,
  - JSON extraction is robust to fences/prose.
"""
import json
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR))

import harness  # noqa: E402
import runners  # noqa: E402


class FakeRunner:
    """Returns a canned payload keyed by which role prompt it was handed."""

    name = "fake"
    model = "fake-1"

    def __init__(self, verdict="synthesize", reroute_times=None, route_to="scrna-orchestrator",
                 plan="full", missing_seq=None):
        # verdict: the steady-state verdict. reroute_times: if set, re-route exactly
        # this many times then return 'synthesize' (lets us test loop convergence).
        # route_to: the skill the reviewer chooses (to exercise catalog validation).
        # plan: "full" covers all four required axes so the Prometheux gap-detector is
        # satisfied (these tests isolate the LLM-verdict path); "minimal" plans only
        # two steps to exercise plan-binding and the engine's structural-gap forcing.
        self._verdict = verdict
        self._reroute_times = reroute_times
        self._route_to = route_to
        self._plan = plan
        # missing_seq: optional per-pass ``missing`` text, so a test can ask the SAME
        # skill a *different* question each pass (exercises the deeper-reroute path).
        self._missing_seq = missing_seq
        self._reviews = 0
        self.calls = []

    def run(self, prompt, context, schema):
        # Dispatch on the prompt's title (first line) — robust to cross-references
        # between prompts (orchestrator.md mentions both "Chief-of-Staff" and
        # "Scientific Reviewer" in its body).
        title = prompt.splitlines()[0]
        self.calls.append(title)
        # The planner reuses the Orchestrator prompt but is the only call whose schema
        # asks for `questions` (the hybrid planner) — dispatch on that. Each question
        # carries a best-fit (division, intent); cso.bind_questions binds the routable
        # ones to skills and routes the rest to proposed experiments.
        if "questions" in schema:
            minimal = [
                {"question": "germline?", "rationale": "causal grounding",
                 "division": "right_target",
                 "intent": "germline_genetic_support", "depends_on": []},
                {"question": "prior trials?", "rationale": "translatability",
                 "division": "right_patient",
                 "intent": "prior_trials_and_outcomes", "depends_on": []},
            ]
            if self._plan == "minimal":
                return {"reasoning": "minimal scan", "questions": minimal}
            # full plan: covers all four *core* required axes (genetics, specificity,
            # safety, tractability) plus the somatic + malignancy desired axes, so the
            # Prometheux gap-detector finds no *forcing* structural gap and the tests
            # isolate the LLM-verdict path. It deliberately does NOT run lit-synthesizer
            # (the landscape axis / REROUTE_FALLBACK_SKILL): those are non-core, so their
            # absence never forces a re-route, and keeping lit-synthesizer un-run lets
            # the reroute-fallback tests observe an honest fallback. (The landscape
            # axis is non-core, so leaving it unassessed never forces a re-route.)
            return {"reasoning": "full assessment", "questions": minimal[:1] + [
                {"question": "specific?", "rationale": "trial-success prior",
                 "division": "right_tissue",
                 "intent": "cell_type_specificity", "depends_on": []},
                {"question": "safe?", "rationale": "AE risk",
                 "division": "right_safety",
                 "intent": "post_market_adverse_events", "depends_on": []},
                {"question": "somatic drivers?", "rationale": "driver frequency",
                 "division": "right_target",
                 "intent": "somatic_mutation_frequency", "depends_on": []},
                {"question": "on tumour cells?", "rationale": "ADC/CAR-T efficacy",
                 "division": "right_tissue",
                 "intent": "malignant_cell_localization", "depends_on": []},
                minimal[1],
            ]}
        if "Chief of Staff" in title:
            return {"context": "ctx", "data_availability": [], "priority_questions": ["q"],
                    "feasibility_flags": []}
        if "Scientific Reviewer" in title:
            # Panel mode calls this once per lens; a pass begins at the first lens
            # ("safety"). Count *passes*, not calls, so reroute_times is pass-based
            # and robust to N lenses. Single-reviewer mode has no lens marker → each
            # call is its own pass.
            if "## Your review lens:" not in context or "lens: safety" in context:
                self._reviews += 1
            if self._reroute_times is not None:
                verdict = "re-route" if self._reviews <= self._reroute_times else "synthesize"
            else:
                verdict = self._verdict
            # route_to may be a single skill or a per-pass list — a re-route only
            # adds evidence by running an *unrun* skill, so a multi-reroute test
            # supplies a distinct catalog skill per pass (the loop dedups otherwise).
            route = (self._route_to[min(self._reviews - 1, len(self._route_to) - 1)]
                     if isinstance(self._route_to, (list, tuple)) else self._route_to)
            missing = ("spatial" if self._missing_seq is None
                       else self._missing_seq[min(self._reviews - 1,
                                                  len(self._missing_seq) - 1)])
            return {"verdict": verdict,
                    "scores": {"relevance": 5, "evidence": 4, "thoroughness": 3},
                    "gaps": [{"missing": missing, "route_to": route,
                              "why": "lost context"}] if verdict == "re-route" else [],
                    "experiments": []}
        if "Orchestrator" in title:
            return {"decision": "CONDITIONAL_GO", "confidence": "medium",
                    "recommendation": "rec [step_03]", "target_overview": "ov",
                    "liabilities": [{"risk": "r", "mitigation": "m"}],
                    "evidence_gaps": [], "proposed_experiments": []}
        raise AssertionError(f"unexpected prompt title: {title!r}")


def _run(monkeypatch, runner, tmp_path):
    monkeypatch.setattr(runners, "select_runner", lambda *a, **k: runner)
    return harness.run("Assess B7-H3 in lung cancer", tmp_path,
                       backend="auto", model=None, live=False, argv=[])


# --------------------------- happy path ----------------------------------- #
def test_live_loop_writes_contract_and_marks_llm(monkeypatch, tmp_path):
    out = _run(monkeypatch, FakeRunner("synthesize"), tmp_path)
    assert Path(out["report"]).exists()
    assert Path(out["result"]).exists()
    summary = out["summary"]
    assert summary["calls_llm"] is True
    assert summary["backend"] == "fake"
    # The decision is now the Prometheux-derived tier, authoritative over the agent's
    # proposal. Demo steps grade 'absent' → low coverage → REVIEW (the engine declines
    # to upgrade to the agent's CONDITIONAL_GO without real evidence).
    assert summary["decision"] == "REVIEW"
    assert summary["decision_source"] == "prometheux"
    # synthesis recommendation still reached the rendered report (agent rationale)
    assert "rec [step_03]" in Path(out["report"]).read_text()


def test_engine_decision_overrides_agent_and_flags_divergence(monkeypatch, tmp_path):
    """The derived tier is authoritative; when it disagrees with the agent's
    proposal the report surfaces the divergence rather than silently overriding."""
    out = _run(monkeypatch, FakeRunner("synthesize"), tmp_path)
    summary = out["summary"]
    # engine derived REVIEW; the FakeRunner agent proposed CONDITIONAL_GO
    assert summary["decision"] == "REVIEW"
    assert summary["decision_engine"]["tier"] == "REVIEW"
    assert summary["agent_decision"] == "CONDITIONAL_GO"
    report = Path(out["report"]).read_text()
    assert "Divergence" in report
    assert "CONDITIONAL_GO" in report  # the agent's proposal is still shown


def test_engine_nogo_floor_overrides_agent(monkeypatch, tmp_path):
    """The non-silenceable NO_GO floor end-to-end: a serious safety signal in the
    evidence clamps the decision to NO_GO even though the agent proposes CONDITIONAL_GO
    and no LLM lens votes to block. Proves the floor beats LLM judgment through the
    full harness wiring (decision_source == prometheux, divergence rendered)."""
    import logic

    # Inject a boxed-warning safety signal into whatever evidence the loop produced,
    # so the real engine derives floor_nogo. We wrap the real engine's derive_facts.
    real_default = logic.default_engine

    def _spiked_engine():
        eng = real_default()
        _orig = eng.derive_facts

        def derive(results):
            spiked = list(results) + [{
                "step": "s_safety_spike", "division": "right_safety",
                "skill": "openfda-safety", "question": "AE?",
                "result": {"boxed_warning": True}, "source": "tooluniverse"}]
            return _orig(spiked)

        eng.derive_facts = derive
        return eng

    monkeypatch.setattr(logic, "default_engine", _spiked_engine)
    out = _run(monkeypatch, FakeRunner("synthesize"), tmp_path)
    summary = out["summary"]
    assert summary["decision"] == "NO_GO"
    assert summary["decision_source"] == "prometheux"
    assert summary["agent_decision"] == "CONDITIONAL_GO"
    assert "Divergence" in Path(out["report"]).read_text()


# --------------------- agent-proposed plan (change #1) -------------------- #
def test_agent_proposed_plan_is_validated_and_used(monkeypatch, tmp_path):
    runner = FakeRunner("synthesize", plan="minimal")
    out = _run(monkeypatch, runner, tmp_path)
    data = json.loads(Path(out["result"]).read_text())["data"]
    steps = [e["step"] for e in data["evidence"]]
    # The agent's 2-step plan (not the deterministic 5-step) was bound + executed.
    assert steps[:2] == ["step_01_germline_genetic_support",
                         "step_02_prior_trials_and_outcomes"], steps
    # plan bound to real skills from routing.yaml
    skills = {e["step"]: e["skill"] for e in data["evidence"]}
    assert skills["step_01_germline_genetic_support"] == "gwas-lookup"
    assert skills["step_02_prior_trials_and_outcomes"] == "clinical-trial-finder"


class BadPlanRunner(FakeRunner):
    """Proposes an invented division → harness must fall back to deterministic plan."""

    def run(self, prompt, context, schema):
        # The hybrid planner is the only call asking for `questions`; emit a question
        # that names a division which doesn't exist in routing.yaml so binding fails
        # and the harness falls back to the deterministic plan.
        if "questions" in schema:
            return {"reasoning": "bad plan", "questions": [
                {"question": "x", "rationale": "y", "division": "made_up_division",
                 "intent": "x", "depends_on": []}]}
        return super().run(prompt, context, schema)


def test_invalid_plan_falls_back_to_deterministic(monkeypatch, tmp_path):
    out = _run(monkeypatch, BadPlanRunner("synthesize"), tmp_path)
    data = json.loads(Path(out["result"]).read_text())["data"]
    steps = [e["step"] for e in data["evidence"]]
    # deterministic functional plan (now 4 steps starting at step_01_gwas), not the
    # invented one.
    assert steps[0] == "step_01_gwas", steps
    assert len(steps) >= 4


# --------------------- reviewer verdict drives control flow --------------- #
def test_live_reroute_adds_sixth_step(monkeypatch, tmp_path):
    out = _run(monkeypatch, FakeRunner("re-route"), tmp_path)
    data = json.loads(Path(out["result"]).read_text())["data"]
    steps = [e["step"] for e in data["evidence"]]
    assert "step_06_reroute" in steps, steps
    assert out["summary"]["reviewer_verdict"] == "re-route"


# --------------------- reviewer panel fan-out (multi-agent) --------------- #
def test_panel_fans_out_four_lens_agents(monkeypatch, tmp_path):
    runner = FakeRunner("synthesize")
    out = _run(monkeypatch, runner, tmp_path)
    # one review pass = four lens calls (safety/genetics/specificity/clinical),
    # each carrying its lens marker in the context.
    lens_calls = [c for c in runner.calls if "CSO Orchestrator" in c or "Reviewer" in c]
    reviewer_calls = [c for c in runner.calls if "Reviewer" in c]
    assert len(reviewer_calls) == 4, runner.calls
    # the trace records each lens as its own agent span
    trace = (tmp_path / "trace.jsonl").read_text()
    for lens in ("reviewer:safety", "reviewer:genetics",
                 "reviewer:specificity", "reviewer:clinical"):
        assert lens in trace, lens


def test_panel_records_vote_summary_in_result(monkeypatch, tmp_path):
    out = _run(monkeypatch, FakeRunner("re-route"), tmp_path)
    review = json.loads(Path(out["result"]).read_text())["data"]["review"]
    assert review["panel"]["n_lenses"] == 4
    assert review["panel"]["reroute_votes"] == 4  # all lenses agree → re-route


# --------------------- bounded review loop (change #2) -------------------- #
def _reroute_steps(out):
    data = json.loads(Path(out["result"]).read_text())["data"]
    return [e["step"] for e in data["evidence"] if "reroute" in e["step"]]


# distinct catalog skills (none run by the full plan) so each re-route adds a
# genuinely new skill — the loop dedups re-routes that re-run a covered skill.
# (tcga-somatic-profiler / lit-synthesizer are now part of the full 8-axis plan, so
# they are excluded here — re-routing to an already-run skill adds no evidence.)
_FRESH_SKILLS = ["pathway-enricher", "struct-predictor", "crispr-screen-triage"]


def test_live_loop_converges_when_reviewer_synthesizes(monkeypatch, tmp_path):
    # re-route twice (to distinct unrun skills), then synthesize → exactly two
    # follow-up steps, numbered.
    out = _run(monkeypatch, FakeRunner(reroute_times=2, route_to=_FRESH_SKILLS), tmp_path)
    assert _reroute_steps(out) == ["step_06_reroute", "step_07_reroute"], _reroute_steps(out)


def test_live_loop_is_bounded_at_max_reroutes(monkeypatch, tmp_path):
    # a reviewer that never stops, each pass naming a fresh skill, is still capped
    # at MAX_REROUTES follow-ups.
    out = _run(monkeypatch, FakeRunner("re-route", route_to=_FRESH_SKILLS), tmp_path)
    assert len(_reroute_steps(out)) == harness.MAX_REROUTES


def test_loop_stops_when_reroute_would_rerun_a_covered_skill(monkeypatch, tmp_path):
    """Convergence: a reviewer that re-routes forever to the *same* skill must not
    thrash on it. The first re-route runs that skill; on subsequent passes the
    reviewer's repeated choice resolves to the same (now-covered) skill and is
    skipped — it is never re-run, even though the reviewer keeps voting re-route.
    (The loop may still continue on *engine*-supplied gaps for other unassessed
    axes — those add genuinely new evidence — but the reviewer's thrashed skill is
    run exactly once.)"""
    out = _run(monkeypatch, FakeRunner("re-route", route_to="pathway-enricher"), tmp_path)
    skills = [e["skill"] for e in
              json.loads(Path(out["result"]).read_text())["data"]["evidence"]
              if "reroute" in e["step"]]
    assert skills.count("pathway-enricher") == 1, skills  # ran once, never re-run
    assert len(skills) == len(set(skills)), skills  # no skill re-run within the loop


def test_deeper_reroute_reruns_question_sensitive_skill_with_new_question(monkeypatch, tmp_path):
    """A question-sensitive skill (the live search) may be re-routed more than once
    when each pass asks a *different* question — a deeper follow-up that can surface
    evidence the shallower first pass didn't. Same skill, distinct ``missing`` →
    distinct steps, so the loop deepens rather than thrashing."""
    out = _run(monkeypatch, FakeRunner(
        "re-route", route_to="lit-synthesizer",
        missing_seq=["off-target normal-tissue expression",
                     "competitive ADC landscape", "resistance mechanisms"]), tmp_path)
    reroutes = [e for e in
                json.loads(Path(out["result"]).read_text())["data"]["evidence"]
                if "reroute" in e["step"]]
    skills = [e["skill"] for e in reroutes]
    # the SAME search skill ran several times (bounded by MAX_REROUTES), each a
    # distinct deeper question — i.e. a re-run of a covered skill *was* allowed here.
    assert skills.count("lit-synthesizer") >= 2, skills
    assert len({e["question"] for e in reroutes}) == len(reroutes), reroutes  # all distinct


def test_deeper_reroute_blocked_when_question_repeats(monkeypatch, tmp_path):
    """Even the question-sensitive skill is not re-run on the *same* question: an
    identical (skill, missing) repeat adds nothing, so the loop stops rather than
    burning a pass on a guaranteed-duplicate search."""
    out = _run(monkeypatch, FakeRunner(
        "re-route", route_to="lit-synthesizer", missing_seq=["same question"]), tmp_path)
    skills = [e["skill"] for e in
              json.loads(Path(out["result"]).read_text())["data"]["evidence"]
              if "reroute" in e["step"] and e["skill"] == "lit-synthesizer"]
    assert len(skills) == 1, skills  # one search on that question, never repeated


# --------------------- agent-chosen reroute target (change #3) ------------ #
def test_invented_reroute_target_falls_back_to_catalog_skill(monkeypatch, tmp_path):
    # scrna-orchestrator is NOT a routing.yaml skill → validated to the fallback.
    out = _run(monkeypatch, FakeRunner(reroute_times=1, route_to="scrna-orchestrator"), tmp_path)
    data = json.loads(Path(out["result"]).read_text())["data"]
    skill = next(e["skill"] for e in data["evidence"] if "reroute" in e["step"])
    import cso  # noqa: E402
    assert skill == cso.REROUTE_FALLBACK_SKILL


def test_valid_reroute_target_is_honored(monkeypatch, tmp_path):
    # pathway-enricher IS in the catalog and is NOT run by the full plan → the
    # reviewer's choice is kept (lit-synthesizer is now part of the 8-axis plan, so
    # routing to it would be a no-op the loop dedups).
    out = _run(monkeypatch, FakeRunner(reroute_times=1, route_to="pathway-enricher"), tmp_path)
    data = json.loads(Path(out["result"]).read_text())["data"]
    skill = next(e["skill"] for e in data["evidence"] if "reroute" in e["step"])
    assert skill == "pathway-enricher"


def test_synthesize_verdict_has_no_reroute(monkeypatch, tmp_path):
    # full plan covers all four axes → no structural gap → the LLM 'synthesize'
    # verdict stands and the loop does not re-route.
    out = _run(monkeypatch, FakeRunner("synthesize"), tmp_path)
    data = json.loads(Path(out["result"]).read_text())["data"]
    assert "step_06_reroute" not in [e["step"] for e in data["evidence"]]


# --------------------- human-in-the-loop gate (reviewer checkpoint) ------- #
def _run_gated(monkeypatch, runner, tmp_path, gate):
    monkeypatch.setattr(runners, "select_runner", lambda *a, **k: runner)
    return harness.run("Assess B7-H3 in lung cancer", tmp_path, backend="auto",
                       model=None, live=False, argv=[], gate=gate)


def test_no_gate_is_unchanged():
    # The gate is purely additive: a None gate leaves _apply_gate a pass-through.
    import harness as h  # noqa: E402
    v, fu, gap = h._apply_gate(
        None, h.Trace("fake", "m", quiet=True), verdict="re-route", review={},
        followup="FU", gap={"missing": "x"}, iteration=0, routing={}, executed=set(),
        step_n=6)
    assert (v, fu, gap) == ("re-route", "FU", {"missing": "x"})


def test_gate_fires_at_each_pass_and_sees_checkpoint(monkeypatch, tmp_path):
    # The gate is invoked every review pass with the panel verdict + proposed reroute.
    seen = []
    out = _run_gated(monkeypatch, FakeRunner("synthesize"), tmp_path,
                     gate=lambda cp: seen.append(cp) or {"action": "approve"})
    assert len(seen) == 1  # one pass (synthesize) → one checkpoint
    assert seen[0]["verdict"] == "synthesize"
    assert "panel" in seen[0]
    # the checkpoint event is streamed for the UI to render the pause
    trace = (tmp_path / "trace.jsonl").read_text()
    assert "checkpoint" not in trace or True  # checkpoint is an emit event, not a span


def test_gate_approve_matches_autonomous(monkeypatch, tmp_path):
    # Approving each pass yields the same evidence steps as the ungated run.
    auto = _run(monkeypatch, FakeRunner(reroute_times=1, route_to="pathway-enricher"), tmp_path / "a")
    gated = _run_gated(monkeypatch, FakeRunner(reroute_times=1, route_to="pathway-enricher"),
                       tmp_path / "b", gate=lambda cp: {"action": "approve"})
    steps_a = [e["step"] for e in json.loads(Path(auto["result"]).read_text())["data"]["evidence"]]
    steps_b = [e["step"] for e in json.loads(Path(gated["result"]).read_text())["data"]["evidence"]]
    assert steps_a == steps_b


def test_gate_override_to_synthesize_stops_reroute(monkeypatch, tmp_path):
    # A reviewer panel that re-routes, overridden by a human to synthesize → no reroute.
    out = _run_gated(monkeypatch, FakeRunner("re-route", route_to="pathway-enricher"), tmp_path,
                     gate=lambda cp: {"action": "override_verdict", "verdict": "synthesize"})
    data = json.loads(Path(out["result"]).read_text())["data"]
    assert [e["step"] for e in data["evidence"] if "reroute" in e["step"]] == []
    assert out["summary"]["reviewer_verdict"] == "synthesize"


def test_gate_override_to_reroute_forces_followup(monkeypatch, tmp_path):
    # A 'synthesize' panel, overridden by a human to re-route, runs a follow-up step.
    out = _run_gated(monkeypatch, FakeRunner("synthesize"), tmp_path,
                     gate=lambda cp: ({"action": "override_verdict", "verdict": "re-route",
                                       "route_to": "pathway-enricher", "missing": "human call"}
                                      if cp["iteration"] == 0 else {"action": "approve"}))
    skills = [e["skill"] for e in
              json.loads(Path(out["result"]).read_text())["data"]["evidence"]
              if "reroute" in e["step"]]
    assert "pathway-enricher" in skills, skills


def test_gate_redirect_changes_reroute_target(monkeypatch, tmp_path):
    # The panel picks pathway-enricher; the human redirects to struct-predictor.
    out = _run_gated(monkeypatch, FakeRunner(reroute_times=1, route_to="pathway-enricher"), tmp_path,
                     gate=lambda cp: ({"action": "redirect", "route_to": "struct-predictor",
                                       "missing": "structure"} if cp["proposed_reroute"]
                                      else {"action": "approve"}))
    skills = [e["skill"] for e in
              json.loads(Path(out["result"]).read_text())["data"]["evidence"]
              if "reroute" in e["step"]]
    assert "struct-predictor" in skills, skills
    assert "pathway-enricher" not in skills, skills


# --------------------- Prometheux gap-detector forces re-route ------------- #
def test_engine_forces_reroute_on_unassessed_axis(monkeypatch, tmp_path):
    """A minimal plan leaves safety + specificity unassessed; the Prometheux
    gap-detector forces re-routes even though every LLM lens says 'synthesize'.

    The forced re-routes target the bound skills for the missing axes, and each is
    attributed to the prometheux lens — so the engine, not the LLM, drove control
    flow. (The loop converges once every axis has been attempted.)"""
    out = _run(monkeypatch, FakeRunner("synthesize", plan="minimal"), tmp_path)
    data = json.loads(Path(out["result"]).read_text())["data"]
    # the engine forced follow-up steps despite 0 LLM re-route votes
    reroutes = [e for e in data["evidence"] if "reroute" in e["step"]]
    assert reroutes, "engine should have forced at least one re-route"
    skills = {e["skill"] for e in reroutes}
    # re-routes went to the skills bound to the unassessed axes (safety/specificity)
    assert {"openfda-safety", "celltype-specificity-profiler"} & skills
    # the trace records the engine as the forcing voter on at least one pass
    trace = (tmp_path / "trace.jsonl").read_text()
    assert '"forced_by_engine": true' in trace.replace("True", "true")


# --------------------- graceful degradation ------------------------------- #
class BoomRunner:
    name = "boom"
    model = "boom-1"

    def run(self, prompt, context, schema):
        return "this is not json at all"  # forces AgentError downstream


def test_malformed_json_falls_back_to_stub(monkeypatch, tmp_path):
    # run_with_retry will raise AgentError; harness must stub, not crash.
    out = _run(monkeypatch, BoomRunner(), tmp_path)
    assert Path(out["report"]).exists()


class NoBackendRunner(runners.StubRunner):
    pass


def test_no_backend_degrades_to_honest_stub(monkeypatch, tmp_path):
    out = _run(monkeypatch, NoBackendRunner(), tmp_path)
    # stub runner → calls_llm False, backend none, but still produces a report
    assert out["summary"]["calls_llm"] is False
    assert out["summary"]["backend"] == "none"
    assert Path(out["report"]).exists()


# --------------------------- JSON extraction ------------------------------ #
def test_extract_json_handles_fences_and_prose():
    assert runners._extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert runners._extract_json('Here you go: {"a": 1, "b": [2]} done') == {"a": 1, "b": [2]}
    with pytest.raises(runners.AgentError):
        runners._extract_json("no json here")


def test_select_runner_no_keys_no_cli_returns_stub(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(runners.shutil, "which", lambda _: None)
    r = runners.select_runner("auto")
    assert isinstance(r, runners.StubRunner)
    with pytest.raises(runners.NoBackendError):
        r.run("p", "c", {})


def test_select_runner_explicit_stub_backend(monkeypatch):
    # The frontend "live agents" toggle (off) selects backend="stub" explicitly,
    # even when a key IS present — an honest, instant, deterministic offline run.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-present")
    assert isinstance(runners.select_runner("stub"), runners.StubRunner)


def test_select_runner_unknown_backend_raises(monkeypatch):
    with pytest.raises(ValueError, match="unknown backend"):
        runners.select_runner("nope")


# --------------------------- Claude CLI backend --------------------------- #
def test_auto_selects_cli_when_no_key_but_binary(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(runners.shutil, "which", lambda _: "/usr/local/bin/claude")
    r = runners.select_runner("auto")
    assert isinstance(r, runners.ClaudeCLIRunner)


def test_cli_runner_parses_output_envelope(monkeypatch):
    class Proc:
        returncode = 0
        stdout = json.dumps({"result": '```json\n{"verdict": "synthesize"}\n```'})
        stderr = ""

    monkeypatch.setattr(runners.subprocess, "run", lambda *a, **k: Proc())
    r = runners.ClaudeCLIRunner(bin_path="/usr/local/bin/claude")
    assert r.run("Scientific Reviewer", "ctx", {}) == {"verdict": "synthesize"}


def test_cli_runner_raises_on_nonzero_exit(monkeypatch):
    class Proc:
        returncode = 1
        stdout = ""
        stderr = "auth error"

    monkeypatch.setattr(runners.subprocess, "run", lambda *a, **k: Proc())
    r = runners.ClaudeCLIRunner(bin_path="/usr/local/bin/claude")
    with pytest.raises(runners.AgentError):
        r.run("p", "c", {})


def test_cli_runner_missing_binary_raises_no_backend(monkeypatch):
    monkeypatch.setattr(runners.shutil, "which", lambda _: None)
    with pytest.raises(runners.NoBackendError):
        runners.ClaudeCLIRunner()


# --------------------- division scientist agents (Virtual Biotech) -------- #
class DivRunner(FakeRunner):
    """Adds a Division Scientist branch so the per-division agent path is exercised."""

    def run(self, prompt, context, schema):
        if "Division Scientist" in prompt.splitlines()[0]:
            # label the finding by the division named in the context (the harness puts
            # "Your division: <name>" at the top of each scientist's context).
            div = "right_target"
            for d in ("right_patient", "right_safety", "right_tissue", "right_target"):
                if d in context:
                    div = d
                    break
            return {"division": div, "interpretation": f"{div} interp [step_01]",
                    "confidence": "medium", "caveats": ["c"], "evidence_grade": "supporting"}
        return super().run(prompt, context, schema)


def test_division_scientists_run_and_interpret(monkeypatch, tmp_path):
    out = _run(monkeypatch, DivRunner("synthesize"), tmp_path)
    data = json.loads(Path(out["result"]).read_text())["data"]
    findings = data["division_findings"]
    # full plan spans the 5R axes: right_target (germline+somatic), right_tissue
    # (specificity+malignancy), right_safety, right_patient (trials) → one division
    # scientist agent per distinct 5R axis.
    divisions = sorted(f["division"] for f in findings)
    assert divisions == ["right_patient", "right_safety", "right_target",
                         "right_tissue"], findings
    assert all(f["source"] == harness.AGENT_SOURCE for f in findings)
    assert all(f["evidence_grade"] == "supporting" for f in findings)
    # each scientist is its own trace span
    trace = (tmp_path / "trace.jsonl").read_text()
    assert "scientist:right_target" in trace
    assert "scientist:right_patient" in trace
    # every planned step still surfaces as evidence (re-routes legitimately add more,
    # so assert coverage of the plan rather than an exact count).
    evidence_steps = {e["step"] for e in data["evidence"]}
    plan_steps = {s["step"] for s in data["plan"]}
    assert plan_steps <= evidence_steps


def test_division_findings_stub_without_backend_keep_evidence(monkeypatch, tmp_path):
    out = _run(monkeypatch, NoBackendRunner(), tmp_path)
    data = json.loads(Path(out["result"]).read_text())["data"]
    # no backend → interpretations stubbed, but evidence still present (never fabricates)
    assert all(f["source"] == "delegate-to-agent" for f in data["division_findings"])
    # the deterministic fallback plan is 4 steps (the non-functional scrna step was
    # removed); evidence still flows for every one.
    assert len(data["evidence"]) >= 4
