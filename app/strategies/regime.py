"""Market regime — the context the agent trades *into*.

The live track record showed the agent bleeding on shorts while the market rose:
its short signals were fighting an uptrend. The honest fix is not to guess better
but to stop taking the structurally-losing side — so we read a simple regime from
a Nifty-50 proxy versus its 200-day average and let the scan gate shorts when the
tape is clearly bullish. Read-only; fails open to 'neutral' so a data hiccup never
silently changes behaviour.
"""
from __future__ import annotations

from typing import Any

PROXY = "NIFTYBEES.NS"   # Nifty-50 ETF — trades like an equity, so any collector fetches it
BAND = 2.0               # % band around the 200-day SMA that counts as 'neutral' (anti-whipsaw)


def market_regime(proxy: str = PROXY) -> dict[str, Any]:
    """Classify the market as bull / bear / neutral off a proxy vs its 200-day SMA."""
    out: dict[str, Any] = {"regime": "neutral", "proxy": proxy, "gap_pct": None,
                           "note": "regime unavailable — treating as neutral"}
    try:
        from app.collectors.market_collector import fetch_history
        close = fetch_history(proxy, period="2y")["Close"]
        if len(close) >= 200:
            sma = float(close.rolling(200).mean().iloc[-1])
            price = float(close.iloc[-1])
            gap = (price / sma - 1) * 100.0
            regime = "bull" if gap > BAND else "bear" if gap < -BAND else "neutral"
            out = {
                "regime": regime, "proxy": proxy, "gap_pct": round(gap, 2),
                "price": round(price, 2), "sma200": round(sma, 2),
                "note": f"{proxy} is {gap:+.1f}% vs its 200-day average",
            }
    except Exception:
        pass  # fail open — never let a data glitch silently gate trades
    return out


def shorts_allowed(regime: dict[str, Any]) -> bool:
    """Policy: only short in a CONFIRMED bear tape.

    The live record shows shorts bleed in bull AND neutral markets — the proxy sat
    at its 200-day average for weeks while shorts kept losing. So permit shorts only
    when the regime is decisively bearish; in bull or neutral, don't take the side
    the agent's own history says it loses on.
    """
    return (regime or {}).get("regime") == "bear"
