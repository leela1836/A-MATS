"""Upstox collector tests — offline (no network): candle parsing + symbol map."""
import pandas as pd

import app.collectors.upstox_collector as ux


def test_candles_to_df_shape_and_order():
    # Upstox returns candles newest-first; we must sort ascending and shape them
    # like yfinance (Open/High/Low/Close/Volume, DatetimeIndex).
    candles = [
        ["2025-01-03T00:00:00+05:30", 102.0, 103.0, 101.0, 102.5, 2000, 0],
        ["2025-01-02T00:00:00+05:30", 100.0, 101.5, 99.5, 101.0, 1500, 0],
        ["2025-01-01T00:00:00+05:30", 99.0, 100.0, 98.0, 99.5, 1000, 0],
    ]
    df = ux._candles_to_df(candles)
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.is_monotonic_increasing            # oldest first
    assert df["Close"].iloc[-1] == 102.5               # newest last
    assert df["Open"].dtype == float and len(df) == 3


def test_instrument_key_maps_and_strips_suffix(monkeypatch):
    monkeypatch.setattr(ux, "_instr_map", {
        "RELIANCE": "NSE_EQ|INE002A01018",
        "TCS": "NSE_EQ|INE467B01029",
    })
    assert ux.instrument_key("RELIANCE.NS") == "NSE_EQ|INE002A01018"
    assert ux.instrument_key("tcs.ns") == "NSE_EQ|INE467B01029"
    assert ux.instrument_key("NOTLISTED.NS") is None


def test_have_token_reflects_env(monkeypatch):
    monkeypatch.delenv(ux.TOKEN_ENV, raising=False)
    assert ux.have_token() is False
    monkeypatch.setenv(ux.TOKEN_ENV, "abc123")
    assert ux.have_token() is True


def test_fetch_requires_token(monkeypatch):
    monkeypatch.delenv(ux.TOKEN_ENV, raising=False)
    try:
        ux.fetch_history_upstox("RELIANCE.NS")
        assert False, "should raise without a token"
    except RuntimeError as e:
        assert "UPSTOX_ACCESS_TOKEN" in str(e)
