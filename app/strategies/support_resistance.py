"""Support & resistance detection from swing pivots.

A level matters because price turned there REPEATEDLY — so the method is: find
swing pivots (a bar whose high tops its neighbours, or whose low bottoms them),
then cluster nearby pivots into zones. A zone touched many times is stronger
than a lone wick. Old resistance that price has broken above becomes support
(and vice-versa), so a level is classified support/resistance by where it sits
relative to the CURRENT price, not by whether it came from a high or a low.

Tolerances are fractions of price, never absolute rupees, so a Rs 90 stock and
a Rs 3,500 stock cluster on the same logic.

Reference: classical technical analysis (Edwards & Magee); the pivot-fractal
definition follows Bill Williams' fractals with a configurable arm length.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

PIVOT_ARM = 3          # bars on each side that a swing must exceed
MERGE_TOL = 0.008      # pivots within 0.8% of a cluster mean merge into it
MIN_SEPARATION = 0.004 # drop a level sitting within 0.4% of the current price
MAX_LEVELS = 6         # keep only the strongest zones, so the chart stays legible


@dataclass
class Level:
    price: float
    kind: str        # "support" | "resistance" relative to the reference price
    strength: int    # number of pivot touches in the cluster

    def as_dict(self) -> dict[str, Any]:
        return {"price": round(self.price, 2), "kind": self.kind, "strength": self.strength}


def _pivot_prices(df: pd.DataFrame, arm: int) -> list[float]:
    """Swing-high highs and swing-low lows — the raw touch points."""
    highs = df["High"].to_numpy(dtype=float)
    lows = df["Low"].to_numpy(dtype=float)
    n = len(df)
    out: list[float] = []
    for i in range(arm, n - arm):
        left_h = highs[i - arm:i]
        right_h = highs[i + 1:i + arm + 1]
        if highs[i] > left_h.max() and highs[i] > right_h.max():
            out.append(float(highs[i]))
        left_l = lows[i - arm:i]
        right_l = lows[i + 1:i + arm + 1]
        if lows[i] < left_l.min() and lows[i] < right_l.min():
            out.append(float(lows[i]))
    return out


def _cluster(prices: list[float], tol: float) -> list[tuple[float, int]]:
    """Merge prices within `tol` (fraction) of the running cluster mean.

    Returns (mean_price, touch_count) per cluster. Sorting first makes a single
    linear pass correct — a price only ever needs to compare to the last cluster.
    """
    clusters: list[list[float]] = []
    for p in sorted(prices):
        if clusters:
            mean = sum(clusters[-1]) / len(clusters[-1])
            if abs(p - mean) <= tol * mean:
                clusters[-1].append(p)
                continue
        clusters.append([p])
    return [(sum(c) / len(c), len(c)) for c in clusters]


def detect_levels(
    df: pd.DataFrame,
    ref_price: Optional[float] = None,
    arm: int = PIVOT_ARM,
    max_levels: int = MAX_LEVELS,
) -> list[Level]:
    """Strongest S/R zones for `df`, classified against the current price.

    `ref_price` defaults to the last close. Levels sitting almost exactly on the
    current price are dropped — they are not actionable as either side.
    """
    if df is None or len(df) < 2 * arm + 2:
        return []

    ref = float(ref_price) if ref_price is not None else float(df["Close"].iloc[-1])
    clusters = _cluster(_pivot_prices(df, arm), MERGE_TOL)

    levels: list[Level] = []
    for price, touches in clusters:
        if ref > 0 and abs(price - ref) / ref < MIN_SEPARATION:
            continue  # too close to price to trade against
        kind = "support" if price < ref else "resistance"
        levels.append(Level(price=price, kind=kind, strength=touches))

    # Strongest first, then keep them in price order for drawing.
    levels.sort(key=lambda l: (-l.strength, abs(l.price - ref)))
    levels = levels[:max_levels]
    levels.sort(key=lambda l: l.price)
    return levels


def nearest(levels: list[Level], price: float) -> tuple[Optional[Level], Optional[Level]]:
    """(nearest support below price, nearest resistance above price)."""
    below = [l for l in levels if l.price < price]
    above = [l for l in levels if l.price > price]
    support = max(below, key=lambda l: l.price) if below else None
    resistance = min(above, key=lambda l: l.price) if above else None
    return support, resistance


def summarise(df: pd.DataFrame, ref_price: Optional[float] = None) -> dict[str, Any]:
    """Levels plus the nearest support/resistance the agent can reason over."""
    ref = float(ref_price) if ref_price is not None else (
        float(df["Close"].iloc[-1]) if df is not None and len(df) else 0.0
    )
    levels = detect_levels(df, ref_price=ref)
    support, resistance = nearest(levels, ref)
    return {
        "levels": [l.as_dict() for l in levels],
        "support": round(support.price, 2) if support else None,
        "resistance": round(resistance.price, 2) if resistance else None,
        "support_strength": support.strength if support else 0,
        "resistance_strength": resistance.strength if resistance else 0,
    }
