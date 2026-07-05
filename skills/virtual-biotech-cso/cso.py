#!/usr/bin/env python
"""virtual-biotech-cso — a ToolUniverse orchestration skill.

Reproduces the multi-agent therapeutic-target-assessment loop from
*The Virtual Biotech* (Zhang et al. 2026): a Chief-of-Staff briefing, task
decomposition + routing across four scientific divisions, a one-pass
Scientific-Reviewer audit (which may re-route to fill a gap), and a synthesized
report. It is an ORCHESTRATOR: it routes sub-questions to predefined ToolUniverse
tools (via ``tool_router.yaml``) and never does the underlying biology itself.

This skill makes NO LLM call of its own. The reasoning roles (Chief of Staff,
Scientific Reviewer, CSO synthesis) are delegated to the driving agent: a
subagent-capable harness (e.g. Claude Code) runs the prompts in ``prompts/`` —
ideally one subagent per role/division — using its own session model. No API
key is required.

Two execution modes, both honest:
  - ``--live``  : executes each routed skill through its predefined ToolUniverse
                  tool (``tool_backend.run_predefined_tool``). Reasoning is still
                  delegated to the agent; steps with no ToolUniverse mapping are
                  reported "not executed", never fabricated.
  - default     : routed steps are left as honest "not executed" stubs and the
                  reasoning roles as delegation stubs for the agent to drive.

Output contract: ``report.md`` + ``result.json`` + ``reproducibility/`` in the
chosen ``--output`` directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SKILL_NAME = "virtual-biotech-cso"
VERSION = "0.1.0"

SKILL_DIR = Path(__file__).resolve().parent
REPO_ROOT = SKILL_DIR.parent.parent
PROMPTS_DIR = SKILL_DIR / "prompts"
ROUTING_PATH = SKILL_DIR / "routing.yaml"

ORCHESTRATOR_PROMPT = PROMPTS_DIR / "orchestrator.md"
CHIEF_OF_STAFF_PROMPT = PROMPTS_DIR / "chief_of_staff.md"
REVIEWER_PROMPT = PROMPTS_DIR / "reviewer.md"
DIVISION_SCIENTIST_PROMPT = PROMPTS_DIR / "division_scientist.md"

DEFAULT_QUERY = "Assess B7-H3 potential as a therapeutic target in lung cancer"
DELEGATE = "delegate-to-agent"
DISCLAIMER = (
    "ClawBio is a research and educational tool. It is not a medical device and "
    "does not provide clinical diagnoses. Consult a healthcare professional before "
    "making any medical decisions."
)

# Canonical data source per routed skill — harvested into the report's References
# section so every evidence row is traceable to its origin.
SOURCE_REGISTRY: dict[str, dict[str, str]] = {
    "gwas-lookup": {"name": "GWAS Catalog / Open Targets / PheWeb (federated)",
                    "url": "https://www.ebi.ac.uk/gwas/"},
    "fine-mapping": {"name": "GWAS summary statistics (SuSiE fine-mapping)", "url": ""},
    "cellxgene-fetch": {"name": "CZ CELLxGENE Census",
                        "url": "https://cellxgene.cziscience.com/"},
    "scrna-embedding": {"name": "single-cell atlas (scVI/scANVI embedding)", "url": ""},
    "scrna-orchestrator": {"name": "single-cell atlas (Scanpy pipeline)", "url": ""},
    "celltype-specificity-profiler": {"name": "derived: tau + bimodality on the fetched atlas",
                                      "url": ""},
    "crispr-screen-triage": {"name": "CRISPR screen counts / DepMap", "url": ""},
    "pathway-enricher": {"name": "Enrichr (KEGG/GO/Reactome/WikiPathways)",
                         "url": "https://maayanlab.cloud/Enrichr/"},
    "turingdb-graph": {"name": "TuringDB (STRING/Reactome graph)", "url": ""},
    "opentargets-target-factors": {"name": "Open Targets Platform GraphQL (prioritisation/tractability/safety)",
                                   "url": "https://platform.opentargets.org/"},
    "struct-predictor": {"name": "Boltz-2 structure prediction", "url": ""},
    "omics-target-evidence-mapper": {"name": "Open Targets / UniProt / PubMed",
                                     "url": "https://platform.opentargets.org/"},
    "clinpgx": {"name": "ClinPGx (PharmGKB/CPIC)", "url": "https://www.clinpgx.org/"},
    "openfda-safety": {"name": "openFDA FAERS / drug label",
                       "url": "https://open.fda.gov/"},
    "lit-synthesizer": {"name": "Tavily Search API (recent literature / competitive / safety)",
                        "url": "https://tavily.com/"},
    "clinical-trial-finder": {"name": "ClinicalTrials.gov API v2 (+ EUCTR)",
                              "url": "https://clinicaltrials.gov/"},
    "equity-scorer": {"name": "population genetic references (HEIM)", "url": ""},
    "claw-ancestry-pca": {"name": "Simons Genome Diversity Project", "url": ""},
}

# Provenance marker + evidence grade derived from how a step was sourced.
PROVENANCE = {
    "tooluniverse": ("🔧 live", "real ToolUniverse tool output"),
    "tool-descriptor": ("📋 descriptor", "tool call for the agent/frontend to run"),
    "web": ("🌐 web", "agent literature search"),
    "unavailable": ("⚪ not-run", "absent — backend unavailable"),
    "error": ("⚪ error", "absent — skill error"),
    DELEGATE: ("⚪ delegated", "absent — pending agent"),
}

# Source labels that count as a real, executed evidence row.
EXECUTED_SOURCES = ("tooluniverse", "tool-descriptor")


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #
@dataclass
class Subtask:
    """A routed unit of work in the CSO plan."""

    step: str
    division: str
    question: str
    skill: str
    depends_on: list[str] = field(default_factory=list)

    def as_plan_entry(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "division": self.division,
            "question": self.question,
            "skill": self.skill,
            "depends_on": self.depends_on,
        }


# --------------------------------------------------------------------------- #
# Pure helpers (no I/O) — importable for tests
# --------------------------------------------------------------------------- #
def case_key(query: str) -> str:
    """Map a free-text query to a case key (``b7h3`` for B7-H3, else a slug)."""
    q = query.lower()
    if "b7-h3" in q or "b7h3" in q or "cd276" in q:
        return "b7h3"
    slug = re.sub(r"[^a-z0-9]+", "_", q).strip("_")
    slug = "_".join(slug.split("_")[:6]) or "query"
    return slug


def load_routing(path: Path = ROUTING_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _skill_for(routing: dict[str, Any], division: str, intent: str) -> str:
    entry = routing.get(division, {}).get(intent)
    if isinstance(entry, dict):
        return entry.get("skill", "unrouted-skill")
    return "unrouted-skill"


# Planner allow-list: the axes the CSO is willing to route to. Only intents whose
# primary skill is in this set are exposed to the planner agent and used by the
# deterministic plan, so planning stays stable regardless of which ones have a live
# ToolUniverse mapping today (a skill with no tool_router.yaml entry simply returns an
# honest "not executed" envelope at run time — see _run_skill_live). This is a curated
# menu, independent of the live backend.
FUNCTIONAL_SKILLS: set[str] = {
    "celltype-specificity-profiler", "clinical-trial-finder", "clinpgx",
    "crispr-screen-triage", "equity-scorer", "gwas-lookup", "lit-synthesizer",
    "malignant-expression-profiler", "openfda-safety", "opentargets-target-factors",
    "tcga-somatic-profiler",
}


def decompose_and_route(query: str, case: str, routing: dict[str, Any]) -> list[Subtask]:
    """Decompose the query into subtasks and route each via routing.yaml.

    Mirrors workflows/b7h3_adc_nomination.md for the B7-H3 case and uses the same
    division structure (with generic wording) for any other target. Skill names
    are resolved from routing.yaml so the plan stays in sync with the map.
    """
    target = "B7-H3 (CD276)" if case == "b7h3" else "the target"
    # The cell-type-expression step (scrna-embedding) is deferred — it needs an h5ad
    # atlas input we don't fetch live — so the deterministic plan goes straight to the
    # cell-type-specificity profiler (functional; reads the same cell-type signal).
    spec = [
        ("step_01_gwas", "target_id_and_prioritization", "germline_genetic_support",
         f"Is there germline genetic support for {target}?", []),
        ("step_03_celltype_specificity", "target_id_and_prioritization", "cell_type_specificity",
         f"How cell-type-specific is {target} expression (tau + bimodality)?", []),
        ("step_04_offtarget_safety", "target_safety", "off_target_expression",
         f"What is the off-target / broad-tissue expression risk for {target}?",
         ["step_03_celltype_specificity"]),
        ("step_05_clinical_trials", "clinical_officers", "prior_trials_and_outcomes",
         f"What prior trials and outcomes exist for {target}?", []),
    ]
    return [
        Subtask(step=step, division=division, question=question,
                skill=_skill_for(routing, division, intent), depends_on=deps)
        for (step, division, intent, question, deps) in spec
    ]


class PlanValidationError(ValueError):
    """An agent-proposed plan referenced a division/intent/dep that doesn't exist."""


