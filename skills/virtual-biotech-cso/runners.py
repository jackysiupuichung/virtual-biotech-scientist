#!/usr/bin/env python
"""runners.py — a pluggable agent runner for the virtual-biotech-cso harness.

The CSO skill (``cso.py``) makes no LLM call: it packages three reasoning roles
(Chief of Staff, Scientific Reviewer, CSO synthesis) as delegation stubs. This
module supplies the *driving agent* those stubs assume — but deliberately NOT
tied to any one vendor or to Claude Code being installed. A single entry point,
``run_agent(prompt, context, schema)``, is backed by an auto-selected provider:

  - ``AnthropicRunner`` — the ``anthropic`` SDK + ``ANTHROPIC_API_KEY`` (primary).
  - ``OpenAIRunner``    — an OpenAI-compatible client (``OPENAI_API_KEY``,
                          optional ``OPENAI_BASE_URL``) using JSON mode, so the
                          harness runs from Cursor or any other environment.
  - ``GeminiRunner``    — Google Gemini via its OpenAI-compatible endpoint
                          (``GEMINI_API_KEY``), reusing the ``openai`` SDK.

If no backend is configured, ``select_runner`` returns a ``StubRunner`` that
raises ``NoBackendError`` — the harness catches it and falls back to cso.py's
honest delegation stub rather than fabricating a result.

JSON contract: every role returns a JSON object matching the ``schema`` passed
in (the shape is harvested from the role's prompt file). Runners instruct the
model to return JSON only, parse it, and on a parse failure retry once before
giving up (the harness then stubs that role).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any, Protocol


def load_dotenv(start: str | None = None) -> None:
    """Populate os.environ from the nearest ``.env`` (zero-dependency).

    Walks up from ``start`` (this file's dir by default) to the filesystem root,
    loading the first ``.env`` found. Existing env vars win — an exported key is
    never overwritten by the file — so CI / shell overrides still take precedence.
    Lines are ``KEY=value`` (``#`` comments and blanks ignored); surrounding
    quotes are stripped. Best-effort: any read error is swallowed so a missing or
    malformed ``.env`` never breaks import. Called once at module import.
    """
    here = os.path.abspath(start or os.path.dirname(__file__))
    while True:
        candidate = os.path.join(here, ".env")
        if os.path.isfile(candidate):
            try:
                for line in open(candidate, encoding="utf-8"):
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key, val = key.strip(), val.strip().strip('"').strip("'")
                    if val and not os.environ.get(key):
                        os.environ[key] = val
            except OSError:
                pass
            return
        parent = os.path.dirname(here)
        if parent == here:
            return
        here = parent


load_dotenv()


class NoBackendError(RuntimeError):
    """Raised when no agent backend is configured (no API key present)."""


class AgentError(RuntimeError):
    """Raised when a configured backend fails to return usable JSON."""


def _extract_json(text: str) -> dict[str, Any]:
    """Parse the first JSON object out of a model response.

    Tolerates ```json fenced blocks and leading/trailing prose. Raises
    ``AgentError`` if no object can be parsed.
    """
    if not text or not text.strip():
        raise AgentError("empty response")
    # Strip a ```json … ``` fence if present.
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = fence.group(1).strip() if fence else text.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    # Fall back to the first balanced {...} span.
    start = candidate.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(candidate)):
            ch = candidate[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(candidate[start : i + 1])
                    except json.JSONDecodeError:
                        break
    raise AgentError("no JSON object found in response")


def _compose(prompt: str, context: str, schema: dict[str, Any]) -> str:
    """Build the user message: role prompt + injected context + strict-JSON ask."""
    return (
        f"{prompt}\n\n"
        f"## Context for this run\n{context}\n\n"
        "## Output requirement\n"
        "Return ONLY a single valid JSON object — no prose, no markdown fence — "
        "matching exactly this schema (keys and value types):\n"
        f"{json.dumps(schema, indent=2)}\n"
    )


SYSTEM = (
    "You are a division agent inside a virtual-biotech multi-agent system. "
    "You return rigorous, evidence-grounded JSON and never fabricate data. "
    "If evidence is absent, say so in the JSON rather than inventing it."
)


class Runner(Protocol):
    name: str
    model: str
    # Token usage from the most recent ``run`` call, for the trace recorder:
    # {"input_tokens": int, "output_tokens": int}. Empty when the backend does
    # not report usage (OpenAI without usage, the CLI envelope, or the stub).
    last_usage: dict[str, int]

    def run(self, prompt: str, context: str, schema: dict[str, Any]) -> dict[str, Any]: ...


class AnthropicRunner:
    """Primary backend — Anthropic Messages API. Portable to any environment."""

    DEFAULT_MODEL = "claude-sonnet-4-6"

    def __init__(self, model: str | None = None) -> None:
        import anthropic  # imported lazily so the dep is optional

        self.name = "anthropic"
        self.model = model or os.environ.get("VBIO_MODEL") or self.DEFAULT_MODEL
        self.last_usage: dict[str, int] = {}
        self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

    def run(self, prompt: str, context: str, schema: dict[str, Any]) -> dict[str, Any]:
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=SYSTEM,
            messages=[{"role": "user", "content": _compose(prompt, context, schema)}],
        )
        usage = getattr(msg, "usage", None)
        self.last_usage = {
            "input_tokens": getattr(usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        } if usage else {}
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        return _extract_json(text)


class OpenAIRunner:
    """OpenAI-compatible backend — for Cursor users / other keys. JSON mode."""

    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(self, model: str | None = None) -> None:
        from openai import OpenAI  # lazy optional dep

        self.name = "openai"
        self.model = model or os.environ.get("VBIO_MODEL") or self.DEFAULT_MODEL
        self.last_usage: dict[str, int] = {}
        # base_url honours OPENAI_BASE_URL for OpenAI-compatible gateways.
        base_url = os.environ.get("OPENAI_BASE_URL")
        self._client = OpenAI(base_url=base_url) if base_url else OpenAI()

    def run(self, prompt: str, context: str, schema: dict[str, Any]) -> dict[str, Any]:
        resp = self._client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": _compose(prompt, context, schema)},
            ],
        )
        usage = getattr(resp, "usage", None)
        self.last_usage = {
            "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
        } if usage else {}
        return _extract_json(resp.choices[0].message.content or "")


class GeminiRunner:
    """Google Gemini backend via its OpenAI-compatible endpoint.

    Gemini exposes an OpenAI-shaped API, so we reuse the ``openai`` SDK pointed at
    Google's compat base_url and authenticated with ``GEMINI_API_KEY`` (Google AI
    Studio's free tier). No extra dependency beyond ``openai``. JSON mode keeps the
    role's structured-output contract.
    """

    DEFAULT_MODEL = "gemini-2.5-flash"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

    def __init__(self, model: str | None = None) -> None:
        from openai import OpenAI  # lazy optional dep (shared with OpenAIRunner)

        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise NoBackendError("set GEMINI_API_KEY to use the Gemini backend")
        self.name = "gemini"
        self.model = model or os.environ.get("VBIO_MODEL") or self.DEFAULT_MODEL
        self.last_usage: dict[str, int] = {}
        self._client = OpenAI(api_key=key, base_url=self.BASE_URL)

    def run(self, prompt: str, context: str, schema: dict[str, Any]) -> dict[str, Any]:
        resp = self._client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": _compose(prompt, context, schema)},
            ],
        )
        usage = getattr(resp, "usage", None)
        self.last_usage = {
            "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
        } if usage else {}
        return _extract_json(resp.choices[0].message.content or "")


class ClaudeCLIRunner:
    """Claude Code CLI backend — reuses local Claude Code auth, no API key.

    Shells out to ``claude -p <message> --output-format json``. Useful on a
    machine where Claude Code is installed/authenticated (e.g. the hackathon
    laptop) so the live loop runs without exporting an API key. Not portable to
    environments lacking the ``claude`` binary — which is why it sits behind the
    SDK backends in ``select_runner``'s auto order.
    """

    DEFAULT_MODEL = "sonnet"

    def __init__(self, model: str | None = None, *, bin_path: str | None = None) -> None:
        self.name = "claude-cli"
        self.model = model or os.environ.get("VBIO_MODEL") or self.DEFAULT_MODEL
        self.last_usage: dict[str, int] = {}
        self._bin = bin_path or shutil.which("claude")
        if not self._bin:
            raise NoBackendError("claude CLI not found on PATH")

    def run(self, prompt: str, context: str, schema: dict[str, Any]) -> dict[str, Any]:
        message = f"{SYSTEM}\n\n{_compose(prompt, context, schema)}"
        proc = subprocess.run(
            [self._bin, "-p", message, "--output-format", "json", "--model", self.model],
            capture_output=True, text=True, timeout=180,
        )
        if proc.returncode != 0:
            raise AgentError(f"claude CLI exited {proc.returncode}: {proc.stderr.strip()[:300]}")
        # --output-format json wraps the reply in an envelope: {"result": "...", ...}.
        # Fall back to the raw stdout if the envelope shape is unexpected.
        text = proc.stdout
        self.last_usage = {}
        try:
            envelope = json.loads(proc.stdout)
            if isinstance(envelope, dict) and "result" in envelope:
                text = envelope["result"]
            # The CLI json envelope reports usage under "usage" (Anthropic shape).
            usage = envelope.get("usage") if isinstance(envelope, dict) else None
            if isinstance(usage, dict):
                self.last_usage = {
                    "input_tokens": int(usage.get("input_tokens", 0) or 0),
                    "output_tokens": int(usage.get("output_tokens", 0) or 0),
                }
        except json.JSONDecodeError:
            pass
        return _extract_json(text)


class StubRunner:
    """No backend configured — every call raises so the harness stubs the role."""

    name = "stub"
    model = "none"
    last_usage: dict[str, int] = {}

    def run(self, prompt: str, context: str, schema: dict[str, Any]) -> dict[str, Any]:
        raise NoBackendError(
            "No agent backend configured. Set ANTHROPIC_API_KEY (or OPENAI_API_KEY) "
            "to run the live multi-agent loop; running stub-only for now."
        )


def select_runner(backend: str = "auto", model: str | None = None) -> Runner:
    """Choose a runner by explicit ``backend`` or by which API key is present.

    Order for ``auto``: Anthropic key, then OpenAI key, then the Claude Code CLI
    (reuses local auth, no key), then a no-op StubRunner. The StubRunner is
    always returned (never None) so callers have a uniform object; it raises
    NoBackendError on use.
    """
    backend = (backend or "auto").lower()
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    has_gemini = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))

    if backend == "anthropic":
        return AnthropicRunner(model)
    if backend == "openai":
        return OpenAIRunner(model)
    if backend == "gemini":
        return GeminiRunner(model)
    if backend == "claude-cli":
        return ClaudeCLIRunner(model)
    if backend == "stub":
        # Explicit offline path: honest, deterministic, no LLM call. The frontend's
        # "live agents" toggle selects this when unchecked (instant demo).
        return StubRunner()
    if backend not in ("auto",):
        raise ValueError(
            f"unknown backend {backend!r} (use auto|anthropic|openai|gemini|claude-cli|stub)")

    if has_anthropic:
        return AnthropicRunner(model)
    if has_openai:
        return OpenAIRunner(model)
    if has_gemini:
        return GeminiRunner(model)
    if shutil.which("claude"):
        return ClaudeCLIRunner(model)
    return StubRunner()


def run_with_retry(runner: Runner, prompt: str, context: str,
                   schema: dict[str, Any], retries: int = 1) -> dict[str, Any]:
    """Call ``runner`` with one retry on a JSON parse/agent error.

    NoBackendError is not retried — it propagates so the harness can stub the
    role immediately.
    """
    last: Exception | None = None
    for _ in range(retries + 1):
        try:
            result = runner.run(prompt, context, schema)
            if not isinstance(result, dict):
                raise AgentError(f"runner returned {type(result).__name__}, expected dict")
            return result
        except NoBackendError:
            raise
        except Exception as exc:  # noqa: BLE001 — provider SDKs vary
            last = exc
    raise AgentError(f"agent failed after {retries + 1} attempts: {last}")
