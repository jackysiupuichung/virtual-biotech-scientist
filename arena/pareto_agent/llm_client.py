"""Provider-agnostic async LLM-JSON client.

Backend selection mirrors the order documented in `.env.example`:
ANTHROPIC_API_KEY -> OPENAI_API_KEY -> GEMINI_API_KEY/GOOGLE_API_KEY -> Claude Code
CLI (no key needed). Swap providers by setting env vars; no code changes required.
Provider SDKs are imported lazily so this module has no hard dependency on any of them.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from typing import Optional, Protocol, Type, TypeVar

from pydantic import BaseModel, ValidationError

try:
    from common.llm_backend import resolve_backend
except ImportError:  # ensure repo root is importable
    _REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    from common.llm_backend import resolve_backend

ModelT = TypeVar("ModelT", bound=BaseModel)


class LLMJSONError(RuntimeError):
    """Raised when an LLM call fails to produce schema-valid JSON after retries."""


class LLMBackend(Protocol):
    async def complete(self, prompt: str) -> str: ...


def _extract_json(text: str) -> str:
    """Pull a JSON object out of a possibly markdown-fenced / prose-wrapped completion."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


class AnthropicBackend:
    def __init__(self, model: Optional[str] = None):
        import anthropic  # optional dependency, imported lazily

        self._client = anthropic.AsyncAnthropic()
        self._model = model or os.environ.get("VBIO_MODEL") or "claude-sonnet-4-5"

    async def complete(self, prompt: str) -> str:
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in resp.content if block.type == "text")


class OpenAIBackend:
    def __init__(self, model: Optional[str] = None):
        import openai  # optional dependency, imported lazily

        self._client = openai.AsyncOpenAI(
            base_url=os.environ.get("OPENAI_BASE_URL") or None,
        )
        self._model = model or os.environ.get("VBIO_MODEL") or "gpt-4o-mini"

    async def complete(self, prompt: str) -> str:
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""


class GeminiBackend:
    def __init__(self, model: Optional[str] = None):
        import google.generativeai as genai  # optional dependency, imported lazily

        genai.configure(
            api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        )
        self._model = genai.GenerativeModel(
            model or os.environ.get("VBIO_MODEL") or "gemini-1.5-pro"
        )

    async def complete(self, prompt: str) -> str:
        resp = await self._model.generate_content_async(prompt)
        return resp.text


class ClaudeCLIBackend:
    """No-key fallback: shells out to the local `claude` CLI in headless print mode."""

    async def complete(self, prompt: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise LLMJSONError(f"claude CLI failed: {stderr.decode(errors='replace')}")
        return stdout.decode(errors="replace")


def select_backend() -> LLMBackend:
    # Delegate the selection *decision* to the shared single-source ladder; map the
    # resolved name to this module's async Backend classes. The arena has no stub,
    # so "stub" (no key + no CLI) maps to ClaudeCLIBackend, preserving the prior
    # no-key fallback behavior.
    name, _model = resolve_backend()
    return {
        "anthropic": AnthropicBackend,
        "openai": OpenAIBackend,
        "gemini": GeminiBackend,
        "claude-cli": ClaudeCLIBackend,
        "stub": ClaudeCLIBackend,
    }[name]()


_backend: Optional[LLMBackend] = None


def get_backend() -> LLMBackend:
    global _backend
    if _backend is None:
        _backend = select_backend()
    return _backend


def reset_backend() -> None:
    """Force the next get_backend() call to re-select (mainly for tests)."""
    global _backend
    _backend = None


async def call_llm_json(
    prompt: str, response_model: Type[ModelT], *, max_retries: int = 2
) -> ModelT:
    """Call the active backend and validate its output against response_model.

    Retries with a stricter follow-up instruction on invalid JSON / schema
    mismatch, then raises LLMJSONError. Never raises on a clean transport call
    that simply returns malformed text -- that is what retries are for.
    """
    backend = get_backend()
    last_error: Optional[Exception] = None
    current_prompt = prompt

    for _ in range(max_retries + 1):
        try:
            raw = await backend.complete(current_prompt)
            data = json.loads(_extract_json(raw))
            return response_model.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            current_prompt = (
                prompt
                + "\n\nYour previous response was not valid JSON matching the required "
                + "schema. Return ONLY the JSON object: no prose, no markdown fences, "
                + "no explanation."
            )
        except Exception as exc:  # backend/transport failure
            last_error = exc

    raise LLMJSONError(
        f"LLM call failed after {max_retries + 1} attempts: {last_error}"
    ) from last_error