def _routable_intents(routing: dict[str, Any]) -> dict[str, set[str]]:
    """Map each division → the set of intents it can route (from routing.yaml).

    Only intents whose primary skill is in FUNCTIONAL_SKILLS are exposed — so the
    planner agent's menu, and any plan validated against it, can only route to skills
    that actually execute live. Deferred skills are simply absent from the menu.
    """
    out: dict[str, set[str]] = {}
    for division, intents in routing.items():
        if not isinstance(intents, dict):
            continue
        usable = {intent for intent, entry in intents.items()
                  if isinstance(entry, dict) and entry.get("skill") in FUNCTIONAL_SKILLS}
        if usable:
            out[division] = usable
    return out


def validate_and_bind_plan(
    proposed: list[dict[str, Any]], routing: dict[str, Any]
) -> list[Subtask]:
    """Validate an *agent-proposed* plan and bind each step to a real skill.

    This is the inverse of ``decompose_and_route``: rather than generating the plan
    deterministically, the driving agent (Chief of Staff / CSO role) proposes it and
    this function keeps it honest — it is a **validator, not a generator**. It

      * rejects divisions / intents that don't exist in ``routing.yaml`` (no invented
        skills — the same no-fabrication contract the deterministic path enforces),
      * resolves each ``(division, intent)`` to its real skill via ``_skill_for``,
      * assigns stable ``step_NN_<intent>`` ids,
      * validates that every ``depends_on`` names an earlier step in the plan.

    A proposed step is a dict: ``{division, intent, question, depends_on?}``. Raises
    :class:`PlanValidationError` on any unroutable reference so the harness can fall
    back to the deterministic plan rather than execute something fabricated.
    """
    if not isinstance(proposed, list) or not proposed:
        raise PlanValidationError("proposed plan is empty or not a list")

    routable = _routable_intents(routing)
    subtasks: list[Subtask] = []
    seen_steps: set[str] = set()
    for i, entry in enumerate(proposed, 1):
        if not isinstance(entry, dict):
            raise PlanValidationError(f"plan step {i} is not an object")
        division = entry.get("division")
        intent = entry.get("intent")
        if division not in routable:
            raise PlanValidationError(
                f"plan step {i}: unknown division {division!r} "
                f"(valid: {sorted(routable)})")
        if intent not in routable[division]:
            raise PlanValidationError(
                f"plan step {i}: intent {intent!r} not routable under {division!r} "
                f"(valid: {sorted(routable[division])})")

        skill = _skill_for(routing, division, intent)
        if skill == "unrouted-skill":
            raise PlanValidationError(
                f"plan step {i}: {division}/{intent} resolved to no skill")

        step = f"step_{i:02d}_{intent}"
        deps = entry.get("depends_on") or []
        if not isinstance(deps, list):
            raise PlanValidationError(f"plan step {i}: depends_on must be a list")
        for dep in deps:
            if dep not in seen_steps:
                raise PlanValidationError(
                    f"plan step {i}: depends_on {dep!r} is not an earlier step")

        question = entry.get("question") or f"{division}/{intent} for the target"
        subtasks.append(Subtask(step=step, division=division, question=str(question),
                                skill=skill, depends_on=list(deps)))
        seen_steps.add(step)
    return subtasks


