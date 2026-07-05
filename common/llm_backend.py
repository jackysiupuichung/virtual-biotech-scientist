"""Single source of truth for LLM backend selection.

Both the virtual-biotech-cso harness (sync, ``skills/virtual-biotech-cso/runners.py``)
and the arena Pareto agent (async, ``arena/pareto_agent/llm_client.py``) historically
duplicated an identical selection ladder over the same env-var conventions. This
module extracts ONLY the pure *decision* — which backend to use and which model —
so there is one place to configure or fix backend selection. It deliberately does
NOT do any calling: each client keeps its own sync/async Runner/Backend classes and
maps the returned name to its own implementation.

The ladder (shared by both clients):
  explicit backend (not "auto") -> ANTHROPIC_API_KEY -> OPENAI_API_KEY
  -> GEMINI_API_KEY/GOOGLE_API_KEY -> `claude` CLI on PATH -> stub.

Pure: no SDK imports, no I/O beyond ``os.environ`` and ``shutil.which``.
"""
from __future__ import annotations

import os
import shutil


def resolve_backend(explicit: str | None = None) -> tuple[str, str | None]:
    """Resolve which backend to use and which model, from env + optional override.

    Returns ``(backend_name, model)`` where ``backend_name`` is one of
    ``{"anthropic", "openai", "gemini", "claude-cli", "stub"}`` and ``model`` is
    ``os.environ.get("VBIO_MODEL")`` or ``None``. ``explicit`` (when given and not
    ``"auto"``) is returned verbatim as the backend name, letting callers force a
    provider; otherwise the shared key/PATH ladder decides.
    """
    model = os.environ.get("VBIO_MODEL") or None
    if explicit and explicit.lower() != "auto":
        return explicit.lower(), model
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic", model
    if os.environ.get("OPENAI_API_KEY"):
        return "openai", model
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini", model
    if shutil.which("claude"):
        return "claude-cli", model
    return "stub", model
