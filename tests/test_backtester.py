"""Backtester tests on synthetic price series — deterministic and offline.

The lookahead test is the important one: a backtest that peeks at future
bars produces beautiful, worthless numbers.
"""
import math

import numpy as np
import pandas as pd
import pytest

from app.backtester.analytics import _max_drawdown, _sharpe, analyse
from app.backtester.engine import WARMUP_BARS, run_backtest


def _frame(closes: list[float], spread: float = 0.01) -> pd.DataFrame:
    """Build an OHLCV frame from a close series."""
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="B")
    closes_arr = np.array(closes, dtype=float)
    return pd.DataFrame(
        {
            "Open": closes_arr * (1 - spread / 2),
            "High": closes_arr * (1 + spread),
            "Low": closes_arr * (1 - spread),
            "Close": closes_arr,
            "Volume": np.full(len(closes), 1_000_000),
        },
        index=idx,
    )


def _uptrend(n=260, start=100.0, step=0.4):
    # Gentle drift plus a deterministic wiggle so ATR is non-zero.
    return [start + i * step + (2.0 if i % 7 == 0 else 0.0) for i in range(n)]


def _wave(n=400, base=100.0, amp=0.15, period=55):
    """Cyclical series that actually triggers entries.

    A monotonic ramp pins RSI above the 68 cut-off forever, so classify()
    returns HOLD for every bar and the backtest does nothing — which made
    earlier assertions pass vacuously over empty trade lists. This oscillates
    so EMA20 crosses EMA50 repeatedly while RSI travels the mid range.
    """
    out = []
    for i in range(n):
        cycle = math.sin(2 * math.pi * i / period)
        wobble = 0.012 * math.sin(2 * math.pi * i / 6.0)  # intra-cycle noise
        out.append(base * (1 + amp * cycle + wobble))
    return out


def _assert_trades(res, why=""):
    """Guard against vacuous assertions over an empty trade list."""
    assert res.trades, f"fixture generated no trades — assertion would be vacuous {why}"
    return res


def test_runs_and_reports_period():
    df = _frame(_wave())
    res = run_backtest("TEST.NS", df=df, starting_equity=1_000_000)
    assert res.bars == len(df) - WARMUP_BARS
    assert len(res.equity_curve) == res.bars
    assert res.starting_equity == 1_000_000
    _assert_trades(res)


def test_monotonic_ramp_produces_no_trades():
    """Documents why _wave exists: a pure ramp pins RSI above the cut-off,
    so classify() holds forever and any assertion on trades is vacuous."""
    res = run_backtest("TEST.NS", df=_frame(_uptrend()), starting_equity=1_000_000)
    assert res.signals_seen == 0
    assert res.trades == []


def test_rejects_insufficient_history():
    with pytest.raises(ValueError, match="need >"):
        run_backtest("TEST.NS", df=_frame(_uptrend(n=20)))


def test_no_lookahead_future_bars_cannot_change_the_past():
    """Appending future bars must not alter already-closed trades.

    If the engine peeked ahead, extending the series would retroactively
    change decisions made earlier.
    """
    base = _wave(n=300)
    short = _assert_trades(
        run_backtest("TEST.NS", df=_frame(base), starting_equity=1_000_000),
        "— lookahead test must compare real trades",
    )

    # Same history, then a violent crash appended AFTER the original window.
    extended_closes = base + [base[-1] * 0.5 - i for i in range(60)]
    extended = run_backtest("TEST.NS", df=_frame(extended_closes), starting_equity=1_000_000)

    # Every trade that closed within the original window must be identical.
    cutoff = short.equity_curve[-1]["date"]
    a = [t for t in short.trades if t.exit_date <= cutoff]
    b = [t for t in extended.trades if t.exit_date <= cutoff]
    assert a, "no closed trades in window — comparison would be vacuous"
    assert len(a) == len(b), "future data changed how many trades closed in the past"
    for x, y in zip(a, b):
        assert (x.entry_date, x.entry_price, x.exit_date, x.exit_price) == (
            y.entry_date, y.entry_price, y.exit_date, y.exit_price
        ), "future data altered a past trade — lookahead bias"


