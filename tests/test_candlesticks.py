"""Candlestick detection tests on hand-built OHLC bars.

Every fixture is constructed by hand so the expected pattern is unambiguous.
The context tests matter most: the same shape must read bullish or bearish
depending on the prevailing trend, and a detector that ignores that produces
confident nonsense.
"""
import pandas as pd
import pytest

from app.strategies.candlesticks import Candle, detect, summarise


def _df(bars: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """bars = [(open, high, low, close), ...]"""
    return pd.DataFrame(bars, columns=["Open", "High", "Low", "Close"])


def _names(patterns) -> set[str]:
    return {p.name for p in patterns}


# ── candle geometry ──

def test_candle_geometry():
    c = Candle(open=100, high=110, low=90, close=105)
    assert c.body == 5
    assert c.range == 20
    assert c.upper_shadow == 5      # 110 - max(100,105)
    assert c.lower_shadow == 10     # min(100,105) - 90
    assert c.is_bull is True
    assert c.body_pct == pytest.approx(0.25)


# ── context dependence (the important ones) ──

def test_hammer_is_bullish_after_a_decline():
    # Small body at top, long lower shadow.
    bars = [(100, 101, 99, 100), (99, 100, 98, 99), (95, 96, 88, 95.5)]
    got = detect(_df(bars), trend="down")
    assert "hammer" in _names(got)
    assert next(p for p in got if p.name == "hammer").direction == "bullish"


def test_same_shape_is_a_bearish_hanging_man_after_a_rally():
    """Identical candle, opposite meaning — this is why trend is a parameter."""
    bars = [(100, 101, 99, 100), (99, 100, 98, 99), (95, 96, 88, 95.5)]
    got = detect(_df(bars), trend="up")
    assert "hanging_man" in _names(got)
    assert next(p for p in got if p.name == "hanging_man").direction == "bearish"
    assert "hammer" not in _names(got)


def test_hammer_does_not_fire_sideways():
    bars = [(100, 101, 99, 100), (99, 100, 98, 99), (95, 96, 88, 95.5)]
    got = _names(detect(_df(bars), trend="sideways"))
    assert "hammer" not in got and "hanging_man" not in got


def test_shooting_star_only_after_a_rally():
    # Small body at bottom, long upper shadow.
    bars = [(90, 91, 89, 90), (92, 93, 91, 92), (100, 112, 99.5, 100.5)]
    assert "shooting_star" in _names(detect(_df(bars), trend="up"))
    assert "inverted_hammer" in _names(detect(_df(bars), trend="down"))


# ── two-bar ──

def test_bullish_engulfing():
    bars = [(100, 101, 99, 100), (100, 100.5, 96, 96.5), (95, 103, 94.5, 102)]
    got = detect(_df(bars), trend="down")
    assert "bullish_engulfing" in _names(got)


def test_bearish_engulfing():
    bars = [(100, 101, 99, 100), (96.5, 100.5, 96, 100), (102, 102.5, 94, 95)]
    got = detect(_df(bars), trend="up")
    assert "bearish_engulfing" in _names(got)


def test_engulfing_requires_opposite_colours():
    # Both bullish, second larger — larger body but NOT an engulfing pattern.
    bars = [(100, 101, 99, 100), (96, 100, 95, 99), (94, 104, 93, 103)]
    assert "bullish_engulfing" not in _names(detect(_df(bars), trend="down"))


def test_engulfing_requires_full_containment():
    # Second body is bigger but does not cover the first.
    bars = [(100, 101, 99, 100), (100, 101, 96, 96.5), (98, 99.5, 97, 99.4)]
    assert "bullish_engulfing" not in _names(detect(_df(bars), trend="down"))


def test_bullish_harami():
    bars = [(110, 111, 109, 110), (110, 110.5, 100, 100.5), (103, 105, 102.5, 105)]
    assert "bullish_harami" in _names(detect(_df(bars), trend="down"))


# ── three-bar ──

def test_morning_star():
    bars = [(110, 110.5, 100, 100.5), (99, 100, 98, 99.2), (100, 108, 99.5, 107)]
    got = detect(_df(bars), trend="down")
    assert "morning_star" in _names(got)
    assert next(p for p in got if p.name == "morning_star").direction == "bullish"


def test_evening_star():
    bars = [(100, 110.5, 99.5, 110), (111, 112, 110, 111.2), (110, 110.5, 101, 102)]
    got = detect(_df(bars), trend="up")
    assert "evening_star" in _names(got)


def test_three_white_soldiers():
    bars = [(100, 106, 99.5, 105), (105, 111, 104.5, 110), (110, 116, 109.5, 115)]
    assert "three_white_soldiers" in _names(detect(_df(bars), trend="up"))


def test_three_black_crows():
    bars = [(115, 115.5, 109, 110), (110, 110.5, 104, 105), (105, 105.5, 99, 100)]
    assert "three_black_crows" in _names(detect(_df(bars), trend="down"))


# ── doji ──

def test_doji_is_neutral():
    bars = [(100, 101, 99, 100), (100, 101, 99, 100), (100, 105, 95, 100.1)]
    got = detect(_df(bars), trend="sideways")
    doji = next(p for p in got if "doji" in p.name)
    assert doji.direction == "neutral"


def test_dragonfly_and_gravestone_have_direction():
    dragonfly = [(100, 101, 99, 100)] * 2 + [(100, 100.2, 90, 100.1)]
    assert "dragonfly_doji" in _names(detect(_df(dragonfly), trend="sideways"))
    gravestone = [(100, 101, 99, 100)] * 2 + [(100, 110, 99.9, 100.1)]
    assert "gravestone_doji" in _names(detect(_df(gravestone), trend="sideways"))


# ── robustness ──

def test_scale_invariance():
    """Same shape at Rs 100 and Rs 24,000 must detect identically."""
    small = [(100, 101, 99, 100), (100, 100.5, 96, 96.5), (95, 103, 94.5, 102)]
    big = [(v * 240 for v in bar) for bar in small]
    a = _names(detect(_df(small), trend="down"))
    b = _names(detect(_df([tuple(x) for x in big]), trend="down"))
    assert a == b


def test_insufficient_bars_returns_empty():
    assert detect(_df([(100, 101, 99, 100)]), trend="up") == []
    assert detect(None, trend="up") == []


def test_flat_bar_does_not_crash():
    bars = [(100, 100, 100, 100)] * 3
    detect(_df(bars), trend="up")  # must not raise


def test_summarise_nets_opposing_signals():
    assert summarise([])["net_bias"] == "none"
    got = detect(_df([(110, 111, 109, 110), (110, 110.5, 100, 100.5), (103, 105, 102.5, 105)]),
                 trend="down")
    s = summarise(got)
    assert s["net_score"] > 0
    assert s["net_bias"] == "bullish"
    assert -1.0 <= s["net_score"] <= 1.0
