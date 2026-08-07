"""Strategy library + router: liquidity gate, per-strategy firing, regime rule."""
import numpy as np
import pandas as pd
import pytest

from app.strategies.library import MIN_TURNOVER, build_context, classify_strategy, route


def _df(close, volume=2_000_000.0, n=260):
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    c = np.asarray(close, dtype=float)
    return pd.DataFrame(
        {"Open": c, "High": c + 1, "Low": c - 1, "Close": c, "Volume": volume}, index=idx,
    )


def _ctx(df, ind, trend, regime, support=None, resistance=None):
    return build_context("X.NS", df, ind, trend, regime, support, resistance)


def test_liquidity_gate_blocks_thin_names():
    df = _df(np.linspace(100, 150, 260), volume=500.0)   # tiny turnover
    ctx = _ctx(df, {"last_price": 150, "rsi_14": 60, "atr_14": 2,
                    "ema_20": 148, "ema_50": 145, "ema_200": 130}, "up", "bull")
    assert ctx.avg_turnover < MIN_TURNOVER
    assert route(ctx, "long") is None       # gated purely on liquidity


def test_trend_following_fires_in_uptrend():
    df = _df(np.linspace(100, 150, 260))
    ctx = _ctx(df, {"last_price": 150, "rsi_14": 60, "atr_14": 2,
                    "ema_20": 148, "ema_50": 145, "ema_200": 130}, "up", "bull")
    sig = route(ctx, "long")
    assert sig is not None and sig.strategy == "trend_following"
    assert sig.stop < sig.entry < sig.target      # sane long levels


def test_mean_reversion_fires_oversold_at_support():
    df = _df(np.full(260, 100.0))
    ctx = _ctx(df, {"last_price": 100, "rsi_14": 25, "atr_14": 2,
                    "ema_20": 101, "ema_50": 102, "ema_200": 103},
               "sideways", "neutral", support=99.0)
    sig = route(ctx, "long")
    assert sig is not None and sig.strategy == "mean_reversion"


def test_breakout_needs_a_volume_surge():
    vol = np.full(260, 1_000_000.0)
    vol[-1] = 5_000_000.0                          # today's surge
    df = _df(np.full(260, 100.0))
    df["Volume"] = vol
    ctx = _ctx(df, {"last_price": 100, "rsi_14": 55, "atr_14": 2,
                    "ema_20": 99, "ema_50": 98, "ema_200": 97},
               "up", "bull", resistance=99.0)      # price above resistance
    sig = route(ctx, "long")
    assert sig is not None and sig.strategy == "breakout"


def test_candlestick_pattern_is_a_routable_strategy():
    """A strong bullish engulfing on the last bar fires the candlestick strategy."""
    from app.strategies.library.strategies import CandlestickPattern

    n = 60
    o = np.full(n, 100.0); c = np.full(n, 100.0)
    h = np.full(n, 101.0); l = np.full(n, 99.0)
    o[-2], c[-2], h[-2], l[-2] = 105.0, 100.0, 106.0, 99.0   # prior bearish bar
    o[-1], c[-1], h[-1], l[-1] = 99.0, 106.0, 107.0, 98.0    # bullish bar engulfs it
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    df = pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 2_000_000.0}, index=idx)
    ctx = _ctx(df, {"last_price": 106.0, "rsi_14": 55, "atr_14": 2,
                    "ema_20": 103, "ema_50": 102, "ema_200": 100}, "sideways", "neutral", support=99.0)
    sig = CandlestickPattern().evaluate(ctx)
    assert sig is not None and sig.direction == "long" and sig.strategy == "candlestick"
    assert route(ctx, "long").strategy == "candlestick"   # and the router picks it


def test_shorts_gated_outside_a_bear_regime():
    df = _df(np.linspace(150, 100, 260))           # downtrend
    ind = {"last_price": 100, "rsi_14": 40, "atr_14": 2,
           "ema_20": 102, "ema_50": 105, "ema_200": 120}
    assert route(_ctx(df, ind, "down", "bull"), "short") is None     # bull → no shorts
    assert route(_ctx(df, ind, "down", "neutral"), "short") is None  # neutral → no shorts
    assert route(_ctx(df, ind, "down", "bear"), "short") is not None # bear → allowed


def test_strategy_lab_backtests_all_strategies():
    """The validation backtester runs each library strategy and reports its edge."""
    from app.backtester.strategy_lab import backtest

    r = backtest(symbols=["A.NS", "B.NS"], period="2y")  # conftest stubs the data
    assert set(r["strategies"]) == {"trend_following", "breakout", "candlestick", "mean_reversion"}
    for a in r["strategies"].values():
        assert "trades" in a and "win_rate" in a and "avg" in a


def test_roster_promotes_and_demotes_on_live_edge(tmp_path, monkeypatch):
    """A shadow strategy that proves positive live is promoted; a live one that
    goes negative is benched — governance runs on out-of-sample results, not vibes."""
    from app.journal.store import Journal
    from app.strategies.library import roster

    monkeypatch.setattr(roster, "ROSTER_FILE", tmp_path / "roster.json")
    j = Journal(path=tmp_path / "j.db")

    def add(strategy, pnl, n):
        for _ in range(n):
            did = j.record_decision("s", "X.NS", {
                "direction": "long", "strategy": strategy, "entry_price": 100.0})
            j.close_decision(did, 100.0 + pnl, "win" if pnl > 0 else "loss", pnl)

    add("mean_reversion", 3.0, 35)     # clearly positive net of costs
    add("trend_following", -3.0, 35)   # clearly negative
    r = roster.evaluate_and_update(journal=j, save=True)
    assert r["mean_reversion"]["status"] == "live"      # promoted
    assert r["trend_following"]["status"] == "benched"  # demoted
    assert roster.is_tradable("candlestick") is False   # validated loser stays benched


def test_classify_strategy_always_returns_a_name():
    df = _df(np.full(260, 100.0))
    ctx = _ctx(df, {"last_price": 100, "rsi_14": 50, "atr_14": 2,
                    "ema_20": 100, "ema_50": 100, "ema_200": 100}, "sideways", "neutral")
    assert classify_strategy(ctx, "long") == "trend_following"   # fallback when nothing fits
