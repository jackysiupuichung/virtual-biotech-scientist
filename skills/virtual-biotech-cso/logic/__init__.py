"""Symbolic logic layer for the CSO: a stratified Datalog engine that grounds both
the discovery loop (structural gaps, safety hard-gate) and the report (grade
downgrades/rejections) from one shared fact base, as a non-silenceable floor under
the LLM. See ``README.md`` for the fact contract and rule set."""

from .engine import LogicEngine, PyDatalogEngine, default_engine
from .facts import Fact, derive_edb, f

__all__ = [
    "LogicEngine",
    "PyDatalogEngine",
    "default_engine",
    "Fact",
    "derive_edb",
    "f",
]
