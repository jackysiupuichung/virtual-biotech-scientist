"""MCP run_experiment interface + pluggable frontier-model backends (ARENA.md §5.1).

Importing this package registers all backends (Boltz-2 live; single-cell +
DNA/RNA-LM stubs) with ``interface._REGISTRY`` as a side effect, so callers that
only ``import vbs.experiments`` get a populated registry. Backends import lazily
(no scanpy/ToolUniverse at module load), so this stays cheap and dependency-free.
"""
from . import backends  # noqa: F401  (side effect: register the three backends)
from .interface import available, backend_for_axis, register, run_experiment  # noqa: F401