def bind_questions(
    questions: list[dict[str, Any]], routing: dict[str, Any]
) -> tuple[list[Subtask], list[dict[str, Any]]]:
    """Bind a hybrid planner's free-form questions to functional skills.

    The hybrid planner reasons up an *ideal* investigation as natural-language
    questions, each with a best-guess (division, intent). This splits them:

      * a question whose (division, intent) routes to a functional skill becomes a
        bound :class:`Subtask` (executed this run),
      * a question with no fitting / no functional skill becomes a **proposed
        experiment** — the agent knew what it wanted but no tool can answer it yet.

    Returns ``(subtasks, experiments)``. Unlike ``validate_and_bind_plan`` this never
    raises on an unroutable question — it just routes it to the experiments bucket, so
    the agent's full reasoning survives even when only part of it is executable. A
    question that fits a real (division, intent) but a *deferred* skill still routes to
    experiments (we only execute FUNCTIONAL_SKILLS), with a note naming the skill.
    """
    routable = _routable_intents(routing)            # functional intents only
    all_intents = {                                  # every intent, for "deferred" detection
        div: {i for i, e in ix.items() if isinstance(e, dict)}
        for div, ix in routing.items() if isinstance(ix, dict)
    }
    subtasks: list[Subtask] = []
    experiments: list[dict[str, Any]] = []
    seen_steps: set[str] = set()
    n = 0
    for entry in questions or []:
        if not isinstance(entry, dict):
            continue
        q = str(entry.get("question") or "investigate the target").strip()
        division, intent = entry.get("division"), entry.get("intent")
        bound = (division in routable and intent in routable.get(division, set()))
        if bound:
            n += 1
            step = f"step_{n:02d}_{intent}"
            deps = [d for d in (entry.get("depends_on") or []) if d in seen_steps]
            subtasks.append(Subtask(step=step, division=division, question=q,
                                    skill=_skill_for(routing, division, intent),
                                    depends_on=deps))
            seen_steps.add(step)
        else:
            # name the tool gap when the question fit a real intent but a deferred skill
            note = entry.get("rationale") or ""
            if division in all_intents and intent in all_intents.get(division, set()):
                note = (note + " ").strip() + f"(needs {_skill_for(routing, division, intent)}, " \
                       "not yet runnable — see docs/deferred-skills.md)"
            experiments.append({"experiment": q, "rationale": note,
                                "expected_readout": "would answer this open question"})
    return subtasks, experiments


def catalog_skills(routing: dict[str, Any]) -> set[str]:
    """Every skill name reachable in routing.yaml (primary ``skill`` + ``also`` lists).

    Used to validate an *agent-chosen* reroute target — the reviewer may only route
    to a skill that actually exists in the catalog, never an invented one.
    """
    skills: set[str] = set()
    for intents in routing.values():
        if not isinstance(intents, dict):
            continue
        for entry in intents.values():
            if isinstance(entry, dict):
                if isinstance(entry.get("skill"), str):
                    skills.add(entry["skill"])
                skills.update(s for s in entry.get("also", []) if isinstance(s, str))
    return skills


REROUTE_FALLBACK_SKILL = "lit-synthesizer"  # the routing.yaml-designated reroute target

# Skills whose output is *question-sensitive*: a re-route can ask them a deeper,
# different question (a gap's ``missing``) and genuinely get new evidence. Only the
# free-text live search qualifies — its query is steered by a reviewer ``focus``.
# Gene-DB skills are deterministic in the gene alone, so a "different question" cannot
# change their result; the review loop blocks repeats of those so it never thrashes
# re-running a lookup that can't improve.
QUESTION_SENSITIVE_SKILLS = frozenset({"lit-synthesizer"})


def group_by_division(subtasks: list[Subtask]) -> list[tuple[str, list[Subtask]]]:
    """Group routed subtasks by division, preserving first-seen order.

    Each group becomes one **division scientist agent** (Virtual Biotech structure:
    the CSO delegates to domain-specialised scientist agents). Order-stable so the
    trace and report are deterministic.
    """
    order: list[str] = []
    groups: dict[str, list[Subtask]] = {}
    for t in subtasks:
        if t.division not in groups:
            groups[t.division] = []
            order.append(t.division)
        groups[t.division].append(t)
    return [(d, groups[d]) for d in order]


