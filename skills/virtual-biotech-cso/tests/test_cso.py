"""Tests for the virtual-biotech-cso skill (offline; no network/LLM)."""
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR))

import pytest  # noqa: E402

from cso import (  # noqa: E402
    FUNCTIONAL_SKILLS,
    PlanValidationError,
    case_key,
    decompose_and_route,
    load_routing,
    validate_and_bind_plan,
    _reroute_task,
    _result_digest,
)

SCRIPT = SKILL_DIR / "cso.py"


# --------------------------- pure helpers --------------------------------- #
def test_case_key_b7h3_aliases():
    for q in ("Assess B7-H3 in lung cancer", "what about CD276?", "b7h3 target"):
        assert case_key(q) == "b7h3"


def test_case_key_generic_slug():
    assert case_key("Evaluate KRAS G12C in colorectal cancer").startswith("evaluate_kras")


def test_decompose_routes_from_yaml():
    routing = load_routing()
    tasks = decompose_and_route("Assess B7-H3 in lung cancer", "b7h3", routing)
    # The cell-type-expression step (scrna-embedding) is deferred (no live h5ad atlas),
    # so the deterministic plan goes straight to the functional specificity profiler.
    assert [t.step for t in tasks] == [
        "step_01_gwas",
        "step_03_celltype_specificity",
        "step_04_offtarget_safety",
        "step_05_clinical_trials",
    ]
    # every routed skill in the deterministic plan is functional (executes live)
    assert all(t.skill in FUNCTIONAL_SKILLS for t in tasks), [t.skill for t in tasks]
    # routing.yaml binds the specificity sub-question to our PR #1 skill
    spec = next(t for t in tasks if t.step == "step_03_celltype_specificity")
    assert spec.skill == "celltype-specificity-profiler"


def test_reroute_task_uses_gap_route():
    gap = {"missing": "spatial validation", "route_to": "scrna-orchestrator", "why": "x"}
    t = _reroute_task(gap)
    assert t.skill == "scrna-orchestrator"
    assert t.step == "step_06_reroute"


def test_result_digest_specificity_shape():
    env = {"result": {"tau": 0.78, "interpretation": "cell-type-specific (tau > 0.7)"}}
    assert "tau=0.78" in _result_digest(env)


# --------------------------- end-to-end demo ------------------------------ #
def _run(args, env_extra=None):
    env = os.environ.copy()
    # ensure no LLM/clawbio path is taken even if a key is present in CI
    env.pop("ANTHROPIC_API_KEY", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        capture_output=True, text=True, env=env,
    )


def test_demo_writes_full_contract(tmp_path):
    out = tmp_path / "demo"
    res = _run(["--demo", "--output", str(out)])
    assert res.returncode == 0, res.stderr
    summary = json.loads(res.stdout)["summary"]
    assert summary["case"] == "b7h3"
    assert summary["mode"] == "demo"
    assert summary["reviewer_verdict"] == "re-route"
    assert summary["n_steps"] == 5  # 4 functional steps + one re-route

    assert (out / "report.md").exists()
    assert (out / "result.json").exists()
    repro = out / "reproducibility"
    for f in ("commands.sh", "environment.yml", "checksums.sha256"):
        assert (repro / f).exists()

    report = (out / "report.md").read_text()
    assert "cached illustrative fixtures" in report  # honesty label present
    assert "celltype-specificity-profiler" in report  # chains to PR #1 skill
    # target-ID dossier structure
    for header in ("## Executive summary", "## Evidence by division", "## Evidence gaps",
                   "## Proposed experiments", "## References & data sources"):
        assert header in report, f"missing section: {header}"
    assert "**Decision:**" in report                       # decision present
    assert "[1]" in report                                 # per-row reference markers
    assert "https://clinicaltrials.gov/" in report          # a harvested source URL

    envelope = json.loads((out / "result.json").read_text())
    assert envelope["skill"] == "virtual-biotech-cso"
    assert envelope["data"]["review"]["verdict"] == "re-route"
    assert len(envelope["data"]["evidence"]) == 5  # 4 functional steps + one re-route
    # new schema fields
    for key in ("references", "evidence_gaps", "proposed_experiments"):
        assert key in envelope["data"], f"missing data key: {key}"
    assert len(envelope["data"]["references"]) == 5
    assert envelope["summary"]["decision"] == "CONDITIONAL_GO"
    assert envelope["data"]["proposed_experiments"]  # non-empty (synthesis + reviewer)


def test_demo_report_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    _run(["--demo", "--output", str(a)])
    _run(["--demo", "--output", str(b)])
    assert (a / "report.md").read_text() == (b / "report.md").read_text()


def test_default_mode_is_honest_without_backends(tmp_path):
    # no --demo, no --live, no API key -> honest 'unavailable'/'not generated', never fabricated
    out = tmp_path / "default"
    res = _run(["--output", str(out)])
    assert res.returncode == 0, res.stderr
    summary = json.loads(res.stdout)["summary"]
    assert summary["n_executed"] == 0
    report = (out / "report.md").read_text()
    assert "not executed" in report
    assert "no data-derived recommendation" in report


