"""client.py — ToolUniverse MCP client (DESIGN.md §5, SETUP.md §1).

ToolUniverse (mims-harvard) is the evidence/tool layer: 1000+ scientific tools,
datasets, and models over MCP — Open Targets, CELLxGENE, TCGA/GDC, openFDA,
ClinicalTrials.gov, and a Boltz-2 backend. This module is the thin client the
divisions call.

CRITICAL constraint (DESIGN §5, SETUP §1): ToolUniverse ships 1000+ tool schemas;
loading them all blows the context window — the first failure mode to avoid. So
we use **compact mode / an explicit include-list** and expose only a handful of
discovery tools. The `.mcp.json` in the repo root already launches
``uvx --refresh tooluniverse``; the include-list is set here.

SCAFFOLD: the include-list + a ``call(tool, args)`` signature are defined; the MCP
transport (stdio session to the tooluniverse server, or the tooluniverse SDK) is
the TODO. Nothing here imports ToolUniverse at module load, so the package stays
importable without the (large) optional ``.[tools]`` dependency.
"""
from __future__ import annotations

from typing import Any

# The handful of discovery tools we expose — keep this SHORT (DESIGN §5).
# Extend deliberately; every added schema costs context. Names are ToolUniverse
# tool ids (verify against `tooluniverse-smcp --list`).
DEFAULT_INCLUDE_TOOLS = [
    "OpenTargets_get_associated_diseases",
    "OpenTargets_get_target_factors",
    "OpenFDA_get_adverse_events",
    "ClinicalTrials_search",
    "Boltz2_predict_binding_affinity",
]


class ToolUniverseClient:
    """Compact-mode MCP client over the ToolUniverse server.

    TODO(B5): open an MCP stdio session to ``uvx tooluniverse`` (or use the
    tooluniverse SDK directly), applying ``include_tools`` so only the discovery
    subset is loaded. Provide ``call(tool, args) -> dict`` returning the raw tool
    payload; divisions convert it to Evidence via adapter.py. Cache identical
    (tool, args) calls so the VoI no-thrash rule holds at the transport layer too.
    """

    def __init__(self, include_tools: list[str] | None = None, *, compact: bool = True) -> None:
        self.include_tools = include_tools or list(DEFAULT_INCLUDE_TOOLS)
        self.compact = compact
        self._session = None  # MCP session handle, opened lazily in connect()

    def connect(self) -> None:
        raise NotImplementedError(
            "ToolUniverse MCP session not wired — open a stdio session to "
            "`uvx tooluniverse` with include_tools=self.include_tools. See TODO(B5)."
        )

    def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """Invoke one ToolUniverse tool; return its raw JSON payload."""
        raise NotImplementedError(
            f"ToolUniverse.call({tool!r}) not wired — dispatch over MCP. See TODO(B5)."
        )