def _reroute_task(gap: dict[str, Any], routing: dict[str, Any] | None = None,
                  step_n: int = 6, executed: set[str] | None = None) -> Subtask:
    """Build a follow-up Subtask from a reviewer gap (change #3: validated target).

    The reviewer *chooses* ``route_to``; we keep it honest — if it names a skill that
    isn't in the catalog (or names none), fall back to the routing.yaml-designated
    reroute target rather than executing an invented skill. ``step_n`` lets the
    bounded review loop (change #2) number successive reroutes step_06, step_07, ….

    ``executed`` is the set of skills already run this assessment. It is used by
    the caller for convergence (a reroute that names an already-run skill adds no
    evidence, so the loop stops); we surface it here only so the returned Subtask
    carries the chosen skill faithfully — we do **not** substitute an arbitrary
    unrun skill, since an off-axis skill (e.g. a pharmacogenomics tool for a
    specificity gap) is worse than not re-routing at all.
    """
    executed = executed or set()
    chosen = gap.get("route_to")
    if routing is not None and chosen not in catalog_skills(routing):
        chosen = REROUTE_FALLBACK_SKILL
    elif not chosen:
        chosen = REROUTE_FALLBACK_SKILL
    return Subtask(
        step=f"step_{step_n:02d}_reroute",
        division="target_id_and_prioritization",
        question=f"Reviewer follow-up: {gap.get('missing', 'fill gap')} — {gap.get('why', '')}".strip(),
        skill=chosen,
    )


# --------------------------------------------------------------------------- #
# Reviewer panel — N lens-specialised reviewers, deterministically aggregated
# --------------------------------------------------------------------------- #
# Each lens is an independent skeptic with a distinct focus. The harness fans
# these out concurrently (one agent call each) and aggregate_panel_review folds
# their verdicts into the single review payload _review_loop already consumes.
REVIEWER_LENSES = [
    {"key": "safety",
     "focus": "off-target / broad-tissue expression and adverse-event risk. Flag any target "
              "advanced without a safety read; a broad-expression target is a liability."},
    {"key": "genetics",
     "focus": "strength of germline/somatic support. Flag over-reach — correlational ORs or "
              "weak associations stated as causal. Absent GWAS is non-disqualifying for IO."},
    {"key": "specificity",
     "focus": "cell-type and malignant-cell localization. For ADC/CAR-T, flag specificity that "
              "is stromal rather than tumour-cell; that materially changes the conclusion."},
    {"key": "clinical",
     "focus": "trial precedent and translatability. Flag a recommendation with no clinical or "
              "competitive-landscape context, or stale evidence needing a literature check."},
]

PANEL_REROUTE_MIN_VOTES = 2  # re-route when >= this many lenses flag a gap


def _axis_min(reviews: list[dict[str, Any]], axis: str) -> int | None:
    """Skeptical score aggregation: the weakest lens sets the panel score per axis."""
    vals = [r.get("scores", {}).get(axis) for r in reviews]
    nums = [v for v in vals if isinstance(v, (int, float))]
    return int(min(nums)) if nums else None


