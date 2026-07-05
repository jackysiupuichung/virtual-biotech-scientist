"""Predefined-tool backend for the CSO — ToolUniverse first, then clawbio.

This is the backend the CSO tries *first* for a routed step (ahead of the old
in-repo skills). It resolves a routing.yaml ``skill`` name to a concrete tool via
``tool_router.yaml`` and produces an evidence envelope in one of two ways:

  1. **Descriptor** (always): a ``{tool_name, arguments}`` dict an agent (Claude
     Code) or the frontend can execute via ``mcp__tooluniverse__execute_tool``.
     This keeps the CSO runnable when it is *driven by an agent* — the natural
     mode for the MCP ToolUniverse server, which a standalone process can't reach.

  2. **In-process** (when available): if the ``tooluniverse`` Python package is
     importable, execute the tool directly and fold a compact summary into the
     envelope — so a standalone ``--tools`` run still gets real data with no agent.

No LLM is involved. Any failure returns an honest envelope, never a fabrication.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

SKILL_DIR = Path(__file__).resolve().parent
TOOL_ROUTER_PATH = SKILL_DIR / "tool_router.yaml"


def load_tool_router(path: Path = TOOL_ROUTER_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# A gene/target symbol: 2-7 uppercase alnum, optional hyphen block (B7-H3, CD276,
# KRAS, HER2). We also map a few well-known aliases to their HGNC symbol so the
# API tools (which key on HGNC) resolve — e.g. B7-H3 → CD276.
_ALIAS_TO_HGNC = {
    "B7-H3": "CD276", "B7H3": "CD276", "PD-L1": "CD274", "PD1": "PDCD1",
    "HER2": "ERBB2", "HER-2": "ERBB2",
}
_GENE_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,6}(?:-[A-Z0-9]+)?)\b")


def parse_query(query: str) -> dict[str, str]:
    """Extract {gene, gene_symbol, disease, drug} from a '<gene> in <disease>' query.

    Best-effort and deterministic. ``gene`` is the raw symbol as written; ``gene_symbol``
    is the HGNC-resolved form for the API tools. ``disease`` is the text after 'in'.
    ``drug`` defaults to the gene symbol (many FAERS/label lookups accept the target
    name); the agent/frontend can override it with a known marketed drug.
    """
    q = query or ""
    m = _GENE_RE.search(q)
    raw_gene = m.group(1) if m else ""
    hgnc = _ALIAS_TO_HGNC.get(raw_gene, raw_gene)
    # disease = phrase after the last ' in ' (…'as a target in lung cancer')
    disease = ""
    parts = re.split(r"\bin\b", q, flags=re.IGNORECASE)
    if len(parts) > 1:
        disease = parts[-1].strip(" .").strip()
    return {
        "gene": raw_gene, "gene_symbol": hgnc,
        "disease": disease, "drug": raw_gene,
    }


def _fill(template: Any, ctx: dict[str, str]) -> Any:
    """Recursively substitute {gene}/{disease}/… placeholders in an arg template."""
    if isinstance(template, str):
        out = template
        for key, val in ctx.items():
            out = out.replace("{" + key + "}", val)
        return out
    if isinstance(template, list):
        return [_fill(v, ctx) for v in template]
    if isinstance(template, dict):
        return {k: _fill(v, ctx) for k, v in template.items()}
    return template


def _dig(payload: Any, dotted: str) -> Any:
    """Follow a dotted path into nested dicts/lists; None if any hop is missing."""
    cur = payload
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit():
            idx = int(part)
            cur = cur[idx] if idx < len(cur) else None
        else:
            return None
        if cur is None:
            return None
    return cur


def build_call(skill: str, query: str,
               router: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Resolve a routed ``skill`` → a concrete predefined-tool descriptor.

    Returns ``{backend, tool_name, arguments, summary_paths}`` or None if this skill
    has no predefined-tool mapping (caller then falls through to the old backends).
    """
    router = router if router is not None else load_tool_router()
    entry = router.get(skill)
    if not isinstance(entry, dict) or "tool" not in entry:
        return None
    ctx = parse_query(query)
    return {
        "backend": entry.get("backend", "tooluniverse"),
        "tool_name": entry["tool"],
        "arguments": _fill(entry.get("args", {}), ctx),
        "summary_paths": entry.get("summary", []),
    }


def _execute_in_process(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """Execute a ToolUniverse tool in-process if the package is importable.

    None when the package is absent (the caller keeps the descriptor for an agent
    to run). A ToolUniverse-side error is returned as an honest envelope, not raised.
    """
    try:
        from tooluniverse import ToolUniverse  # type: ignore
    except Exception:
        return None
    try:
        tu = ToolUniverse()
        tu.load_tools()
        result = tu.run_one_tool(tool_name, arguments)
        return {"status": "ok", "via": f"tooluniverse:{tool_name} (in-process)",
                "raw": result}
    except Exception as exc:  # pragma: no cover - depends on live TU runtime
        return {"status": "not executed",
                "reason": f"tooluniverse in-process error: {type(exc).__name__}: {exc}"}


def _summarize(raw: Any, summary_paths: list[str]) -> dict[str, Any]:
    """Lift a compact digest from a (large) tool payload for the evidence row."""
    digest: dict[str, Any] = {}
    for path in summary_paths or []:
        digest[path] = _dig(raw, path)
    return digest


def run_predefined_tool(skill: str, query: str,
                        router: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Try to answer a routed step with a predefined ToolUniverse/clawbio tool.

    Resolution:
      * no mapping for this skill        → return None (fall through to old backends)
      * mapping + package importable     → execute in-process, return {status:ok, ...}
      * mapping + no package             → return a descriptor envelope for an agent
                                           / the frontend to execute, status 'deferred'
    """
    call = build_call(skill, query, router)
    if call is None:
        return None
    envelope: dict[str, Any] = {
        "tool_call": {"tool_name": call["tool_name"], "arguments": call["arguments"]},
        "backend": call["backend"],
    }
    executed = _execute_in_process(call["tool_name"], call["arguments"])
    if executed is not None and executed.get("status") == "ok":
        envelope.update(executed)
        envelope["summary"] = _summarize(executed.get("raw"), call["summary_paths"])
        # keep the row light: drop the raw payload once summarized
        envelope.pop("raw", None)
        envelope["source"] = "tooluniverse"
        return envelope
    if executed is not None:  # importable but errored — surface honestly
        envelope.update(executed)
        envelope["source"] = "unavailable"
        return envelope
    # package absent → hand the descriptor to the driving agent / frontend
    envelope["status"] = "deferred"
    envelope["reason"] = ("tooluniverse package not importable in-process; execute this "
                          "tool_call via the MCP ToolUniverse server (agent/frontend).")
    envelope["source"] = "tool-descriptor"
    return envelope
