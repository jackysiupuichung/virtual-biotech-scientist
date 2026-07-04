"""OpenAI-compatible chat backend + the three-method registry.

One transport, three configs. Every supported method (local tiny model, the
university llama.cpp server, hosted Qwen) exposes the same
``POST {base_url}/chat/completions`` endpoint, so we only need a single client.

Design notes
------------
- Uses ``httpx`` (already a transitive dep) rather than the ``openai`` SDK, to
  keep the dependency surface small and the request shape explicit.
- Config comes from env vars (see ``.env.example``); nothing is hard-coded so the
  same code runs against a laptop, a campus GPU box, or a cloud API.
- ``chat()`` is synchronous and returns the assistant text. Tool-calling and
  streaming are deliberately out of scope for this first cut.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal, Sequence, TypedDict

import httpx

Role = Literal["system", "user", "assistant"]


class Message(TypedDict):
    role: Role
    content: str


Method = Literal["local", "llama", "qwen"]


@dataclass
class Backend:
    """Resolved configuration for one LLM method."""

    method: Method
    base_url: str
    model: str
    api_key: str | None = None
    # Defaults kept conservative so a 0.5B model doesn't ramble.
    temperature: float = 0.2
    timeout: float = 120.0

    def client(self) -> "OpenAIChatBackend":
        return OpenAIChatBackend(self)


class OpenAIChatBackend:
    """Minimal OpenAI-compatible chat/completions client."""

    def __init__(self, cfg: Backend) -> None:
        self.cfg = cfg
        self._url = cfg.base_url.rstrip("/") + "/chat/completions"

    def chat(
        self,
        messages: Sequence[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Send a chat request and return the assistant's text."""
        payload: dict = {
            "model": self.cfg.model,
            "messages": list(messages),
            "temperature": self.cfg.temperature if temperature is None else temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {"Content-Type": "application/json"}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"

        resp = httpx.post(
            self._url, json=payload, headers=headers, timeout=self.cfg.timeout
        )
        resp.raise_for_status()
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:  # surface a bad/unexpected response
            raise RuntimeError(
                f"{self.cfg.method} backend returned no completion: {data!r}"
            ) from exc


# --- registry -----------------------------------------------------------------
#
# Each method reads its own env vars, all with sane defaults so `local` works out
# of the box against Ollama and the others only need a URL (+ key for qwen).

_DEFAULTS = {
    "local": {
        # llama_cpp.server started by scripts/serve_local.py (OpenAI-compat).
        "base_url": "http://localhost:8080/v1",
        "model": "local",  # model_alias set in serve_local.py
        "key_env": None,
    },
    "llama": {
        "base_url": "http://localhost:8080/v1",  # llama.cpp llama-server default
        "model": "llama",  # llama-server ignores/echoes the name; set to taste
        "key_env": "LLAMA_API_KEY",  # usually unset for a campus server
    },
    "qwen": {
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "key_env": "QWEN_API_KEY",
    },
}


def _env(method: Method, suffix: str) -> str | None:
    """Look up e.g. VBIO_LLAMA_BASE_URL, falling back to None."""
    return os.getenv(f"VBIO_{method.upper()}_{suffix}")


def get_backend(method: str = "auto") -> Backend:
    """Resolve a :class:`Backend` for ``method``.

    ``"auto"`` reads ``VBIO_BACKEND`` (default ``"local"``) so scripts can stay
    method-agnostic and be switched from the environment.
    """
    if method == "auto":
        method = os.getenv("VBIO_BACKEND", "local")
    if method not in _DEFAULTS:
        raise ValueError(
            f"unknown backend {method!r}; choose from {sorted(_DEFAULTS)} or 'auto'"
        )

    d = _DEFAULTS[method]
    base_url = _env(method, "BASE_URL") or d["base_url"]
    model = _env(method, "MODEL") or d["model"]
    api_key = os.getenv(d["key_env"]) if d["key_env"] else None

    return Backend(method=method, base_url=base_url, model=model, api_key=api_key)
