"""LLM client tests: provider dispatch, key resolution, cost maths.

No real network calls.
"""
import pytest

from app.llm import client


def test_provider_comes_from_config():
    # configs/agent.yaml is the source of truth for the active provider.
    assert client.provider_name() in {"google", "openai"}


def test_key_env_follows_provider(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "g-key")
    monkeypatch.setenv("OPENAI_API_KEY", "o-key")
    assert client.api_key("google") == "g-key"
    assert client.api_key("openai") == "o-key"


def test_unavailable_without_key(monkeypatch):
    """conftest strips all provider keys, so this must raise, not call out."""
    with pytest.raises(client.LLMUnavailable):
        client.complete_json("sys", {"x": 1})


def test_no_provider_key_leaks_into_tests():
    """Guards the invariant that the suite can never spend real tokens."""
    for provider in ("google", "openai"):
        assert client.api_key(provider) is None


def test_cost_maths():
    # gemini-2.5-flash: $0.30/1M in, $2.50/1M out.
    cost = client._cost("gemini-2.5-flash", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.30 + 2.50)


def test_unknown_model_uses_default_pricing():
    assert client._cost("some-future-model", 1_000_000, 0) == pytest.approx(
        client._DEFAULT_PRICING[0]
    )
