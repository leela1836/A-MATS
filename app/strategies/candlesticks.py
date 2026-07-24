"""Candlestick pattern detection.

CONTEXT IS THE WHOLE POINT. The same shape means opposite things depending on
where it appears: a small body with a long lower shadow is a bullish Hammer
after a decline, and a bearish Hanging Man after a rally. Detectors that
report shapes without trend context produce confident nonsense, so every
detector here takes the prevailing trend and several patterns simply do not
fire in the wrong one.

Thresholds are proportions of the bar's own range, never absolute rupees, so
they behave identically on a Rs 280 stock and a Rs 24,000 index.

Reference: Nison, *Japanese Candlestick Charting Techniques* — the classical
definitions, which are deliberately loose; the tolerances below are one
reasonable reading of them, not gospel.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

# Shape tolerances, all as a fraction of the bar's high-low range.
DOJI_BODY_MAX = 0.10      # body this small = indecision
SMALL_BODY_MAX = 0.35     # "small real body" for hammers/stars
LONG_SHADOW_MIN = 2.0     # shadow at least Nx the body
SHORT_SHADOW_MAX = 0.20   # opposite shadow must be stubby
MARUBOZU_BODY_MIN = 0.90  # almost no shadow at all


@dataclass
class Pattern:
    name: str
    direction: str      # "bullish" | "bearish" | "neutral"
    strength: float     # 0-1, how textbook the instance is
    bars: int           # how many bars the pattern spans
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "direction": self.direction,
            "strength": round(self.strength, 3), "bars": self.bars,
            "note": self.note,
        }


@dataclass
class Candle:
    open: float
    high: float
    low: float
    close: float

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return max(self.high - self.low, 1e-9)

    @property
    def upper_shadow(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_shadow(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def is_bull(self) -> bool:
        return self.close > self.open

    @property
    def is_bear(self) -> bool:
        return self.close < self.open

    @property
    def body_pct(self) -> float:
        return self.body / self.range

    @property
    def midpoint(self) -> float:
        return (self.open + self.close) / 2


def _candles(df: pd.DataFrame, n: int = 3) -> list[Candle]:
    """Last n candles, oldest first."""
    tail = df.tail(n)
    return [
        Candle(float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"]))
        for _, r in tail.iterrows()
    ]


# ── single-bar ──

def _doji(c: Candle) -> Optional[Pattern]:
    if c.body_pct > DOJI_BODY_MAX:
        return None
    upper, lower = c.upper_shadow / c.range, c.lower_shadow / c.range
    strength = 1.0 - (c.body_pct / DOJI_BODY_MAX)
    if lower > 0.6 and upper < SHORT_SHADOW_MAX:
        return Pattern("dragonfly_doji", "bullish", strength * 0.7, 1,
                       "rejection of lower prices")
    if upper > 0.6 and lower < SHORT_SHADOW_MAX:
        return Pattern("gravestone_doji", "bearish", strength * 0.7, 1,
                       "rejection of higher prices")
    return Pattern("doji", "neutral", strength * 0.5, 1, "indecision")


def _hammer_family(c: Candle, trend: str) -> Optional[Pattern]:
    """Long lower shadow, small body at the top of the range.

    Bullish only after a decline (Hammer). The identical shape after a rally
    is a Hanging Man — a warning, not a buy.
    """
    if c.body_pct > SMALL_BODY_MAX or c.body == 0:
        return None
    if c.lower_shadow < LONG_SHADOW_MIN * c.body:
        return None
    if c.upper_shadow > SHORT_SHADOW_MAX * c.range:
        return None
    strength = min(c.lower_shadow / c.range, 1.0)
    if trend == "down":
        return Pattern("hammer", "bullish", strength, 1,
                       "sellers rejected after decline")
    if trend == "up":
        return Pattern("hanging_man", "bearish", strength * 0.8, 1,
                       "same shape as hammer, but after a rally — warning")
    return None


def _star_family(c: Candle, trend: str) -> Optional[Pattern]:
    """Long upper shadow, small body at the bottom of the range."""
    if c.body_pct > SMALL_BODY_MAX or c.body == 0:
        return None
    if c.upper_shadow < LONG_SHADOW_MIN * c.body:
        return None
    if c.lower_shadow > SHORT_SHADOW_MAX * c.range:
        return None
    strength = min(c.upper_shadow / c.range, 1.0)
    if trend == "up":
        return Pattern("shooting_star", "bearish", strength, 1,
                       "buyers rejected after rally")
    if trend == "down":
        return Pattern("inverted_hammer", "bullish", strength * 0.7, 1,
                       "failed push down, needs confirmation")
    return None


def _marubozu(c: Candle) -> Optional[Pattern]:
    if c.body_pct < MARUBOZU_BODY_MIN:
        return None
    d = "bullish" if c.is_bull else "bearish"
    return Pattern("marubozu", d, c.body_pct, 1, "conviction, no rejection wick")


# ── two-bar ──

def _engulfing(prev: Candle, cur: Candle) -> Optional[Pattern]:
    """Current real body fully engulfs the previous, opposite colour."""
    if prev.body == 0 or cur.body <= prev.body:
        return None
    cur_top, cur_bot = max(cur.open, cur.close), min(cur.open, cur.close)
    prev_top, prev_bot = max(prev.open, prev.close), min(prev.open, prev.close)
    if not (cur_top >= prev_top and cur_bot <= prev_bot):
        return None
    strength = min(cur.body / max(prev.body, 1e-9) / 3.0, 1.0)
    if prev.is_bear and cur.is_bull:
        return Pattern("bullish_engulfing", "bullish", strength, 2,
                       "buyers overwhelmed the prior down bar")
    if prev.is_bull and cur.is_bear:
        return Pattern("bearish_engulfing", "bearish", strength, 2,
                       "sellers overwhelmed the prior up bar")
    return None


def _harami(prev: Candle, cur: Candle) -> Optional[Pattern]:
    """Small body contained inside the previous large body — momentum stalling."""
    if prev.body == 0 or cur.body >= prev.body * 0.6:
        return None
    cur_top, cur_bot = max(cur.open, cur.close), min(cur.open, cur.close)
    prev_top, prev_bot = max(prev.open, prev.close), min(prev.open, prev.close)
    if not (cur_top <= prev_top and cur_bot >= prev_bot):
        return None
    strength = 1.0 - (cur.body / max(prev.body, 1e-9))
    if prev.is_bear and cur.is_bull:
        return Pattern("bullish_harami", "bullish", strength * 0.7, 2,
                       "downside momentum stalling")
    if prev.is_bull and cur.is_bear:
        return Pattern("bearish_harami", "bearish", strength * 0.7, 2,
                       "upside momentum stalling")
    return None


# ── three-bar ──

def _star_three(a: Candle, b: Candle, c: Candle) -> Optional[Pattern]:
    """Morning/Evening Star: strong bar, small indecisive bar, strong reversal."""
    if b.body_pct > SMALL_BODY_MAX and b.body_pct > DOJI_BODY_MAX:
        return None
    if a.body_pct < 0.4 or c.body_pct < 0.4:
        return None  # first and third must be decisive

    if a.is_bear and c.is_bull and c.close > a.midpoint:
        depth = (c.close - a.midpoint) / max(a.body, 1e-9)
        return Pattern("morning_star", "bullish", min(depth, 1.0), 3,
                       "three-bar bottom reversal")
    if a.is_bull and c.is_bear and c.close < a.midpoint:
        depth = (a.midpoint - c.close) / max(a.body, 1e-9)
        return Pattern("evening_star", "bearish", min(depth, 1.0), 3,
                       "three-bar top reversal")
    return None


def _three_soldiers_crows(a: Candle, b: Candle, c: Candle) -> Optional[Pattern]:
    """Three consecutive decisive bars in the same direction."""
    if all(x.is_bull and x.body_pct > 0.5 for x in (a, b, c)):
        if b.close > a.close and c.close > b.close:
            return Pattern("three_white_soldiers", "bullish", 0.8, 3,
                           "sustained accumulation")
    if all(x.is_bear and x.body_pct > 0.5 for x in (a, b, c)):
        if b.close < a.close and c.close < b.close:
            return Pattern("three_black_crows", "bearish", 0.8, 3,
                           "sustained distribution")
    return None


# ── public API ──

def detect(df: pd.DataFrame, trend: str = "sideways") -> list[Pattern]:
    """Patterns completing on the LAST bar of `df`.

    `trend` is the prevailing context (up/down/sideways) — several patterns
    are only meaningful in one direction and will not fire otherwise.
    Returns strongest first.
    """
    if df is None or len(df) < 3:
        return []

    a, b, c = _candles(df, 3)
    found: list[Optional[Pattern]] = [
        _engulfing(b, c),
        _harami(b, c),
        _star_three(a, b, c),
        _three_soldiers_crows(a, b, c),
        _hammer_family(c, trend),
        _star_family(c, trend),
        _marubozu(c),
        _doji(c),
    ]
    out = [p for p in found if p is not None]
    out.sort(key=lambda p: (-p.strength, -p.bars))
    return out


def summarise(patterns: list[Pattern]) -> dict[str, Any]:
    """Condense detections into a net bias the reasoning agent can weigh."""
    if not patterns:
        return {"patterns": [], "net_bias": "none", "net_score": 0.0}

    score = sum(
        p.strength * (1 if p.direction == "bullish" else -1 if p.direction == "bearish" else 0)
        for p in patterns
    )
    # Normalise against the count so a pile of weak signals can't dominate.
    score = round(max(min(score / max(len(patterns), 1), 1.0), -1.0), 3)
    bias = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "mixed"
    return {
        "patterns": [p.as_dict() for p in patterns],
        "net_bias": bias,
        "net_score": score,
    }