def aggregate_panel_review(lens_reviews: list[tuple[str, dict[str, Any]]],
                           routing: dict[str, Any] | None = None,
                           min_votes: int = PANEL_REROUTE_MIN_VOTES,
                           extra_gaps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Fold N lens verdicts into one review payload (deterministic, testable).

    - verdict: ``re-route`` iff >= ``min_votes`` lenses returned ``re-route``; the
      panel is skeptical but not hair-trigger (one lone dissent doesn't reroute).
      **Exception:** any ``extra_gaps`` entry with ``forces_reroute`` (e.g. a
      Prometheux-derived *structural* gap — a required axis with no evidence at all)
      forces ``re-route`` regardless of the lens vote count. A proven missing axis is
      a deductive fact, not a judgement, so the engine is a non-silenceable member.
    - gaps: union across lenses **and** ``extra_gaps``, deduped by (route_to, missing);
      each tagged with the lenses that raised it. ``extra_gaps`` are treated as a lens
      whose key they carry (``["prometheux"]``). A forcing gap sorts first so
      _review_loop reroutes on it. If ``routing`` is given, a gap whose ``route_to``
      isn't in the catalog is kept but validated downstream by _reroute_task.
    - scores: min per axis across lenses (weakest link).
    - experiments: union across lenses.
    The ``lens`` provenance on each gap is what makes "survived N skeptics" auditable.
    """
    reviews = [r for _, r in lens_reviews]
    votes = sum(1 for r in reviews if r.get("verdict") == "re-route")

    seen: dict[tuple, dict[str, Any]] = {}
    for key, r in lens_reviews:
        for gap in r.get("gaps", []) or []:
            if not isinstance(gap, dict):
                continue
            sig = (gap.get("route_to"), gap.get("missing"))
            if sig in seen:
                seen[sig].setdefault("lenses", []).append(key)
            else:
                g = dict(gap)
                g["lenses"] = [key]
                seen[sig] = g
    for gap in extra_gaps or []:
        if not isinstance(gap, dict):
            continue
        sig = (gap.get("route_to"), gap.get("missing"))
        if sig in seen:
            # merge: keep the forcing flag + explanation, union the lens provenance
            seen[sig].update({k: v for k, v in gap.items() if k != "lenses"})
            for lk in gap.get("lenses", []):
                if lk not in seen[sig].setdefault("lenses", []):
                    seen[sig]["lenses"].append(lk)
        else:
            seen[sig] = dict(gap)
    gaps = list(seen.values())
    # A proven structural gap forces re-route even without the min_votes lens majority.
    forced = any(g.get("forces_reroute") for g in gaps)
    verdict = "re-route" if (votes >= min_votes or forced) else "synthesize"
    # Forcing gaps first, then most-corroborated, so _review_loop reroutes on them.
    gaps.sort(key=lambda g: (bool(g.get("forces_reroute")), len(g.get("lenses", []))),
              reverse=True)

    experiments = [e for _, r in lens_reviews for e in (r.get("experiments", []) or [])]
    return {
        "verdict": verdict,
        "scores": {axis: _axis_min(reviews, axis)
                   for axis in ("relevance", "evidence", "thoroughness")},
        "gaps": gaps,
        "experiments": experiments,
        "panel": {"n_lenses": len(lens_reviews), "reroute_votes": votes,
                  "min_votes": min_votes, "forced_by_engine": forced,
                  "lenses": [k for k, _ in lens_reviews]},
    }


def _agent_task(role: str, prompt_path: Path, context: str) -> dict[str, Any]:
    """Describe a reasoning step delegated to the driving agent.

    This skill performs no LLM call. A subagent-capable harness (e.g. Claude
    Code) runs ``prompt_path`` on ``context`` to produce this role's output —
    ideally as its own subagent. Standalone, the step stays an honest stub.
    """
    return {
        "role": role,
        "prompt_file": str(prompt_path.relative_to(SKILL_DIR)),
        "context": context,
        "status": DELEGATE,
    }


# --------------------------------------------------------------------------- #
# Reasoning roles — delegated to the agent (never an LLM call)
# --------------------------------------------------------------------------- #
def load_briefing(query: str, case: str) -> dict[str, Any]:
    """STEP A: Chief-of-Staff briefing.

    An honest delegation stub — the driving agent runs prompts/chief_of_staff.md
    to fill it. This skill makes no LLM call.
    """
    return {
        "context": "[delegate-to-agent] The Chief-of-Staff briefing is produced by the driving "
        "agent running prompts/chief_of_staff.md on the query (e.g. a Claude Code subagent). "
        "This skill performs no LLM call.",
        "data_availability": [],
        "priority_questions": [],
        "feasibility_flags": [],
        "source": DELEGATE,
        "agent_prompt": "prompts/chief_of_staff.md",
    }


def _run_skill_live(skill: str, target: str | None = None,
                    focus: str | None = None,
                    question: str | None = None) -> dict[str, Any]:
    """Execute a routed axis via ToolUniverse (no LLM). Two tiers:

    1. **Pinned** — if ``skill`` maps to a tool in ``tool_router.yaml``,
       ``run_predefined_tool`` answers it (fast, deterministic, offline-cacheable).
    2. **Discovery** — otherwise, run the *custom-experiment* loop over the step's
       ``question``: Tool_Finder → ToolGraph compose → execute_tool
       (``discover_and_run``). This is how a novel axis with no pinned tool still
       gets answered — the plan selects tools from all of ToolUniverse at runtime.

    Both tiers execute via the injected agent executor when set, else in-process
    (``tooluniverse`` package), else emit a descriptor for the driving agent to run.
    An axis with neither a mapping nor a discoverable tool returns an honest
    "not executed" envelope; never a fabrication. ``focus`` steers a deeper
    re-route's discovery query.
    """
    try:
        import tool_backend
    except Exception:  # pragma: no cover - backend import must never crash the run
        return {"status": "not executed", "reason": "tool_backend import failed."}
    # Tier 1: pinned mapping
    predefined = tool_backend.run_predefined_tool(skill, target or "")
    if predefined is not None:
        return predefined
    # Tier 2: dynamic discovery over the sub-question (the custom-experiment path)
    probe = " ".join(p for p in (question, focus) if p) or skill
    return tool_backend.discover_and_run(probe, target or "")


def execute_skill(task: Subtask, case: str, live: bool,
                  target: str | None = None, focus: str | None = None) -> dict[str, Any]:
    """STEP C: produce a result envelope for a routed skill.

    Always attempts the live path — the routed axis is executed through its
    predefined ToolUniverse tool (``tool_router.yaml``); an axis with no mapping
    returns an honest "not executed" stub, never a fabricated result. ``target``
    (the query's "<gene> in <disease>") is passed to the tool call. ``focus`` is
    an optional reviewer follow-up for a *deeper* re-route. No LLM is involved.
    """
    envelope = {
        "step": task.step,
        "division": task.division,
        "skill": task.skill,
        "question": task.question,
    }
    if live:
        result = _run_skill_live(task.skill, target=target, focus=focus,
                                 question=task.question)
    else:
        # default mode: no live backend is touched — routed steps stay honest stubs
        # for the driving agent to fill (this skill makes no LLM call).
        result = {"status": "not executed",
                  "reason": "default mode — run with --live to execute this axis "
                            "via its ToolUniverse tool."}
    envelope["result"] = result
    # The ToolUniverse backend labels its own source (tooluniverse / tool-descriptor /
    # unavailable); honour it. A bare "not executed" stub (no source) is 'unavailable'.
    envelope["source"] = result.get("source", "unavailable") if isinstance(result, dict) else "unavailable"
    return envelope


def load_review(query: str, case: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    """STEP D: Scientific-Reviewer verdict.

    A delegation stub defaulting to 'synthesize' (no re-route) — the driving
    agent runs prompts/reviewer.md to audit the evidence and may set verdict
    're-route'. This skill makes no LLM call.
    """
    return {
        "verdict": "synthesize", "scores": {}, "gaps": [],
        "note": "[delegate-to-agent] The Scientific-Reviewer audit is produced by the driving "
        "agent running prompts/reviewer.md over the evidence; standalone it defaults to "
        "'synthesize' with no re-route. This skill performs no LLM call.",
        "source": DELEGATE,
        "agent_prompt": "prompts/reviewer.md",
    }


def load_synthesis(query: str, case: str, results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """STEP E input: the CSO recommendation + liabilities.

    Always None — the recommendation is written by the driving agent
    (prompts/orchestrator.md) over the evidence; this skill emits the routed
    evidence, not a generated recommendation.
    """
    return None


# --------------------------------------------------------------------------- #
# STEP E: synthesis (report.md)
# --------------------------------------------------------------------------- #
def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _result_digest(env: dict[str, Any]) -> str:
    result = env.get("result", {})
    if isinstance(result, dict):
        if "status" in result:
            return _md_escape(f"{result['status']} — {result.get('reason', '')}")[:160]
        if "interpretation" in result:
            return _md_escape(f"tau={result.get('tau')}; {result.get('interpretation', '')}")
        if "summary" in result:
            return _md_escape(str(result["summary"]))[:180]
        keys = ", ".join(list(result.keys())[:4])
        return _md_escape(f"{{{keys}}}")
    return _md_escape(str(result))[:120]


def _provenance(env: dict[str, Any]) -> tuple[str, str]:
    """(marker, grade-phrase) for a step, from how it was sourced."""
    return PROVENANCE.get(env.get("source", ""), ("? unknown", "unknown provenance"))


def _evidence_grade(env: dict[str, Any]) -> str:
    src = env.get("source", "")
    return {"tooluniverse": "strong", "tool-descriptor": "supporting",
            "web": "supporting"}.get(src, "absent")


_NCT_RE = re.compile(r"\bNCT\d{8}\b", re.IGNORECASE)
_EUCTR_RE = re.compile(r"\b\d{4}-\d{6}-\d{2}\b")


def _trial_deep_link(text: str) -> str:
    """Deep link to the actual trial record if `text` names a registry id, else ""."""
    m = _NCT_RE.search(text or "")
    if m:
        return f"https://clinicaltrials.gov/study/{m.group(0).upper()}"
    m = _EUCTR_RE.search(text or "")
    if m:
        return ("https://www.clinicaltrialsregister.eu/ctr-search/search"
                f"?query={m.group(0)}")
    return ""


def _evidence_reference(env: dict[str, Any]) -> str:
    """A traceable citation for one evidence step: registry source + harvested provenance."""
    skill = env.get("skill", "")
    reg = SOURCE_REGISTRY.get(skill, {"name": skill or "unknown", "url": ""})
    bits = [reg["name"]]
    res = env.get("result", {})
    if isinstance(res, dict):
        for k in ("atlas", "atlas_name", "census_version"):
            if res.get(k):
                bits.append(f"{k}={res[k]}")
        if res.get("source") and str(res["source"]) not in bits:
            bits.append(str(res["source"]))
    cite = "; ".join(_md_escape(str(b)) for b in bits if b)
    # Prefer a deep link to the *actual* trial record (NCT…/EUCTR id) over the
    # registry homepage, so trial citations point at the study, not clinicaltrials.gov/.
    deep = _trial_deep_link(json.dumps(res, default=str)) if isinstance(res, dict) else ""
    url = deep or reg.get("url", "")
    if url:
        cite += f" — {url}"
    return cite


def _norm_liabilities(synthesis: dict[str, Any] | None) -> list[str]:
    """Liabilities as 'risk → mitigation' strings (accept str or {risk,mitigation})."""
    out = []
    for item in list((synthesis or {}).get("liabilities", [])):
        if isinstance(item, dict):
            risk = item.get("risk", "risk")
            mit = item.get("mitigation")
            out.append(f"**{risk}**" + (f" — *mitigation:* {mit}" if mit else ""))
        else:
            out.append(str(item))
    return out


def synthesize_report(query: str, case: str, briefing: dict[str, Any],
                      results: list[dict[str, Any]], review: dict[str, Any],
                      synthesis: dict[str, Any] | None,
                      decision_engine: dict[str, Any] | None = None,
                      ranking: list[dict[str, Any]] | None = None) -> str:
    """Build a structured target-identification dossier from the assembled evidence."""
    syn = synthesis or {}
    symbol = (case or "target").upper()
    executed = [e for e in results if e.get("source") in EXECUTED_SOURCES]
    L: list[str] = [f"# Target Assessment — {symbol} · {query}", ""]
    L += [f"*Virtual-Biotech CSO v{VERSION} · mode: live/agent-driven · the skill makes no LLM call; "
          "reasoning is delegated to the driving agent via `prompts/`.*", ""]

    # 1 — Executive summary (decision + confidence + recommendation)
    # The Prometheux decision layer derives the tier deductively from per-axis
    # coverage; when present it is authoritative for the Decision field, and the
    # agent's free-text becomes rationale. If the two disagree, both are shown and
    # the divergence is flagged — the derived tier is never silently overridden.
    agent_decision = syn.get("decision")
    confidence = syn.get("confidence") or ("see reviewer scores" if executed else "n/a")
    L += ["## Executive summary", ""]
    if decision_engine:
        tier = decision_engine["tier"]
        L += [f"- **Decision:** {tier} "
              f"_(derived · coverage {decision_engine['score']}/{decision_engine['max_score']})_",
              f"- **Confidence:** {confidence}",
              f"- **Basis:** {decision_engine['explanation']}"]
        absent = decision_engine.get("absent_axes") or []
        if absent:
            L += [f"- **No information on:** {', '.join(absent)} "
                  "— absent (not weak evidence); the score reflects absence."]
        L += [""]
        if agent_decision and agent_decision != tier:
            L += [f"> ⚠️ **Divergence:** the synthesis agent proposed **{agent_decision}**, "
                  f"but the deductive decision layer derives **{tier}** from the evidence "
                  "coverage. The derived tier is the Decision of record; the agent's "
                  "rationale is below.", ""]
    else:
        decision = agent_decision or "REVIEW"
        L += [f"- **Decision:** {decision}", f"- **Confidence:** {confidence}", ""]
    if syn.get("recommendation"):
        L += [str(syn["recommendation"]), ""]
    elif not executed:
        L += ["_No skills executed, so no data-derived recommendation is asserted._ The driving "
              "agent writes the recommendation (`prompts/orchestrator.md`) once evidence is present.", ""]
    else:
        L += ["_Recommendation is written by the driving agent from the evidence below "
              "(`prompts/orchestrator.md`)._", ""]

    # 1b — Comparative ranking (Prometheux explain-a-rank, only with a rival on the graph)
    if ranking:
        L += ["## Comparative ranking", "",
              "_Deductive explain-a-rank over the accumulated evidence graph: each edge "
              "names the axis on which one target has a strong claim the other lacks._", ""]
        for e in ranking:
            L.append(f"- **{e['winner']} > {e['loser']}** on _{e['axis']}_ — {e['explanation']}")
        L.append("")

    # 2 — Target overview
    L += ["## Target overview", "",
          str(syn.get("target_overview") or briefing.get("context", "(no briefing)")), ""]

    # 3 — Evidence by division (with provenance, grade, and per-row reference)
    L += ["## Evidence by division", "",
          "| # | Division | Sub-question | Skill | Provenance | Grade | Key result | Ref |",
          "|---|----------|--------------|-------|------------|-------|------------|-----|"]
    for i, env in enumerate(results, 1):
        marker, _ = _provenance(env)
        L.append(
            f"| {i} | {env['division']} | {_md_escape(env['question'])} | `{env['skill']}` | "
            f"{marker} | {_evidence_grade(env)} | {_result_digest(env)} | [{i}] |"
        )
    L.append("")

    # 4 — Evidence strength
    scores = review.get("scores", {})
    n_strong = sum(1 for e in results if _evidence_grade(e) == "strong")
    L += ["## Evidence strength", "",
          f"- {n_strong}/{len(results)} steps graded **strong** (live skill data); "
          f"{len(executed)} executed, {len(results) - len(executed)} absent.",
          f"- Reviewer scores — relevance: {scores.get('relevance', '?')}, "
          f"evidence: {scores.get('evidence', '?')}, thoroughness: {scores.get('thoroughness', '?')} (1–5).", ""]

    # 5 — Liabilities & risks
    L += ["## Liabilities & risks", ""]
    liabs = _norm_liabilities(syn)
    for item in liabs:
        L.append(f"- {item}")
    if not liabs:
        L.append("- _None derived (synthesis pending)._")
    L.append("")

    # 6 — Evidence gaps (deterministic: absent/illustrative steps + reviewer gaps + agent)
    L += ["## Evidence gaps", ""]
    gap_lines = []
    for e in results:
        if _evidence_grade(e) == "absent":
            _, phrase = _provenance(e)
            gap_lines.append(f"- **{e['division']} / {e['skill']}** — {phrase} "
                             f"({e['step']}); question unresolved: {_md_escape(e['question'])}")
    for gap in review.get("gaps", []):
        gap_lines.append(f"- **{gap.get('missing', 'gap')}** — {gap.get('why', '')}")
    for g in syn.get("evidence_gaps", []):
        gap_lines.append(f"- {g}")
    L += (gap_lines or ["- _No gaps flagged._"]) + [""]

    # 7 — Proposed experiments to strengthen the evidence
    L += ["## Proposed experiments to strengthen evidence", ""]
    exp_lines = []
    for exp in syn.get("proposed_experiments", []):
        if isinstance(exp, dict):
            exp_lines.append(f"- **{exp.get('experiment', 'experiment')}** — "
                             f"expected readout: {exp.get('expected_readout', '?')}. "
                             f"{exp.get('rationale', '')}")
        else:
            exp_lines.append(f"- {exp}")
    for exp in review.get("experiments", []):
        exp_lines.append(f"- **{exp.get('proposed_experiment', exp.get('missing', 'experiment'))}** "
                         f"(via `{exp.get('route_to', 'a skill')}`) — expected readout: "
                         f"{exp.get('expected_readout', '?')}. {exp.get('why', '')}")
    if not exp_lines:  # deterministic fallback from reviewer gaps
        for gap in review.get("gaps", []):
            exp_lines.append(f"- Fill **{gap.get('missing', 'gap')}** by running "
                             f"`{gap.get('route_to', 'the relevant skill')}`.")
    L += (exp_lines or ["- _None proposed._"]) + [""]

    # 8 — References & data sources (numbered, per evidence step)
    L += ["## References & data sources", ""]
    for i, env in enumerate(results, 1):
        marker, _ = _provenance(env)
        L.append(f"{i}. **{env['skill']}** [{marker}] — {_evidence_reference(env)}")
    L.append("")

    # 9 — Reproducibility + disclaimer
    L += ["## Reproducibility", "",
          "- Bundle: `reproducibility/{commands.sh, environment.yml, checksums.sha256}`; "
          "per-step provenance markers above (🔧 live · 🌐 web · ⚪ absent).", "",
          "---",
          "*Trial-success priors are correlational (Zhang et al. 2026); not a guarantee of "
          "clinical success.*", "", f"*{DISCLAIMER}*", ""]
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# Output contract: report.md + result.json + reproducibility/
# --------------------------------------------------------------------------- #
def _write_result_json(out_dir: Path, summary: dict[str, Any], data: dict[str, Any]) -> Path:
    """Write the standard result.json envelope (optional shared helper if importable)."""
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from clawbio.common.report import write_result_json  # type: ignore

        return write_result_json(out_dir, skill=SKILL_NAME, version=VERSION,
                                  summary=summary, data=data)
    except Exception:
        envelope = {"skill": SKILL_NAME, "version": VERSION, "summary": summary, "data": data}
        path = out_dir / "result.json"
        path.write_text(json.dumps(envelope, indent=2, default=str))
        return path


def _write_reproducibility(repro_dir: Path, argv: list[str], output_files: list[Path]) -> None:
    repro_dir.mkdir(parents=True, exist_ok=True)
    (repro_dir / "commands.sh").write_text(
        "#!/usr/bin/env bash\n# Command used to produce this report\n"
        "python cso.py " + " ".join(argv) + "\n"
    )
    import platform

    deps = []
    for mod in ("pyyaml",):
        try:
            m = __import__("yaml" if mod == "pyyaml" else mod)
            deps.append(f"      - {mod}=={getattr(m, '__version__', 'unknown')}")
        except Exception:
            deps.append(f"      - {mod}")
    (repro_dir / "environment.yml").write_text(
        f"name: {SKILL_NAME}\nchannels:\n  - conda-forge\n  - nodefaults\n"
        f"dependencies:\n  - python={platform.python_version()}\n  - pip\n  - pip:\n"
        + "\n".join(deps) + "\n"
    )
    checks = []
    for path in output_files:
        if path.exists():
            checks.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    (repro_dir / "checksums.sha256").write_text("\n".join(checks) + "\n")


# --------------------------------------------------------------------------- #
# Orchestration loop
# --------------------------------------------------------------------------- #
def run(query: str, out_dir: Path, live: bool, argv: list[str]) -> dict[str, Any]:
    case = case_key(query)
    routing = load_routing()

    briefing = load_briefing(query, case)
    subtasks = decompose_and_route(query, case, routing)

    results: list[dict[str, Any]] = [execute_skill(t, case, live) for t in subtasks]

    review = load_review(query, case, results)
    if review.get("verdict") == "re-route":
        gap = (review.get("gaps") or [{}])[0]
        results.append(execute_skill(_reroute_task(gap), case, live))

    synthesis = load_synthesis(query, case, results)
    report_md = synthesize_report(query, case, briefing, results, review, synthesis)

    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "report.md"
    report_path.write_text(report_md, encoding="utf-8")

    # Reasoning roles the driving agent should run (one subagent per role, ideally).
    agent_tasks = [
        _agent_task("chief_of_staff", CHIEF_OF_STAFF_PROMPT, f"User query: {query}"),
        _agent_task("scientific_reviewer", REVIEWER_PROMPT,
                    "Audit the evidence and return verdict synthesize|re-route with gaps."),
        _agent_task("cso_synthesis", ORCHESTRATOR_PROMPT,
                    "Write recommendation + liabilities from the evidence."),
    ]

    syn = synthesis or {}
    references = [
        {"n": i, "skill": e["skill"], "provenance": _provenance(e)[0],
         "grade": _evidence_grade(e), "source": _evidence_reference(e), "step": e["step"]}
        for i, e in enumerate(results, 1)
    ]
    evidence_gaps = (
        [f"{e['division']}/{e['skill']} ({e['step']}): {_provenance(e)[1]}"
         for e in results if _evidence_grade(e) == "absent"]
        + [g.get("missing") for g in review.get("gaps", [])]
        + list(syn.get("evidence_gaps", []))
    )
    proposed_experiments = list(syn.get("proposed_experiments", [])) + list(review.get("experiments", []))

    summary = {
        "query": query,
        "case": case,
        "mode": "live" if live else "default",
        "n_steps": len(results),
        "reviewer_verdict": review.get("verdict", "synthesize"),
        "n_executed": len([e for e in results if e.get("source") in EXECUTED_SOURCES]),
        "decision": syn.get("decision", "REVIEW"),
        "confidence": syn.get("confidence", "n/a"),
        "calls_llm": False,
    }
    data = {
        "briefing": briefing,
        "plan": [t.as_plan_entry() for t in subtasks],
        "evidence": results,
        "review": review,
        "synthesis": synthesis,
        "references": references,
        "evidence_gaps": evidence_gaps,
        "proposed_experiments": proposed_experiments,
        "agent_tasks": agent_tasks,
        "disclaimer": DISCLAIMER,
    }
    result_path = _write_result_json(out_dir, summary, data)
    _write_reproducibility(out_dir / "reproducibility", argv, [report_path, result_path])
    return {"report": str(report_path), "result": str(result_path), "summary": summary}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cso.py",
        description="Virtual-Biotech CSO — orchestrate a therapeutic-target assessment "
        "(no LLM call; reasoning delegated to the driving agent).",
    )
    p.add_argument("--query", type=str, default=None,
                   help=f"Target-assessment query (default: {DEFAULT_QUERY!r})")
    p.add_argument("--live", action="store_true",
                   help="Execute routed axes via their predefined ToolUniverse tools (reasoning delegated to the agent)")
    p.add_argument("--output", "--out", dest="out", type=str, default="./output",
                   help="Output directory")
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    query = args.query or DEFAULT_QUERY
    out_dir = Path(args.out).expanduser().resolve()
    summary = run(query, out_dir, live=args.live, argv=argv)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
