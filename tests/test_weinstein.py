"""Weinstein Stage-Analysis signal tests on synthetic multi-year series."""
import numpy as np
import pandas as pd

from app.models.state import Direction
from app.strategies.weinstein import weinstein_signal


def _df(close, volume, last_vol=None):
    close = np.asarray(close, dtype=float)
    high = close + 0.5
    low = close - 0.5
    vol = np.full(len(close), volume, dtype=float)
    if last_vol is not None:
        vol[-1] = last_vol
    return pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": vol})


def test_stage2_breakout_on_volume_is_long():
    # 180 bars rising steadily → MA rising, price above MA, each bar a new high.
    close = np.linspace(100, 200, 180)
    df = _df(close, volume=1e6, last_vol=3e6)  # volume expansion on the breakout
    trend, sig, conf = weinstein_signal(df)
    assert sig == Direction.LONG
    assert trend == "up" and conf > 0.5


def test_breakout_without_volume_is_hold():
    close = np.linspace(100, 200, 180)
    df = _df(close, volume=1e6, last_vol=1e6)  # no expansion → Weinstein waits
    _, sig, _ = weinstein_signal(df)
    assert sig == Direction.HOLD


def test_stage4_breakdown_on_volume_is_short():
    close = np.linspace(200, 100, 180)  # steady decline → MA falling, new lows
    df = _df(close, volume=1e6, last_vol=3e6)
    trend, sig, _ = weinstein_signal(df)
    assert sig == Direction.SHORT and trend == "down"


def test_short_can_be_disabled():
    close = np.linspace(200, 100, 180)
    df = _df(close, volume=1e6, last_vol=3e6)
    _, sig, _ = weinstein_signal(df, {"wein_allow_short": False})
    assert sig == Direction.HOLD


def test_sideways_chop_is_hold():
    rng = np.random.default_rng(0)
    close = 100 + rng.standard_normal(180) * 0.5  # flat MA, no trend, no breakout
    df = _df(close, volume=1e6, last_vol=3e6)
    _, sig, _ = weinstein_signal(df)
    assert sig == Direction.HOLD


def test_insufficient_history_is_hold():
    df = _df(np.linspace(100, 120, 60), volume=1e6)
    _, sig, conf = weinstein_signal(df)
    assert sig == Direction.HOLD and conf == 0.2
