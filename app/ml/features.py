"""Feature extraction for the trade validator.

ONE extractor, shared by training (over backtest bars) and live inference, so
the model can never be trained on features that differ from what it is scored
on. Every value is derived only from bars up to and INCLUDING the decision bar
— the caller passes `window = df.iloc[:decision_index + 1]`, exactly the slice
the backtester's no-lookahead loop uses. Nothing here may read a future bar.

Feature families:
  • technical structure — RSI position, EMA separations, price vs EMA20/50/200,
    ATR as a fraction of price, the rule engine's own confidence
  • candlestick context — the netted, trend-adjusted pattern score
  • volume & liquidity — relative volume (surge), rupee-turnover spike, short-
    vs-long volume trend, and signed up/down volume pressure (a light OBV read)

All ratios are unit-free (fractions, not rupees) so the model behaves the same
on a Rs 280 stock and a Rs 24,000 index.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from app.collectors.market_collector import classify, compute_indicators
from app.models.state import Direction
from app.strategies.candlesticks import detect, summarise

# Order is CONTRACT: saved with every model, asserted at load. Never reorder;
# only append, and retrain when you do.
FEATURE_NAMES: list[str] = [
    "dir_long",
    "rsi_dist",
    "ema_sep",
    "price_vs_ema20",
    "price_vs_ema50",
    "price_vs_ema200",
    "atr_pct",
    "rule_confidence",
    "candle_net_score",
    "vol_surge",
    "turnover_spike",
    "vol_trend_ratio",
    "up_down_vol_pressure",
]


def _safe(n: float, d: float) -> float:
    return float(n / d) if d else 0.0


def _volume_features(window: pd.DataFrame) -> dict[str, float]:
    """Relative volume, turnover, and directional volume pressure.

    Absolute volume is meaningless across instruments, so every figure is
    relative to the symbol's own recent history. Missing/zero volume (some
    index feeds report none) degrades gracefully to 0, i.e. 'no information'.
    """
    if "Volume" not in window.columns:
        return {"vol_surge": 0.0, "turnover_spike": 0.0,
                "vol_trend_ratio": 0.0, "up_down_vol_pressure": 0.0}

    vol = window["Volume"].astype(float).fillna(0.0)
    close = window["Close"].astype(float)
    last_vol = float(vol.iloc[-1])
    avg20 = float(vol.tail(20).mean())
    avg5 = float(vol.tail(5).mean())

    turnover = close * vol
    last_turn = float(turnover.iloc[-1])
    avg_turn20 = float(turnover.tail(20).mean())

    # Signed volume over the last 10 bars / total volume: +1 all buying-day
    # volume, -1 all selling-day volume. A compact OBV-style pressure read.
    look = min(10, len(window) - 1)
    pressure = 0.0
    if look > 0:
        deltas = close.diff().tail(look)
        vols = vol.tail(look)
        signed = float((np.sign(deltas) * vols).sum())
        total = float(vols.sum())
        pressure = _safe(signed, total)

    return {
        "vol_surge": _safe(last_vol, avg20) - 1.0 if avg20 else 0.0,
        "turnover_spike": _safe(last_turn, avg_turn20) - 1.0 if avg_turn20 else 0.0,
        "vol_trend_ratio": _safe(avg5, avg20) - 1.0 if avg20 else 0.0,
        "up_down_vol_pressure": pressure,
    }


def extract(
    window: pd.DataFrame,
    direction: Direction | str,
    params: Optional[dict] = None,
) -> np.ndarray:
    """Feature vector for a candidate entry decided on the LAST bar of `window`.

    `direction` is the trade the rule strategy proposes (long/short); the model
    scores that specific proposal, so its sign matters.
    """
    ind = compute_indicators(window)
    _, _, confidence = classify(ind, params)
    trend, _, _ = classify(ind, params)

    price = ind["last_price"]
    ema20, ema50, ema200 = ind["ema_20"], ind["ema_50"], ind["ema_200"]
    rsi, atr = ind["rsi_14"], ind["atr_14"]

    dir_val = direction.value if isinstance(direction, Direction) else str(direction)
    dir_long = 1.0 if dir_val == Direction.LONG.value else 0.0

    net_score = summarise(detect(window, trend))["net_score"]
    vf = _volume_features(window)

    feats = {
        "dir_long": dir_long,
        "rsi_dist": (rsi - 50.0) / 50.0,
        "ema_sep": _safe(ema20 - ema50, ema50),
        "price_vs_ema20": _safe(price - ema20, ema20),
        "price_vs_ema50": _safe(price - ema50, ema50),
        "price_vs_ema200": _safe(price - ema200, ema200),
        "atr_pct": _safe(atr, price),
        "rule_confidence": float(confidence),
        "candle_net_score": float(net_score),
        **vf,
    }
    return np.array([feats[name] for name in FEATURE_NAMES], dtype=float)