# --------------------- validate_and_bind_plan (change #1) ----------------- #
ROUTING = load_routing()


def test_validate_binds_proposed_plan_to_real_skills():
    plan = [
        {"division": "target_id_and_prioritization",
         "intent": "germline_genetic_support", "question": "germline?"},
        {"division": "target_id_and_prioritization",
         "intent": "cell_type_specificity", "question": "specific?",
         "depends_on": ["step_01_germline_genetic_support"]},
    ]
    subtasks = validate_and_bind_plan(plan, ROUTING)
    assert [s.step for s in subtasks] == [
        "step_01_germline_genetic_support", "step_02_cell_type_specificity"]
    assert subtasks[0].skill == "gwas-lookup"
    assert subtasks[1].skill == "celltype-specificity-profiler"
    assert subtasks[1].depends_on == ["step_01_germline_genetic_support"]


def test_validate_rejects_unknown_division():
    with pytest.raises(PlanValidationError, match="unknown division"):
        validate_and_bind_plan([{"division": "nope", "intent": "x"}], ROUTING)


def test_validate_rejects_unroutable_intent():
    with pytest.raises(PlanValidationError, match="not routable"):
        validate_and_bind_plan(
            [{"division": "clinical_officers", "intent": "made_up"}], ROUTING)


def test_validate_rejects_forward_dependency():
    with pytest.raises(PlanValidationError, match="earlier step"):
        validate_and_bind_plan([
            {"division": "clinical_officers", "intent": "prior_trials_and_outcomes",
             "depends_on": ["step_99_future"]},
        ], ROUTING)


def test_validate_rejects_empty_plan():
    with pytest.raises(PlanValidationError, match="empty"):
        validate_and_bind_plan([], ROUTING)


# --------------------- catalog_skills + validated reroute (changes #2/#3) -- #
from cso import catalog_skills, REROUTE_FALLBACK_SKILL  # noqa: E402


def test_catalog_skills_includes_primary_and_also():
    skills = catalog_skills(ROUTING)
    assert "gwas-lookup" in skills                 # primary skill
    assert "lit-synthesizer" in skills             # reroute target
    assert "gwas-catalog-region-fetch" in skills   # from an `also:` list
    assert "scrna-orchestrator" not in skills       # only a reference, not routable


def test_reroute_validates_invented_target():
    gap = {"missing": "x", "route_to": "made-up-skill", "why": "y"}
    t = _reroute_task(gap, ROUTING)
    assert t.skill == REROUTE_FALLBACK_SKILL


def test_reroute_keeps_valid_target_and_numbers_step():
    gap = {"missing": "recency", "route_to": "lit-synthesizer", "why": "stale"}
    t = _reroute_task(gap, ROUTING, step_n=7)
    assert t.skill == "lit-synthesizer"
    assert t.step == "step_07_reroute"


def test_reroute_without_routing_is_backward_compatible():
    # no routing passed → no validation → caller's choice honored (legacy demo path)
    gap = {"missing": "spatial", "route_to": "scrna-orchestrator", "why": "z"}
    assert _reroute_task(gap).skill == "scrna-orchestrator"


# --------------------- reviewer panel aggregation (multi-agent) ----------- #
from cso import aggregate_panel_review, REVIEWER_LENSES  # noqa: E402


def _rev(verdict, missing=None, route_to="lit-synthesizer", scores=None):
    return {"verdict": verdict, "scores": scores or {"relevance": 5, "evidence": 4, "thoroughness": 3},
            "gaps": [{"missing": missing, "route_to": route_to, "why": "w"}] if missing else [],
            "experiments": []}


def test_panel_reroutes_when_min_votes_met():
    lens = [("safety", _rev("re-route", "off-target")),
            ("genetics", _rev("re-route", "weak GWAS")),
            ("specificity", _rev("synthesize")),
            ("clinical", _rev("synthesize"))]
    agg = aggregate_panel_review(lens, ROUTING)  # 2 votes, min_votes=2
    assert agg["verdict"] == "re-route"
    assert agg["panel"]["reroute_votes"] == 2


def test_panel_synthesizes_on_lone_dissent():
    lens = [("safety", _rev("re-route", "off-target")),
            ("genetics", _rev("synthesize")),
            ("specificity", _rev("synthesize")),
            ("clinical", _rev("synthesize"))]
    agg = aggregate_panel_review(lens, ROUTING)  # 1 vote < 2
    assert agg["verdict"] == "synthesize"


def test_panel_dedupes_gaps_and_tags_lenses():
    # two lenses raise the SAME gap → one deduped entry crediting both lenses
    lens = [("safety", _rev("re-route", "spatial", "lit-synthesizer")),
            ("specificity", _rev("re-route", "spatial", "lit-synthesizer"))]
    agg = aggregate_panel_review(lens, ROUTING)
    spatial = [g for g in agg["gaps"] if g["missing"] == "spatial"]
    assert len(spatial) == 1
    assert sorted(spatial[0]["lenses"]) == ["safety", "specificity"]


