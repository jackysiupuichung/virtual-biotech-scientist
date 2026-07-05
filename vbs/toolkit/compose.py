"""compose.py — self-improving toolkit: compose a new tool on a gap (SELF_IMPROVING.md Level C).

The most on-theme self-improvement level: ToolUniverse natively supports **creating
tools from natural-language descriptions and iteratively optimising tool specs**. So
when the arena hits an axis no existing tool covers, the agent composes a NEW tool
from primitives, registers it, and uses it — the toolkit grows when the scientist
meets its own limits. Precedent: Voyager's growing skill library; ToolUniverse's
own tool-composition feature.

Honest scope (SELF_IMPROVING.md): demonstrate ONE scripted instance working, not a
general capability — the riskiest level to get live, so keep it bounded.

SCAFFOLD: the one scripted case is specified (spatial co-localisation of target +
immune cells, composed from existing primitives); the ToolUniverse compose-and-
register call is the TODO.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ComposedTool:
    name: str
    description: str
    primitives: list[str]  # existing ToolUniverse tools this composes


# The single scripted instance (SELF_IMPROVING.md Level C demo).
SPATIAL_COLOCALISATION = ComposedTool(
    name="spatial_target_immune_colocalisation",
    description=("Given a target gene and a tissue, report spatial co-localisation of the "
                 "target with immune cell populations — an axis no single catalog tool covers."),
    primitives=["CELLxGENE_query", "OpenTargets_get_target_factors"],
)


def compose_on_gap(gap_description: str, *, client=None) -> ComposedTool:
    """Compose a new ToolUniverse tool to fill an uncovered axis.

    TODO(B7): call ToolUniverse's tool-composition API with ``gap_description`` to
    synthesise a spec from ``client``'s available primitives, register it, and
    return the handle so a division can immediately call it. For the demo, run the
    single scripted SPATIAL_COLOCALISATION case end-to-end.
    """
    raise NotImplementedError(
        "tool composition not wired — call ToolUniverse compose-from-NL to build "
        "and register a tool for the uncovered axis. See TODO(B7)."
    )
