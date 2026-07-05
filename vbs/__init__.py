"""Virtual Biotech Scientist — an agentic system over ToolUniverse that ranks
competing therapeutic hypotheses in a prioritisation arena.

Layout:
  vbs.runners     — multi-backend LLM runner (migrated A2)
  vbs.tracing     — trace.jsonl + optional Langfuse (migrated A3)
  vbs.cso         — CSO orchestrator + Scientific Reviewer loop (migrated A1/A4)
  vbs.divisions   — scientist-division evidence producers
  vbs.arena       — hypothesis cards, Pareto, tournament, scheduler, mutation (new B1/B2/B6)
  vbs.voi         — Value-of-Information budgeted selector (A5 skeleton → B3)
  vbs.experiments — MCP run_experiment interface + pluggable backends (new B4)
  vbs.tooluniverse— ToolUniverse MCP client + card adapter (new B5)
  vbs.toolkit     — self-composing toolkit (new B7)
"""
__version__ = "0.1.0"
