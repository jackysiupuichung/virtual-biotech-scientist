"""Unit tests for the shared backend-selection decision."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from common.llm_backend import resolve_backend

ALL_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "VBIO_MODEL")


@pytest.fixture
def clean_env(monkeypatch):
    for k in ALL_KEYS:
        monkeypatch.delenv(k, raising=False)
    # Default: pretend claude is not on PATH unless a test opts in.
    monkeypatch.setattr("common.llm_backend.shutil.which", lambda _name: None)
    return monkeypatch


def test_explicit_wins(clean_env):
    clean_env.setenv("ANTHROPIC_API_KEY", "x")  # present, but explicit overrides
    assert resolve_backend("openai") == ("openai", None)


def test_explicit_auto_falls_through(clean_env):
    clean_env.setenv("OPENAI_API_KEY", "x")
    assert resolve_backend("auto") == ("openai", None)


def test_anthropic_priority(clean_env):
    clean_env.setenv("ANTHROPIC_API_KEY", "a")
    clean_env.setenv("OPENAI_API_KEY", "o")
    clean_env.setenv("GEMINI_API_KEY", "g")
    assert resolve_backend() == ("anthropic", None)


def test_openai_second(clean_env):
    clean_env.setenv("OPENAI_API_KEY", "o")
    clean_env.setenv("GEMINI_API_KEY", "g")
    assert resolve_backend() == ("openai", None)


def test_gemini_third(clean_env):
    clean_env.setenv("GEMINI_API_KEY", "g")
    assert resolve_backend() == ("gemini", None)


def test_google_api_key_selects_gemini(clean_env):
    clean_env.setenv("GOOGLE_API_KEY", "g")
    assert resolve_backend() == ("gemini", None)


def test_claude_cli_when_on_path(clean_env):
    clean_env.setattr("common.llm_backend.shutil.which", lambda _name: "/usr/bin/claude")
    assert resolve_backend() == ("claude-cli", None)


def test_stub_when_nothing(clean_env):
    assert resolve_backend() == ("stub", None)


def test_model_from_env(clean_env):
    clean_env.setenv("VBIO_MODEL", "my-model")
    clean_env.setenv("ANTHROPIC_API_KEY", "a")
    assert resolve_backend() == ("anthropic", "my-model")