def test_panel_scores_are_skeptical_min():
    lens = [("safety", _rev("synthesize", scores={"relevance": 5, "evidence": 2, "thoroughness": 4})),
            ("genetics", _rev("synthesize", scores={"relevance": 3, "evidence": 5, "thoroughness": 4}))]
    agg = aggregate_panel_review(lens, ROUTING)
    assert agg["scores"] == {"relevance": 3, "evidence": 2, "thoroughness": 4}


def test_panel_most_corroborated_gap_first():
    lens = [("safety", _rev("re-route", "spatial", "lit-synthesizer")),
            ("genetics", _rev("re-route", "spatial", "lit-synthesizer")),
            ("clinical", _rev("re-route", "trials", "clinical-trial-finder"))]
    agg = aggregate_panel_review(lens, ROUTING)
    # the 2-lens gap sorts ahead of the 1-lens gap → _review_loop reroutes on it first
    assert agg["gaps"][0]["missing"] == "spatial"


def test_four_lenses_defined():
    keys = [lens["key"] for lens in REVIEWER_LENSES]
    assert keys == ["safety", "genetics", "specificity", "clinical"]


# --------------------- live Tavily routing (sponsor tool + autonomy) ------ #
from cso import _local_skill_args  # noqa: E402


def test_lit_synthesizer_goes_live_with_key(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    args = _local_skill_args("lit-synthesizer", live=True, target="B7-H3 in lung cancer")
    assert args == ["--target", "B7-H3 in lung cancer"]  # real-time Tavily search


def test_lit_synthesizer_falls_back_to_demo_without_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    args = _local_skill_args("lit-synthesizer", live=True, target="B7-H3 in lung cancer")
    assert args == ["--demo"]  # honest offline fallback, never fails


def test_demo_mode_never_goes_live(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    assert _local_skill_args("lit-synthesizer", live=False, target="x") == ["--demo"]


def test_non_tavily_skill_stays_demo(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    assert _local_skill_args("openfda-safety", live=True, target="x") == ["--demo"]


# --------------------- division grouping (Virtual Biotech structure) ------ #
from cso import group_by_division, Subtask  # noqa: E402


def test_group_by_division_preserves_order_and_groups():
    tasks = [
        Subtask("step_01_a", "target_id_and_prioritization", "q", "gwas-lookup"),
        Subtask("step_02_b", "clinical_officers", "q", "clinical-trial-finder"),
        Subtask("step_03_c", "target_id_and_prioritization", "q", "celltype-specificity-profiler"),
    ]
    groups = group_by_division(tasks)
    assert [d for d, _ in groups] == ["target_id_and_prioritization", "clinical_officers"]
    # the two target_id steps are grouped under one scientist agent
    assert [t.step for t in groups[0][1]] == ["step_01_a", "step_03_c"]
    assert [t.step for t in groups[1][1]] == ["step_02_b"]


# --------------------- literature patch for unavailable axes --------------- #
from cso import _patch_with_literature, _LITERATURE_PROXY_INTENT, execute_skill  # noqa: E402


def test_patch_requires_tavily_key(monkeypatch):
    # No key → no patch; the axis stays honestly "unavailable" rather than being
    # filled by lit-synthesizer's offline --demo fixture (which would be illustrative).
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert _patch_with_literature("gwas-lookup", target="B7-H3 in lung cancer") is None


def test_patch_requires_target(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    assert _patch_with_literature("gwas-lookup", target=None) is None


def test_patch_steers_search_at_axis_intent_and_tags_proxy(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    seen = {}

    def fake_local(skill, live=False, target=None, focus=None):
        seen["skill"], seen["focus"] = skill, focus
        return {"status": "ok", "via": "lit", "summary": "s", "references": []}

    monkeypatch.setattr("cso._run_local_skill", fake_local)
    env = _patch_with_literature("crispr-screen-triage", target="B7-H3 in lung cancer")
    assert seen["skill"] == "lit-synthesizer"  # routed through the live Tavily search
    assert "essentiality" in seen["focus"].lower() or "depmap" in seen["focus"].lower()
    assert env["literature_proxy_for"] == "crispr-screen-triage"  # labelled, not the real dataset
    assert "literature patch" in env["via"]


def test_patch_reviewer_focus_narrows_intent(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    seen = {}
    monkeypatch.setattr("cso._run_local_skill",
                        lambda skill, live=False, target=None, focus=None:
                        (seen.update(focus=focus) or {"status": "ok"}))
    _patch_with_literature("gwas-lookup", target="B7-H3", focus="African ancestry cohorts")
    assert "African ancestry cohorts" in seen["focus"]  # deeper re-route steers the patch


def test_unavailable_external_skill_stays_honest_without_key(monkeypatch):
    # End-to-end: a live external skill with no Tavily key reports unavailable, not a
    # fabricated or demo-backed result.
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    t = Subtask("step_01_gwas", "target_id_and_prioritization",
                "germline support?", "gwas-lookup")
    env = execute_skill(t, case="b7h3", demo=False, live=True, target="B7-H3 in lung cancer")
    assert env["source"] == "unavailable"
    assert env["result"]["status"] != "ok"
