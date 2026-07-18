"""Multi-provider LLM factory tests — NO API keys, NO network.

Verifies that ``build_chat_model`` wires the right LangChain class, base_url,
and credential per ``LLM_PROVIDER``, that credential validation is
provider-aware, and that costing resolves the (provider, model) price rows.
"""

from __future__ import annotations

import pytest
from src.config import settings
from src.graph import llm as llm_mod
from src.observability.costing import estimate_cost


def _set(monkeypatch, **attrs):
    for k, v in attrs.items():
        monkeypatch.setattr(settings, k, v, raising=False)


# ── factory wiring (OpenAI-compatible lane) ──────────────────────────────────


def test_openai_provider_uses_default_endpoint(monkeypatch):
    _set(
        monkeypatch,
        llm_provider="openai",
        llm_base_url=None,
        openai_api_key="sk-test",
        llm_model="gpt-4o-mini",
    )
    chat = llm_mod.build_chat_model()
    assert type(chat).__name__ == "ChatOpenAI"
    # langchain-openai leaves base_url unset for the official endpoint
    assert getattr(chat, "openai_api_base", None) in (None, "")


def test_groq_provider_routes_to_groq_endpoint(monkeypatch):
    _set(
        monkeypatch,
        llm_provider="groq",
        llm_base_url=None,
        groq_api_key="gsk_test",
        llm_model="llama-3.3-70b-versatile",
    )
    chat = llm_mod.build_chat_model()
    assert type(chat).__name__ == "ChatOpenAI"
    assert "api.groq.com" in (chat.openai_api_base or "")


def test_nvidia_provider_routes_to_nim_endpoint(monkeypatch):
    _set(
        monkeypatch,
        llm_provider="nvidia",
        llm_base_url=None,
        nvidia_api_key="nvapi-test",
        llm_model="meta/llama-3.1-70b-instruct",
    )
    chat = llm_mod.build_chat_model()
    assert "integrate.api.nvidia.com" in (chat.openai_api_base or "")


def test_ollama_provider_uses_local_base_url_without_key(monkeypatch):
    _set(
        monkeypatch,
        llm_provider="ollama",
        ollama_base_url="http://localhost:11434/v1",
        llm_model="llama3.1:8b",
    )
    chat = llm_mod.build_chat_model()
    assert "11434" in (chat.openai_api_base or "")


def test_explicit_base_url_overrides_provider_default(monkeypatch):
    _set(
        monkeypatch,
        llm_provider="groq",
        llm_base_url="http://proxy.local/v1",
        groq_api_key="gsk_test",
    )
    chat = llm_mod.build_chat_model()
    assert chat.openai_api_base == "http://proxy.local/v1"


def test_unknown_provider_raises_with_supported_list(monkeypatch):
    _set(monkeypatch, llm_provider="doesnotexist")
    with pytest.raises(ValueError, match="Supported:"):
        llm_mod.build_chat_model()


# ── native lanes (skipped automatically if the optional SDK isn't installed) ──


def test_anthropic_provider_uses_native_class(monkeypatch):
    pytest.importorskip("langchain_anthropic")
    _set(
        monkeypatch,
        llm_provider="anthropic",
        anthropic_api_key="sk-ant-test",
        llm_model="claude-sonnet-4-6",
    )
    chat = llm_mod.build_chat_model()
    assert type(chat).__name__ == "ChatAnthropic"


def test_gemini_provider_uses_native_class(monkeypatch):
    pytest.importorskip("langchain_google_genai")
    _set(
        monkeypatch, llm_provider="gemini", google_api_key="test-key", llm_model="gemini-2.0-flash"
    )
    chat = llm_mod.build_chat_model()
    assert type(chat).__name__ == "ChatGoogleGenerativeAI"


# ── provider-aware credential validation ─────────────────────────────────────


def test_missing_provider_key_raises_clear_error(monkeypatch):
    _set(monkeypatch, llm_provider="groq", groq_api_key="")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        llm_mod.build_llm_client()


def test_ollama_needs_no_key(monkeypatch):
    _set(monkeypatch, llm_provider="ollama")
    assert settings.has_llm_credentials is True


def test_placeholder_keys_do_not_count(monkeypatch):
    _set(monkeypatch, llm_provider="openai", openai_api_key="sk-...")
    assert settings.has_llm_credentials is False


# ── provider-aware costing ───────────────────────────────────────────────────


def test_costing_uses_provider_price_row():
    openai_cost = estimate_cost(1000, 1000, "gpt-4o-mini", "openai")
    groq_cost = estimate_cost(1000, 1000, "llama-3.3-70b-versatile", "groq")
    assert openai_cost == pytest.approx(0.00075)
    assert groq_cost == pytest.approx(0.00138)


def test_costing_local_providers_are_free():
    assert estimate_cost(5000, 5000, "llama3.1:8b", "ollama") == 0.0
    assert estimate_cost(5000, 5000, "meta/llama-3.1-70b-instruct", "nvidia") == 0.0


def test_costing_unknown_model_falls_back_to_provider_wildcard():
    # unknown gemini model -> gemini "*" row, not the openai default
    cost = estimate_cost(1000, 1000, "gemini-9.9-ultra", "gemini")
    assert cost == pytest.approx(0.00050)
