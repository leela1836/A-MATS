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


# ── quota fallback chain ──
# Free-tier Gemini keys allow ~20 requests/day PER MODEL, so exhausting one
# model must fall through to the next rather than failing the cycle.

def test_model_chain_starts_with_primary_then_fallbacks():
    chain = client.model_chain()
    assert chain[0] == "gemini-2.5-flash"
    assert len(chain) > 1, "a fallback chain is what multiplies the daily quota"
    assert len(chain) == len(set(chain)), "no duplicate models"


def test_explicit_model_overrides_primary():
    assert client.model_chain("gemini-3.5-flash")[0] == "gemini-3.5-flash"


def test_rate_limited_model_falls_through_to_next(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    seen = []

    def fake_gemini(key, model, *a, **k):
        seen.append(model)
        if model == "gemini-2.5-flash":
            raise client.ModelUnavailable(model, 429, "quota exhausted")
        return '{"ok": true}', 10, 5

    monkeypatch.setattr(client, "_gemini_call", fake_gemini)
    result = client.complete_json("sys", {"a": 1})
    assert seen[0] == "gemini-2.5-flash"      # primary tried first
    assert result.model != "gemini-2.5-flash"  # and fell through
    assert result.data == {"ok": True}


def test_all_models_exhausted_raises(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "k")

    def always_429(key, model, *a, **k):
        raise client.ModelUnavailable(model, 429, "quota")

    monkeypatch.setattr(client, "_gemini_call", always_429)
    with pytest.raises(client.LLMUnavailable, match="all models exhausted"):
        client.complete_json("sys", {"a": 1})


def test_retired_model_404_also_falls_through(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "k")

    def fake(key, model, *a, **k):
        if model == "gemini-2.5-flash":
            raise client.ModelUnavailable(model, 404, "retired")
        return '{"ok": true}', 1, 1

    monkeypatch.setattr(client, "_gemini_call", fake)
    assert client.complete_json("sys", {}).data == {"ok": True}
