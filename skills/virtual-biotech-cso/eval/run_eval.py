#!/usr/bin/env python
"""Evaluation ground: run the CSO over a captured-fixture target, offline, for review.

We are not doing live ToolUniverse runs. Instead this replays real tool outputs
captured into a fixture JSON (e.g. eval/pmel_melanoma.json) by registering a
`set_tool_executor` callback that serves fixture data instead of calling MCP. The
harness runs with the `stub` backend (no LLM — reasoning roles degrade to honest
stubs) but `live=True`, so the routed axes execute through the tool backend and get
REAL data folded in. Output artifacts land in an out dir for review:

    report.md      — the human-facing target-assessment dossier
    result.json    — the machine envelope (briefing, plan, evidence, review, synthesis)
    trace.jsonl    — the agent execution graph (which role/tool ran, in what order)

Usage:
    uv run python skills/virtual-biotech-cso/eval/run_eval.py \
        --fixture skills/virtual-biotech-cso/eval/pmel_melanoma.json \
        --output skills/virtual-biotech-cso/eval/out
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR))

import harness  # noqa: E402
import tool_backend  # noqa: E402


def _sig(tool_name: str, arguments: dict) -> list[str]:
    """Candidate fixture keys for a (tool, args) call, most-specific first.

    Fixture keys look like 'ToolName:GENE:disease' or 'ToolName:GENE' — we match on
    the tool name plus whatever identifying args the call carries (gene / drug /
    disease), so one fixture serves both the pinned and the discovered call shapes.
    """
    gene = (arguments.get("gene_symbol") or arguments.get("gene")
            or arguments.get("intervention") or arguments.get("drug") or "")
    disease = (arguments.get("disease") or arguments.get("disease_name")
               or arguments.get("condition") or "")
    keys = []
    if gene and disease:
        keys.append(f"{tool_name}:{gene}:{disease}")
    if gene:
        keys.append(f"{tool_name}:{gene}")
    keys.append(tool_name)  # bare tool-name fallback
    return keys


def make_replay_executor(fixture: dict):
    """Build a set_tool_executor callback that serves the fixture's tool outputs."""
    tools = fixture.get("tools", {})

    def executor(verb: str, payload: dict):
        if verb == "run":
            name = payload["tool_name"]
            args = payload.get("arguments", {})
            for key in _sig(name, args):
                if key in tools:
                    return {"raw": tools[key]}
            # no fixture for this call — honest miss (the CSO marks it unavailable)
            return {"status": "error", "reason": f"no fixture for {name} / {args}"}
        if verb == "find":
            # discovery isn't exercised here (all eval axes are pinned); return empty
            return {"tools": []}
        if verb == "compose":
            return {"graph": {"nodes": []}}
        return {"status": "error", "reason": f"unknown verb {verb}"}

    return executor


def make_review_gate(fixture: dict):
    """Build a harness `gate` that drives the review→re-route loop from the fixture.

    Without an LLM the stub reviewer always votes 'synthesize', so the loop never
    fires. The fixture's `review.force_reroute_pass_0` says: on the first pass force a
    re-route to a named skill to fill a real gap, then approve every later pass so the
    loop converges after one added step. Returns None if the fixture declares no
    review directive (loop stays inert, as before).
    """
    directive = (fixture.get("review") or {}).get("force_reroute_pass_0")
    if not directive:
        return None

    def gate(checkpoint: dict):
        if checkpoint.get("iteration", 0) == 0:
            return {"action": "override_verdict", "verdict": "re-route",
                    "route_to": directive["route_to"],
                    "missing": directive.get("missing", ""),
                    "why": directive.get("why", "")}
        return {"action": "approve"}  # converge on subsequent passes

    return gate


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fixture", required=True, type=str)
    p.add_argument("--output", required=True, type=str)
    args = p.parse_args(argv)

    fixture = json.loads(Path(args.fixture).read_text())
    query = fixture["query"]
    out_dir = Path(args.output)

    tool_backend.set_tool_executor(make_replay_executor(fixture))
    try:
        result = harness.run(query, out_dir, backend="stub", model=None,
                             live=True, argv=["eval"], quiet=False,
                             gate=make_review_gate(fixture))
    finally:
        tool_backend.set_tool_executor(None)

    print(json.dumps(result.get("summary", result), indent=2))
    print(f"\nArtifacts in {out_dir}/:")
    for name in ("report.md", "result.json", "trace.jsonl"):
        f = out_dir / name
        print(f"  {'✓' if f.exists() else '✗'} {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
