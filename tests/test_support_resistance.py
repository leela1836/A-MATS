"""Support/resistance tests on hand-built bars where the levels are obvious."""
import pandas as pd

from app.strategies.support_resistance import (
    Level,
    detect_levels,
    nearest,
    summarise,
)


def _df(bars: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(bars, columns=["Open", "High", "Low", "Close"])


def _ramp_with_pivots() -> pd.DataFrame:
    """A series that puts clear swing highs near 110 and swing lows near 90,
    each tested twice, with the last close sitting at 100 in between."""
    o = 100.0
    seq = [
        (o, 105, 99, 104), (o, 108, 103, 107), (o, 110, 106, 108),  # swing high ~110
        (o, 107, 101, 102), (o, 100, 94, 96), (o, 95, 90, 91),      # swing low ~90
        (o, 96, 91, 95), (o, 103, 94, 102), (o, 109, 104, 108),     # back up
        (o, 111, 107, 109), (o, 108, 100, 101), (o, 99, 93, 94),    # swing high ~111, low ~93
        (o, 98, 92, 97), (o, 101, 96, 100),                          # settle at 100
    ]
    return _df(seq)


def test_detects_support_below_and_resistance_above():
    df = _ramp_with_pivots()
    levels = detect_levels(df, ref_price=100.0)
    assert levels, "expected some levels"
    kinds = {l.kind for l in levels}
    assert "support" in kinds and "resistance" in kinds
    # supports sit below the reference, resistances above.
    for l in levels:
        if l.kind == "support":
            assert l.price < 100.0
        else:
            assert l.price > 100.0


def test_nearest_brackets_the_price():
    df = _ramp_with_pivots()
    levels = detect_levels(df, ref_price=100.0)
    support, resistance = nearest(levels, 100.0)
    assert support is not None and support.price < 100.0
    assert resistance is not None and resistance.price > 100.0


def test_repeated_touches_increase_strength():
    # Two distinct swing lows in the same ~50 zone (50.0 and 50.2) must cluster
    # into ONE level of strength 2. Distinct, not tied — strict fractals require
    # a genuine turning point, and near-equal touches are what makes a zone.
    lows = [60, 58, 55, 52, 50.0, 53, 56, 59, 57, 54, 50.2, 53, 56, 59, 61]
    bars = [(lo + 1, lo + 4, lo, lo + 2) for lo in lows]
    levels = detect_levels(_df(bars), ref_price=60.0)
    support_strengths = [l.strength for l in levels if l.kind == "support"]
    assert support_strengths and max(support_strengths) >= 2


def test_level_on_the_price_is_dropped():
    df = _ramp_with_pivots()
    # Reference exactly on a pivot cluster (~110) must not report that as a level.
    levels = detect_levels(df, ref_price=110.0)
    assert all(abs(l.price - 110.0) / 110.0 >= 0.004 for l in levels)


def test_scale_invariance():
    small = _ramp_with_pivots()
    big = small.copy()
    big[["Open", "High", "Low", "Close"]] *= 35.0
    a = {l.kind for l in detect_levels(small, ref_price=100.0)}
    b = {l.kind for l in detect_levels(big, ref_price=3500.0)}
    assert a == b  # same structure regardless of price scale


def test_too_few_bars_returns_empty():
    assert detect_levels(_df([(1, 2, 0.5, 1)]), ref_price=1.0) == []
    assert detect_levels(None, ref_price=1.0) == []


def test_summarise_shape():
    s = summarise(_ramp_with_pivots(), ref_price=100.0)
    assert set(s) == {"levels", "support", "resistance", "support_strength", "resistance_strength"}
    assert isinstance(s["levels"], list)
    if s["support"] is not None:
        assert s["support"] < 100.0
    if s["resistance"] is not None:
        assert s["resistance"] > 100.0
