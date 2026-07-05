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


# --------------------------------------------------------------------------- #
# Injectable ToolUniverse executor — the discovery loop's hands.
#
# The harness is plain Python and cannot call MCP tools. The *driving agent*
# (this Claude Code session, or the frontend) can. So it injects an executor:
#   set_tool_executor(fn)  where  fn(verb, payload) -> dict
# verbs: "find"    payload {description, limit}        -> {tools: [{name, description, parameter}]}
#        "compose" payload {tool_configs}              -> {graph: {nodes, edges}}
#        "run"     payload {tool_name, arguments}      -> the tool's raw result
# When no executor is set, the loop falls back to in-process (if the tooluniverse
# package is importable) or emits a descriptor for later execution. This keeps the
# module runnable standalone AND drivable by an agent, with one seam.
# --------------------------------------------------------------------------- #
_TOOL_EXECUTOR: "Any | None" = None


def set_tool_executor(fn: "Any | None") -> None:
    """Register the agent/frontend callback that executes ToolUniverse verbs."""
    global _TOOL_EXECUTOR
    _TOOL_EXECUTOR = fn


# Tool_Finder (embedding RAG) needs ML deps (torch/sentence_transformers) that the
# hosted MCP server may not have; Tool_Finder_Keyword needs none and returns the same
# {name, description, parameter} shape. Default to the keyword finder so discovery
# works on a stock server; an executor may prefer the embedding one when available.
DEFAULT_FINDER = "Tool_Finder_Keyword"


def find_descriptor(description: str, limit: int = 5,
                    finder: str = DEFAULT_FINDER) -> dict[str, Any]:
    """A `find` descriptor: discover tools for a sub-question via a ToolUniverse finder."""
    return {"verb": "find", "tool_name": finder,
            "arguments": {"description": description, "limit": limit}}


def compose_descriptor(tool_configs: list[dict[str, Any]]) -> dict[str, Any]:
    """A `compose` descriptor: order candidate tools by data-flow (ToolGraph)."""
    return {"verb": "compose", "tool_name": "ToolGraphGenerationPipeline",
            "arguments": {"tool_configs": tool_configs}}


