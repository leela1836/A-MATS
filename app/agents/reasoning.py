"""Reasoning Engine: turns a technical read into a trade thesis.

Primary path is an LLM call against a versioned prompt. If no API key is
configured, the provider errors, or the response cannot be coerced into the
ReasonedAnalysis contract, we fall back to deterministic rules so a trading
cycle never fails just because the model was unavailable.

Note the deliberate separation of concerns: this module only guarantees the
output is *structurally* valid. Whether the proposal is *sound* (levels
ordered, reward:risk acceptable) is the Evaluation Engine's job — that gate
must be able to veto the LLM.
"""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.config import get_config
from app.llm.client import LLMUnavailable, complete_json
from app.models.state import Direction, MarketAnalysis, ReasonedAnalysis
from app.prompts import load_prompt


def _finite(x: float) -> bool:
    return x == x and x not in (float("inf"), float("-inf"))


def reason(ma: MarketAnalysis) -> tuple[ReasonedAnalysis, dict[str, Any]]:
    """Return (analysis, usage). usage records source/tokens/cost for tracing."""
    # A broken feed never reaches the model — cheaper and safer to short-circuit.
    if not _finite(ma.last_price):
        return _rule_based(ma), {"source": "fallback", "reason": "non-finite feed"}

    cfg = get_config("agent").get("reasoning_engine", {})
    version = str(cfg.get("prompt_version", "v1"))

    try:
        result = complete_json(
            system_prompt=load_prompt("reasoning", version),
            user_payload={
                "symbol": ma.symbol,
                "last_price": ma.last_price,
                "trend": ma.trend,
                "indicators": ma.indicators,
                "technical_signal": ma.signal.value,
            },
            model=cfg.get("model"),
            temperature=cfg.get("temperature"),
        )
    except LLMUnavailable as exc:
        return _rule_based(ma), {"source": "fallback", "reason": str(exc)[:120]}

    try:
        analysis = _coerce(result.data, ma)
    except (ValidationError, KeyError, TypeError, ValueError) as exc:
        return _rule_based(ma), {
            "source": "fallback",
            "reason": f"unusable LLM output: {type(exc).__name__}",
            "model": result.model,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "cost_usd": result.cost_usd,
        }

    return analysis, {
        "source": "llm",
        "model": result.model,
        "prompt_version": version,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "cost_usd": result.cost_usd,
    }


def _coerce(data: dict[str, Any], ma: MarketAnalysis) -> ReasonedAnalysis:
    """Validate the model's JSON into the ReasonedAnalysis contract."""
    direction = Direction(str(data["direction"]).strip().lower())
    confidence = min(max(float(data.get("confidence", 0.5)), 0.0), 1.0)

    entry = float(data.get("entry_price", ma.last_price))
    stop = float(data["stop_loss"])
    take = float(data["take_profit"])
    if not all(_finite(v) for v in (entry, stop, take)):
        raise ValueError("non-finite levels from model")

    return ReasonedAnalysis(
        symbol=ma.symbol,
        thesis=str(data.get("thesis", "")).strip()[:500] or f"{ma.symbol}: {direction.value}",
        direction=direction,
        confidence=confidence,
        entry_price=round(entry, 2),
        stop_loss=round(stop, 2),
        take_profit=round(take, 2),
    )


def _rule_based(ma: MarketAnalysis) -> ReasonedAnalysis:
    """Deterministic ATR-based thesis — the offline / no-key path."""
    entry = ma.last_price
    atr = ma.indicators.get("atr_14", 0.0) if ma.indicators else 0.0

    if ma.signal == Direction.HOLD or not _finite(entry):
        stop, take = entry, entry
    else:
        stop_dist = 1.5 * atr if atr > 0 else entry * 0.03
        take_dist = 3.0 * atr if atr > 0 else entry * 0.06
        if ma.signal == Direction.LONG:
            stop, take = entry - stop_dist, entry + take_dist
        else:
            stop, take = entry + stop_dist, entry - take_dist

    if ma.indicators:
        rsi = ma.indicators.get("rsi_14", float("nan"))
        thesis = f"{ma.symbol}: trend {ma.trend}, RSI {rsi:.1f} → {ma.signal.value} bias."
    else:
        thesis = f"{ma.symbol}: {ma.signal.value} bias."

    return ReasonedAnalysis(
        symbol=ma.symbol,
        thesis=thesis,
        direction=ma.signal,
        confidence=ma.confidence,
        entry_price=entry,
        stop_loss=round(stop, 2) if _finite(stop) else stop,
        take_profit=round(take, 2) if _finite(take) else take,
    )
