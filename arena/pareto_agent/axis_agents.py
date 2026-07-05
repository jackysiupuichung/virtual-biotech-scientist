"""Six axis-specific pairwise comparison agents, run concurrently per hypothesis pair."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from arena.pareto_agent.llm_client import LLMJSONError, call_llm_json
from arena.pareto_agent.models import AXIS_NAMES, AxisComparison, AxisName
from arena.pareto_agent.prompts import render_axis_prompt


def _insufficient_evidence_fallback(axis: AxisName) -> AxisComparison:
    return AxisComparison(
        axis=axis,
        relation="insufficient_evidence",
        confidence="low",
        rationale="Axis comparison failed or could not be parsed.",
        decisive_evidence=[],
        missing_evidence=["valid axis comparison output"],
    )


async def compare_axis(
    hypothesis_A: Dict[str, Any], hypothesis_B: Dict[str, Any], axis: AxisName
) -> AxisComparison:
    prompt = render_axis_prompt(axis, hypothesis_A, hypothesis_B)
    try:
        return await call_llm_json(prompt, AxisComparison)
    except LLMJSONError:
        # A single failed axis must not abort the whole comparison; treat it
        # conservatively as unresolved so it can never contribute to dominance.
        return _insufficient_evidence_fallback(axis)


async def compare_all_axes(
    hypothesis_A: Dict[str, Any], hypothesis_B: Dict[str, Any]
) -> Dict[AxisName, AxisComparison]:
    results = await asyncio.gather(
        *[compare_axis(hypothesis_A, hypothesis_B, axis) for axis in AXIS_NAMES],
        return_exceptions=True,
    )

    axis_comparisons: Dict[AxisName, AxisComparison] = {}
    for axis, result in zip(AXIS_NAMES, results):
        if isinstance(result, BaseException):
            axis_comparisons[axis] = _insufficient_evidence_fallback(axis)
        else:
            axis_comparisons[axis] = result
    return axis_comparisons
