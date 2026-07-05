"""Prompt templates for the red-flag and axis-comparison LLM calls.

Both prompts ask exclusively for qualitative judgements (relation / confidence /
rationale). Neither prompt may ask for a score, rating, probability, rank, or
percentage — enforced by review, not by code, since this is a prompting contract.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from arena.pareto_agent.models import AxisName

AXIS_DESCRIPTIONS: Dict[str, str] = {
    "right_target": """
Compares the strength of causal and mechanistic support that the target is relevant to the disease.
Prefer human genetics, somatic genetics, perturbation evidence, pathway causality, disease biology, and curated disease association evidence.
Do not reward literature popularity alone.
""".strip(),
    "right_tissue": """
Compares whether the target is present, active, and disease-relevant in the right tissue, cell type, disease state, and patient context.
Prefer single-cell, spatial, disease-tissue, malignant-vs-stromal, or disease-context-specific evidence.
Penalize purely synthetic tissue assumptions.
""".strip(),
    "right_safety": """
Compares expected therapeutic safety margin.
Better means safer, more tolerable, and less likely to create unacceptable on-target or modality-related toxicity.
Consider known safety liabilities, essentiality, genetic constraint, knockout phenotypes, pathway toxicity, tissue distribution, and therapeutic window.
""".strip(),
    "right_patient": """
Compares likely patient impact and clinical relevance.
Prefer hypotheses with defined patient populations, biomarkers, clinical precedent, meaningful endpoints, high unmet need, and plausible therapeutic benefit.
""".strip(),
    "right_commercial": """
Compares commercial attractiveness and strategic whitespace.
Better means stronger differentiation, less crowding, clearer market opportunity, better competitive position, or more attractive indication niche.
Do not confuse scientific validity with commercial attractiveness.
""".strip(),
    "tractability": """
Compares feasibility of modulating the target with the proposed modality.
Prefer direct modality precedent, approved drugs, high-quality ligands, structural pockets, assayability, developable molecules, delivery feasibility, and modality-target fit.
""".strip(),
}

RED_FLAG_PROMPT = """You are a skeptical drug-discovery reviewer performing red-flag screening.

You will receive one therapeutic hypothesis report.

Your task is to decide whether this hypothesis should be allowed into a Pareto-front prioritisation analysis.

Look for critical issues, including:
- catastrophic or unacceptable safety liability
- no plausible target-disease rationale
- no plausible intervention modality
- disease context mismatch
- target is only a biomarker with no causal/interventional rationale
- evidence is almost entirely synthetic with no measured or curated support
- missing required fields
- contradictory report contents
- impossible or incoherent therapeutic hypothesis

Do not rank the hypothesis.
Do not assign numerical scores.

Return only valid JSON using this schema:

{{
  "hypothesis_id": string,
  "decision": "keep" | "remove",
  "red_flags": [
    {{
      "severity": "minor" | "major" | "critical",
      "category": "safety" | "biology" | "tissue" | "patient" | "commercial" | "tractability" | "schema" | "evidence_quality",
      "reason": string
    }}
  ],
  "rationale": string
}}

Removal guidance:
- Use "remove" if there is at least one critical red flag.
- Use "remove" if the report is too incoherent or under-evidenced to compare.
- Use "keep" if the hypothesis has weaknesses but remains comparable.

Hypothesis report:
{hypothesis_json}
"""

AXIS_COMPARISON_PROMPT = """You are an axis-specific drug-discovery comparison agent.

You compare two therapeutic hypotheses on exactly one criterion axis.

Axis:
{axis_name}

Axis meaning:
{axis_description}

You must compare Hypothesis A and Hypothesis B only on this axis.

Do not assign numerical scores.
Do not create a global ranking.
Do not consider other axes except when necessary for minimal context.
Do not reward a hypothesis merely because it has more verbose text.
Prefer direct, measured, curated, or experimentally grounded evidence over synthetic assumptions.

Allowed relations:
- A_better
- B_better
- tie
- incomparable
- insufficient_evidence

Definitions:
A_better:
  Hypothesis A is clearly or probably better than B on this axis.

B_better:
  Hypothesis B is clearly or probably better than A on this axis.

tie:
  A and B are materially similar on this axis.

incomparable:
  A and B differ in a way that cannot be fairly ordered on this axis.

insufficient_evidence:
  The reports do not contain enough evidence to compare A and B on this axis.

Confidence labels:
- high: evidence is direct and comparison is clear
- medium: evidence supports a direction but with caveats
- low: weak, indirect, synthetic, or incomplete evidence

Return only valid JSON using this schema:

{{
  "axis": "{axis_name}",
  "relation": "A_better" | "B_better" | "tie" | "incomparable" | "insufficient_evidence",
  "confidence": "high" | "medium" | "low",
  "rationale": string,
  "decisive_evidence": [string],
  "missing_evidence": [string]
}}

Hypothesis A:
{hypothesis_A_json}

Hypothesis B:
{hypothesis_B_json}
"""


def _sanitize(hypothesis: Dict[str, Any]) -> Dict[str, Any]:
    """Strip ground-truth fields the comparison agents must never see."""
    return {k: v for k, v in hypothesis.items() if k != "label"}


def render_red_flag_prompt(hypothesis: Dict[str, Any]) -> str:
    return RED_FLAG_PROMPT.format(
        hypothesis_json=json.dumps(_sanitize(hypothesis), indent=2)
    )


def render_axis_prompt(
    axis: AxisName, hypothesis_A: Dict[str, Any], hypothesis_B: Dict[str, Any]
) -> str:
    return AXIS_COMPARISON_PROMPT.format(
        axis_name=axis,
        axis_description=AXIS_DESCRIPTIONS[axis],
        hypothesis_A_json=json.dumps(_sanitize(hypothesis_A), indent=2),
        hypothesis_B_json=json.dumps(_sanitize(hypothesis_B), indent=2),
    )
