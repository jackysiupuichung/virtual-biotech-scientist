"""Red-flag screening: an independent per-hypothesis LLM pass before Pareto analysis."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Tuple

from arena.pareto_agent.llm_client import LLMJSONError, call_llm_json
from arena.pareto_agent.models import RedFlag, RedFlagResult
from arena.pareto_agent.prompts import render_red_flag_prompt


async def red_flag_one(hypothesis: Dict[str, Any]) -> RedFlagResult:
    prompt = render_red_flag_prompt(hypothesis)
    try:
        return await call_llm_json(prompt, RedFlagResult)
    except LLMJSONError:
        # Infra/parse failure, not a scientific judgement: default to "keep" so a
        # transient LLM failure cannot silently discard a hypothesis, but surface
        # a minor flag so the failure is visible in the run output.
        return RedFlagResult(
            hypothesis_id=hypothesis.get("id", "unknown"),
            decision="keep",
            red_flags=[
                RedFlag(
                    severity="minor",
                    category="evidence_quality",
                    reason="Red-flag screening failed or could not be parsed; hypothesis was kept by default.",
                )
            ],
            rationale="Automated red-flag screening did not complete successfully.",
        )


async def red_flag_filter(
    hypotheses: List[Dict[str, Any]],
) -> Tuple[List[RedFlagResult], List[Dict[str, Any]]]:
    """Screen every hypothesis concurrently; return (removed results, survivors)."""
    results = await asyncio.gather(*[red_flag_one(h) for h in hypotheses])

    removed_ids = set()
    red_flagged: List[RedFlagResult] = []
    for hypothesis, result in zip(hypotheses, results):
        is_critical = any(f.severity == "critical" for f in result.red_flags)
        if result.decision == "remove" or is_critical:
            removed_ids.add(hypothesis["id"])
            red_flagged.append(result)

    survivors = [h for h in hypotheses if h["id"] not in removed_ids]
    return red_flagged, survivors
