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

from typing import Any, Optional

from pydantic import ValidationError

from app.config import get_config
from app.llm.client import LLMUnavailable, complete_json
from app.models.state import (
    Direction,
    MarketAnalysis,
    NewsSignals,
    ReasonedAnalysis,
)
from app.prompts import load_prompt


def _finite(x: float) -> bool:
    return x == x and x not in (float("inf"), float("-inf"))


def reason(
    ma: MarketAnalysis, news: Optional[NewsSignals] = None
) -> tuple[ReasonedAnalysis, dict[str, Any]]:
    """Return (analysis, usage). usage records source/tokens/cost for tracing."""
    # A broken feed never reaches the model — cheaper and safer to short-circuit.
    if not _finite(ma.last_price):
        return _rule_based(ma), {"source": "fallback", "reason": "non-finite feed"}

    cfg = get_config("agent").get("reasoning_engine", {})
    version = str(cfg.get("prompt_version", "v1"))

    payload: dict[str, Any] = {
        "symbol": ma.symbol,
        "last_price": ma.last_price,
        "trend": ma.trend,
        "indicators": ma.indicators,
        "technical_signal": ma.signal.value,
    }
    if ma.patterns:
        payload["candlesticks"] = {
            "patterns": ma.patterns,
            "bias": ma.pattern_bias,
            "score": ma.pattern_score,
        }
    if ma.nn_score is not None:
        payload["model_validation"] = {
            "win_probability": ma.nn_score,
            "note": "learned validator trained on backtest outcomes; evidence, not an order",
        }
    if news is not None:
        payload["news"] = {
            "sentiment_score": news.sentiment_score,
            "sentiment_label": news.sentiment_label,
            "confidence": news.confidence,
            "key_events": news.key_events,
            "summary": news.summary,
            "article_count": news.article_count,
        }

    try:
        result = complete_json(
            system_prompt=load_prompt("reasoning", version),
            user_payload=payload,
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


def _reward_risk(entry: float, stop: float, take: float) -> float:
    """|target-entry| / |entry-stop|. 0 when there is no real position (hold)."""
    if not all(_finite(v) for v in (entry, stop, take)):
        return 0.0
    risk = abs(entry - stop)
    return round(abs(take - entry) / risk, 2) if risk > 1e-9 else 0.0


def _hold_estimate(entry: float, take: float, atr: float) -> Optional[int]:
    """Rough holding duration: distance to target measured in daily ranges.

    Price travels ~1 ATR per day on average (undirected), so target_dist / ATR
    is the *floor* number of trading days to reach the target if the move goes
    cleanly. Deliberately labelled an estimate — real holds are usually longer
    because movement is not all in one direction.
    """
    if not all(_finite(v) for v in (entry, take, atr)) or atr <= 0 or entry == take:
        return None
    return max(1, round(abs(take - entry) / atr))


def _coerce(data: dict[str, Any], ma: MarketAnalysis) -> ReasonedAnalysis:
    """Validate the model's JSON into the ReasonedAnalysis contract."""
    direction = Direction(str(data["direction"]).strip().lower())
    confidence = min(max(float(data.get("confidence", 0.5)), 0.0), 1.0)

    entry = float(data.get("entry_price", ma.last_price))
    stop = float(data["stop_loss"])
    take = float(data["take_profit"])
    if not all(_finite(v) for v in (entry, stop, take)):
        raise ValueError("non-finite levels from model")

    atr = ma.indicators.get("atr_14", 0.0) if ma.indicators else 0.0
    is_hold = direction == Direction.HOLD

    def _text(key: str, fallback: str) -> str:
        return str(data.get(key, "")).strip()[:300] or fallback

    return ReasonedAnalysis(
        symbol=ma.symbol,
        thesis=str(data.get("thesis", "")).strip()[:500] or f"{ma.symbol}: {direction.value}",
        direction=direction,
        confidence=confidence,
        entry_price=round(entry, 2),
        stop_loss=round(stop, 2),
        take_profit=round(take, 2),
        entry_rationale=_text("entry_rationale", _default_entry_rationale(ma, direction, entry, atr)),
        confirmation=_text("confirmation", _default_confirmation(ma, direction)),
        invalidation=_text("invalidation", _default_invalidation(ma, direction, stop)),
        risk_reward=0.0 if is_hold else _reward_risk(entry, stop, take),
        est_hold_days=None if is_hold else _hold_estimate(entry, take, atr),
    )


def _default_entry_rationale(ma: MarketAnalysis, d: Direction, entry: float, atr: float) -> str:
    if d == Direction.HOLD:
        return "No entry — conditions do not justify a position yet."
    side = "above" if d == Direction.LONG else "below"
    return (
        f"Enter near ₹{entry:.2f} ({ma.trend} trend); stop and target are ATR-scaled "
        f"(ATR ₹{atr:.2f}) so the risk sits {side} structure rather than at a round number."
    )


def _default_confirmation(ma: MarketAnalysis, d: Direction) -> str:
    if d == Direction.HOLD:
        return "Wait for a directional close and momentum to leave the neutral zone."
    if d == Direction.LONG:
        return "Confirm on a daily close holding above EMA20 with RSI14 rising but under 70."
    return "Confirm on a daily close staying below EMA20 with RSI14 falling but above 30."


def _default_invalidation(ma: MarketAnalysis, d: Direction, stop: float) -> str:
    if d == Direction.HOLD:
        return "N/A — no position at risk."
    flip = "down" if d == Direction.LONG else "up"
    return f"Thesis fails on a close through the stop (₹{stop:.2f}) or the trend flipping {flip}."


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

    is_hold = ma.signal == Direction.HOLD
    stop_r = round(stop, 2) if _finite(stop) else stop
    take_r = round(take, 2) if _finite(take) else take
    return ReasonedAnalysis(
        symbol=ma.symbol,
        thesis=thesis,
        direction=ma.signal,
        confidence=ma.confidence,
        entry_price=entry,
        stop_loss=stop_r,
        take_profit=take_r,
        entry_rationale=_default_entry_rationale(ma, ma.signal, entry, atr),
        confirmation=_default_confirmation(ma, ma.signal),
        invalidation=_default_invalidation(ma, ma.signal, stop_r),
        risk_reward=0.0 if is_hold else _reward_risk(entry, stop, take),
        est_hold_days=None if is_hold else _hold_estimate(entry, take, atr),
    )