def run_descriptor(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """A `run` descriptor: execute one concrete tool via execute_tool."""
    return {"verb": "run", "tool_name": tool_name, "arguments": arguments}


def _exec(verb: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Run a verb through the injected executor; None if none is registered."""
    if _TOOL_EXECUTOR is None:
        return None
    try:
        return _TOOL_EXECUTOR(verb, payload)
    except Exception as exc:  # pragma: no cover - executor is agent-supplied
        return {"status": "error", "reason": f"executor {verb} failed: {exc}"}


_TU_INSTANCE = None  # cached ToolUniverse (loading all 2599 tools is slow; do it once)

# COMPACT loading: only load the tool names the CSO actually calls, instead of all
# 2599. This is the standard practice — a restricted, purpose-built tool surface —
# and it makes in-process runs fast. The set is every `tool:` in tool_router.yaml
# plus the finders used by discovery. Override with VBIO_TU_FULL=1 to load everything
# (needed if discovery must reach tools outside the pinned set).
def _compact_tool_names(router: dict[str, Any] | None = None) -> list[str]:
    router = router if router is not None else load_tool_router()
    names = {e["tool"] for e in router.values()
             if isinstance(e, dict) and e.get("tool")}
    names.update({DEFAULT_FINDER, "Tool_Finder", "ToolGraphGenerationPipeline"})
    return sorted(names)


def _get_tooluniverse():
    """Lazily build + cache a loaded ToolUniverse; None if the package is absent.

    Loads a COMPACT tool set (only what the router + discovery call) unless
    VBIO_TU_FULL=1, so an in-process run doesn't pay for all 2599 tools.
    """
    global _TU_INSTANCE
    if _TU_INSTANCE is not None:
        return _TU_INSTANCE
    try:
        from tooluniverse import ToolUniverse  # type: ignore
    except Exception:
        return None
    import os
    tu = ToolUniverse()
    if os.environ.get("VBIO_TU_FULL") == "1":
        tu.load_tools()
    else:
        # restrict to the CSO's tool surface — fast, and the compact posture you want
        tu.load_tools(include_tools=_compact_tool_names(), quiet=True)
    _TU_INSTANCE = tu
    return tu


def _execute_in_process(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """Execute a ToolUniverse tool in-process if the package is importable.

    None when the package is absent (the caller keeps the descriptor for an agent
    to run). A ToolUniverse-side error is returned as an honest envelope, not raised.

    Uses the real ToolUniverse API (v1.3.1): ``tu.run({"name", "arguments"})``.
    """
    tu = _get_tooluniverse()
    if tu is None:
        return None
    try:
        result = tu.run({"name": tool_name, "arguments": arguments})
        # ToolUniverse returns {"status": "success"/"error", "data"/"error": ...}
        if isinstance(result, dict) and result.get("status") == "error":
            return {"status": "not executed",
                    "reason": f"tooluniverse: {result.get('error', 'tool error')}"}
        return {"status": "ok", "via": f"tooluniverse:{tool_name} (in-process)",
                "raw": result}
    except Exception as exc:  # pragma: no cover - depends on live TU runtime
        return {"status": "not executed",
                "reason": f"tooluniverse in-process error: {type(exc).__name__}: {exc}"}


def _count_where(raw: Any, list_path: str, field: str, value: str) -> int | None:
    """Count items in the list at ``list_path`` whose ``field`` equals ``value``.

    Supports summary specs the tool payload can't provide as a direct field — e.g.
    CellMarker returns a `records` list with a `cell_type` field, not pre-computed
    cancer/normal counts. None if the list is missing (honest, not a fake 0)."""
    items = _dig(raw, list_path)
    if not isinstance(items, list):
        return None
    return sum(1 for it in items if isinstance(it, dict) and it.get(field) == value)


def _summarize(raw: Any, summary_paths: list[str]) -> dict[str, Any]:
    """Lift a compact digest from a (large) tool payload for the evidence row.

    Each entry is either a dotted path (``data.disease.evidences.count``) or a derived
    count spec ``count:<list_path>:<field>=<value>`` (e.g.
    ``count:data.records:cell_type=Cancer cell``) — the digest key drops the ``count:``
    prefix so it reads cleanly in the report.
    """
    digest: dict[str, Any] = {}
    for path in summary_paths or []:
        if path.startswith("count:"):
            spec = path[len("count:"):]
            list_path, cond = spec.split(":", 1)
            field, value = cond.split("=", 1)
            digest[f"{value.lower()} count"] = _count_where(raw, list_path, field, value)
        else:
            digest[path] = _dig(raw, path)
    return digest


def _run_tool(tool_name: str, arguments: dict[str, Any],
              summary_paths: list[str]) -> dict[str, Any]:
    """Execute one concrete tool, best backend available, → an evidence envelope.

    Order: injected agent executor (`run` verb) → in-process package → descriptor.
    """
    envelope: dict[str, Any] = {
        "tool_call": {"tool_name": tool_name, "arguments": arguments},
    }
    # 1) agent/frontend executor
    ran = _exec("run", run_descriptor(tool_name, arguments))
    if ran is not None and ran.get("status") != "error":
        raw = ran.get("raw", ran)
        envelope["summary"] = _summarize(raw, summary_paths)
        # carry a human note (fixtures / annotated payloads use `_note`) for the report
        if isinstance(raw, dict) and raw.get("_note"):
            envelope["_note"] = raw["_note"]
        envelope["via"] = f"tooluniverse:{tool_name} (agent)"
        envelope["source"] = "tooluniverse"
        return envelope
    # 2) in-process package
    executed = _execute_in_process(tool_name, arguments)
    if executed is not None and executed.get("status") == "ok":
        envelope["summary"] = _summarize(executed.get("raw"), summary_paths)
        envelope["via"] = executed["via"]
        envelope["source"] = "tooluniverse"
        return envelope
    if executed is not None:  # importable but errored — surface honestly
        envelope.update(executed)
        envelope["source"] = "unavailable"
        return envelope
    # 3) no executor, no package → descriptor for later execution
    envelope["status"] = "deferred"
    envelope["reason"] = ("no ToolUniverse executor registered and package not importable; "
                          "execute this tool_call via the MCP ToolUniverse server.")
    envelope["source"] = "tool-descriptor"
    return envelope


def run_predefined_tool(skill: str, query: str,
                        router: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Answer a routed step via its pinned tool_router.yaml tool. None if unmapped."""
    call = build_call(skill, query, router)
    if call is None:
        return None
    env = _run_tool(call["tool_name"], call["arguments"], call["summary_paths"])
    env["backend"] = call["backend"]
    return env


def discover_and_run(question: str, query: str, *, limit: int = 5) -> dict[str, Any]:
    """Dynamic discovery for an axis with NO pinned mapping (the custom-experiment path).

    find → compose → run:
      1. Tool_Finder(question)                → ranked candidate tools
      2. ToolGraphGenerationPipeline(top-k)   → data-flow order (best-effort)
      3. execute_tool on the ordered chain    → evidence

    Requires the injected agent executor for the live path (find/compose need
    Tool_Finder's ML model). Without an executor it emits a `find` descriptor for
    the driving agent to run — the honest deferred state, never a fabrication.
    """
    found = _exec("find", find_descriptor(question, limit))
    if found is None:
        # no executor → hand the discovery step to the agent/frontend
        return {"status": "deferred", "source": "tool-descriptor",
                "discover": find_descriptor(question, limit),
                "reason": "register a ToolUniverse executor (agent/frontend) to run Tool_Finder."}
    tools = found.get("tools") or found.get("raw") or []
    if not tools:
        return {"status": "not executed", "source": "unavailable",
                "reason": f"Tool_Finder found no tool for: {question!r}"}
    # order the candidates by data-flow when there's more than one (best-effort)
    ordered = tools
    if len(tools) > 1:
        composed = _exec("compose", compose_descriptor(tools))
        node_order = _dig(composed or {}, "graph.nodes")
        if isinstance(node_order, list) and node_order:
            by_name = {t.get("name"): t for t in tools}
            ordered = [by_name[n["name"]] for n in node_order
                       if isinstance(n, dict) and n.get("name") in by_name] or tools
    # Pick the first ordered candidate whose REQUIRED args we can fill from the parsed
    # query context; else fall back to the top. Prevents choosing a tool that needs an
    # arg we can't supply (e.g. an experiment accession) over one that takes gene_symbol.
    ctx = parse_query(query)
    fillable = {k: v for k, v in ctx.items() if v}

    def _args_for(tool: dict[str, Any]) -> dict[str, Any] | None:
        props = (tool.get("parameter") or {}).get("properties", {})
        required = set((tool.get("parameter") or {}).get("required", []))
        args: dict[str, Any] = {}
        for slot in props:
            # map a tool's arg name to our context by exact or aliased key
            for key in (slot, "gene_symbol" if slot == "gene" else slot):
                if key in fillable:
                    args[slot] = fillable[key]
                    break
            else:
                # some tools want gene_symbol; fill from either gene or gene_symbol
                if slot in ("gene_symbol", "gene") and (fillable.get("gene_symbol") or fillable.get("gene")):
                    args[slot] = fillable.get("gene_symbol") or fillable.get("gene")
        # satisfiable only if every REQUIRED slot got a value
        return args if required.issubset(args.keys()) else None

    chosen, args = None, {}
    for cand in ordered:
        maybe = _args_for(cand)
        if maybe is not None:
            chosen, args = cand, maybe
            break
    if chosen is None:  # none fully satisfiable → best-effort on the top candidate
        chosen = ordered[0]
        args = _args_for(chosen) or {}

    env = _run_tool(chosen["name"], args, [])
    env["discovered"] = chosen["name"]
    env["candidates"] = [t.get("name") for t in ordered[:limit]]
    return env
