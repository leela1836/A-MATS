"""Reasoning Engine tests — fallback, LLM coercion, and gate interaction.

No test here makes a real API call; the LLM layer is monkeypatched.
"""
import pytest

from app.agents import reasoning
from app.llm.client import LLMResult, LLMUnavailable
from app.models.state import Direction, MarketAnalysis
from app.workflows.graph import GRAPH
from app.models.state import new_state


def _ma(signal=Direction.LONG, price=1400.0, atr=20.0):
    return MarketAnalysis(
        symbol="RELIANCE.NS", last_price=price, trend="up",
        signal=signal, confidence=0.72,
        indicators={"ema_20": 1380.0, "ema_50": 1350.0, "rsi_14": 58.0, "atr_14": atr},
    )


def test_fallback_used_when_no_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    analysis, usage = reasoning.reason(_ma())
    assert usage["source"] == "fallback"
    # ATR-based levels: 1.5x ATR stop, 3x ATR target.
    assert analysis.stop_loss == pytest.approx(1400.0 - 1.5 * 20.0)
    assert analysis.take_profit == pytest.approx(1400.0 + 3.0 * 20.0)


def test_fallback_on_provider_error(monkeypatch):
    def boom(*a, **k):
        raise LLMUnavailable("network down")
    monkeypatch.setattr(reasoning, "complete_json", boom)
    analysis, usage = reasoning.reason(_ma())
    assert usage["source"] == "fallback"
    assert "network down" in usage["reason"]
    assert analysis.direction == Direction.LONG


def test_llm_output_is_used_and_metered(monkeypatch):
    def fake(*a, **k):
        return LLMResult(
            data={
                "direction": "long", "thesis": "EMA20 above EMA50 with RSI 58.",
                "confidence": 0.81, "entry_price": 1400.0,
                "stop_loss": 1370.0, "take_profit": 1460.0,
            },
            model="gpt-4o", prompt_tokens=900, completion_tokens=110,
            cost_usd=0.00335,
        )
    monkeypatch.setattr(reasoning, "complete_json", fake)
    analysis, usage = reasoning.reason(_ma())
    assert usage["source"] == "llm"
    assert usage["prompt_tokens"] == 900
    assert usage["cost_usd"] == pytest.approx(0.00335)
    assert analysis.confidence == 0.81
    assert analysis.thesis.startswith("EMA20")


def test_malformed_llm_output_falls_back(monkeypatch):
    def fake(*a, **k):
        return LLMResult(
            data={"direction": "sideways-ish", "thesis": "?"},  # invalid enum + missing levels
            model="gpt-4o", prompt_tokens=10, completion_tokens=5, cost_usd=0.0,
        )
    monkeypatch.setattr(reasoning, "complete_json", fake)
    analysis, usage = reasoning.reason(_ma())
    assert usage["source"] == "fallback"
    assert "unusable LLM output" in usage["reason"]
    assert analysis.direction == Direction.LONG  # deterministic path took over


def test_bad_feed_short_circuits_before_llm(monkeypatch):
    """A non-finite feed must never reach the model."""
    called = False

    def fake(*a, **k):
        nonlocal called
        called = True
        raise AssertionError("LLM should not be called on a bad feed")

    monkeypatch.setattr(reasoning, "complete_json", fake)
    _, usage = reasoning.reason(_ma(price=float("nan")))
    assert called is False
    assert usage["source"] == "fallback"


def test_evaluation_gate_can_veto_the_llm(monkeypatch):
    """An inverted-level LLM proposal must be halted by the evaluation gate."""
    def fake(*a, **k):
        return LLMResult(
            data={
                "direction": "long", "thesis": "confidently wrong",
                "confidence": 0.99, "entry_price": 1400.0,
                "stop_loss": 1500.0,    # stop ABOVE entry on a long — illogical
                "take_profit": 1300.0,  # target BELOW entry
            },
            model="gpt-4o", prompt_tokens=10, completion_tokens=5, cost_usd=0.0,
        )
    # complete_json is faked, so no provider key is involved.
    monkeypatch.setattr(reasoning, "complete_json", fake)

    final = GRAPH.invoke(new_state(["RELIANCE.NS"]))
    assert final["halted"] is True
    assert "evaluation" in final["halt_reason"]
    assert final.get("decision") is None
    assert final.get("execution_result") is None