def test_entry_never_fills_at_the_signal_bar_close():
    """Fills happen at the NEXT bar's open, never the observed close."""
    df = _frame(_wave())
    res = _assert_trades(run_backtest("TEST.NS", df=df, starting_equity=1_000_000))
    closes = {str(d.date()): float(c) for d, c in zip(df.index, df["Close"])}
    for t in res.trades:
        # Entry price comes from an open (+slippage), so it should not equal
        # that same date's close.
        assert t.entry_price != pytest.approx(closes.get(t.entry_date, -1)), (
            "entry filled at the signal bar's close — lookahead"
        )


def test_stop_assumed_before_target_when_bar_straddles_both():
    from app.backtester.engine import OpenPosition, _check_exit
    from app.models.state import Direction

    pos = OpenPosition(
        direction=Direction.LONG, entry_price=100.0, entry_date="2024-01-01",
        entry_index=0, qty=10, stop=95.0, target=110.0,
    )
    bar = {"High": 115.0, "Low": 90.0}  # hits both
    price, reason = _check_exit(pos, bar)
    assert reason == "stop", "must assume the pessimistic fill"
    assert price == 95.0


def test_zero_trades_explains_itself_when_sizing_rounds_down():
    """A signal-rich series priced above the per-trade budget must not
    silently report 'no trades' — it must say sizing was the cause."""
    # Same signal-generating shape, but each unit costs ~50k while the 2%
    # per-trade budget on 100k equity is only 2k -> qty rounds to 0.
    df = _frame(_wave(base=50_000))
    res = run_backtest("PRICEY.NS", df=df, starting_equity=100_000)
    assert res.trades == []
    assert res.signals_seen > 0, "fixture should generate signals"
    assert res.skipped_no_size > 0
    m = analyse(res)
    assert "sizing_warning" in m
    assert "rounded to 0 units" in m["sizing_warning"]


def test_commission_and_slippage_are_charged():
    """A flat market should still lose money to costs, never gain."""
    flat = _frame([100.0] * 260, spread=0.0)
    res = run_backtest("TEST.NS", df=flat, starting_equity=1_000_000)
    assert res.equity_curve[-1]["equity"] <= 1_000_000


# ── analytics ──

def test_max_drawdown():
    assert _max_drawdown([100, 120, 60, 80]) == pytest.approx(50.0)
    assert _max_drawdown([100, 110, 120]) == pytest.approx(0.0)


def test_sharpe_none_on_flat_curve():
    assert _sharpe([100.0] * 10) is None


def test_analyse_flags_small_samples():
    res = _assert_trades(
        run_backtest("TEST.NS", df=_frame(_wave()), starting_equity=1_000_000)
    )
    metrics = analyse(res)
    assert "win_rate_pct" in metrics
    assert "max_drawdown_pct" in metrics
    assert metrics["total_trades"] < 20  # the wave fixture is deliberately small
    assert "sample_warning" in metrics, "small samples must be flagged, not hidden"


def test_win_rate_and_profit_factor_consistent():
    res = _assert_trades(
        run_backtest("TEST.NS", df=_frame(_wave()), starting_equity=1_000_000)
    )
    m = analyse(res)
    assert m["total_trades"] > 0
    assert m["wins"] + m["losses"] <= m["total_trades"]  # break-evens allowed
    assert 0.0 <= m["win_rate_pct"] <= 100.0
    # Win rate must agree with the underlying trade list, not be computed loose.
    assert m["wins"] == sum(1 for t in res.trades if t.pnl > 0)
    assert m["win_rate_pct"] == pytest.approx(
        m["wins"] / m["total_trades"] * 100, abs=0.01
    )
