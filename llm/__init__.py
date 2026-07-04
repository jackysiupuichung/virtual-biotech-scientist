"""Pluggable LLM backends for the virtual-biotech agents.

All three supported methods speak the OpenAI *chat/completions* wire protocol, so
a single client (:class:`OpenAIChatBackend`) serves all of them — they differ only
in base URL, model name, and (optionally) API key:

  1. **local**      — a tiny model for smoke-testing the pipeline (e.g. Ollama
                      ``qwen2.5:0.5b`` at http://localhost:11434/v1, no key).
  2. **llama**      — the university llama.cpp server (llama-server exposes an
                      OpenAI-compatible ``/v1`` endpoint).
  3. **qwen**       — Qwen via a hosted OpenAI-compatible API (needs a key).

Select one with ``get_backend("local"|"llama"|"qwen"|"auto")`` or via the
``VBIO_BACKEND`` env var. See ``.env.example`` for the knobs.
"""

from __future__ import annotations

from .backend import Backend, Message, OpenAIChatBackend, get_backend

__all__ = ["Backend", "Message", "OpenAIChatBackend", "get_backend"]
