"""Stan Weinstein's Stage Analysis — a mechanical breakout system.

From *Secrets for Profiting in Bull and Bear Markets*. Weinstein sorts every
chart into one of four stages around its 30-week moving average:

  Stage 1  basing / accumulation  (flat MA, price chopping around it)
  Stage 2  advancing / mark-up    (rising MA, price above it)      <- BUY
  Stage 3  topping / distribution  (flattening MA after a run)
  Stage 4  declining / mark-down    (falling MA, price below it)    <- SHORT/AVOID

The one rule that makes money in his method: **buy a Stage-2 breakout** — price
clearing the top of its base on EXPANDING VOLUME while the 30-week MA has turned
up — and stay out of (or short) Stage 4. This is trend-following: the opposite
temperament to the current EMA/RSI signal, which is why it is worth measuring.

We trade daily bars, so the 30-week MA becomes a 150-day MA (30 weeks x 5
sessions). Everything is a proportion or a moving-average relationship, so it
behaves the same across price scales. Whether it actually beats the incumbent
on NSE large-caps is an empirical question — A/B it, do not assume.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from app.models.state import Direction

DEFAULTS = {
    "wein_ma": 150,          # 30 weeks x 5 sessions
    "wein_breakout": 50,     # base lookback (~10 weeks) for the breakout level
    "wein_vol_period": 50,   # window for the average-volume baseline
    "wein_vol_mult": 1.3,    # breakout volume must exceed this x average
    "wein_slope": 20,        # bars over which the MA must be rising / falling
    "wein_allow_short": True,
}


def _params(overrides: Optional[dict]) -> dict:
    return {**DEFAULTS, **(overrides or {})}


def weinstein_signal(
    window: pd.DataFrame, overrides: Optional[dict] = None
) -> tuple[str, Direction, float]:
    """(trend, signal, confidence) for the last bar of `window`.

    Signal is LONG only on a genuine Stage-2 breakout, SHORT only on a Stage-4
    breakdown, HOLD otherwise — which is most of the time, by design.
    """
    p = _params(overrides)
    ma_p, slope = int(p["wein_ma"]), int(p["wein_slope"])
    if window is None or len(window) < ma_p + slope + 2:
        return "sideways", Direction.HOLD, 0.2

    close = window["Close"].astype(float)
    high = window["High"].astype(float)
    low = window["Low"].astype(float)
    price = float(close.iloc[-1])

    ma = close.rolling(ma_p).mean()
    ma_now = float(ma.iloc[-1])
    ma_ref = float(ma.iloc[-1 - slope])
    if ma_now != ma_now or ma_ref != ma_ref:  # NaN guard on short history
        return "sideways", Direction.HOLD, 0.2
    rising, falling = ma_now > ma_ref, ma_now < ma_ref

    lb = int(p["wein_breakout"])
    prior_high = float(high.iloc[-(lb + 1):-1].max())   # base ceiling (excl. today)
    prior_low = float(low.iloc[-(lb + 1):-1].min())     # base floor

    # Volume expansion — the confirmation Weinstein insists on.
    vratio = 1.0
    if "Volume" in window.columns:
        vp = int(p["wein_vol_period"])
        avg_v = float(window["Volume"].astype(float).iloc[-vp:].mean())
        last_v = float(window["Volume"].astype(float).iloc[-1])
        vratio = (last_v / avg_v) if avg_v > 0 else 1.0
    vol_ok = vratio >= float(p["wein_vol_mult"])

    trend = "up" if price > ma_now else "down" if price < ma_now else "sideways"

    # Stage 2: above a rising MA, closing above the base, on expanding volume.
    if price > ma_now and rising and price > prior_high and vol_ok:
        conf = 0.5 + min((vratio - 1.0) * 0.3, 0.25) + min((price - ma_now) / ma_now, 0.2)
        return "up", Direction.LONG, round(min(conf, 0.95), 3)

    # Stage 4: below a falling MA, breaking the base floor, on expanding volume.
    if p["wein_allow_short"] and price < ma_now and falling and price < prior_low and vol_ok:
        conf = 0.5 + min((vratio - 1.0) * 0.3, 0.25) + min((ma_now - price) / ma_now, 0.2)
        return "down", Direction.SHORT, round(min(conf, 0.95), 3)

    return trend, Direction.HOLD, 0.2
