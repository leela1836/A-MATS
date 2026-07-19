"""Performance metrics over a BacktestResult.

Sharpe is annualised from daily equity returns using 252 trading days. With
few trades these figures are statistically weak — `sample_warning` flags that
explicitly rather than letting a flattering number stand unqualified.
"""
from __future__ import annotations

import math
from typing import Any

from app.backtester.engine import BacktestResult

TRADING_DAYS = 252
MIN_MEANINGFUL_TRADES = 20


def analyse(result: BacktestResult) -> dict[str, Any]:
    trades = result.trades
    curve = [p["equity"] for p in result.equity_curve]
    start = result.starting_equity
    end = curve[-1] if curve else start

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))

    metrics: dict[str, Any] = {
        "symbol": result.symbol,
        "period": f"{result.start_date} → {result.end_date}",
        "bars": result.bars,
        "starting_equity": round(start, 2),
        "ending_equity": round(end, 2),
        "total_return_pct": round((end / start - 1) * 100, 3) if start else 0.0,
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 2) if trades else 0.0,
        "avg_win": round(gross_profit / len(wins), 2) if wins else 0.0,
        "avg_loss": round(-gross_loss / len(losses), 2) if losses else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else None,
        "max_drawdown_pct": round(_max_drawdown(curve), 3),
        "sharpe": _sharpe(curve),
        "exit_breakdown": _exit_breakdown(trades),
        "avg_bars_held": round(sum(t.bars_held for t in trades) / len(trades), 1) if trades else 0.0,
    }

    metrics["signals_seen"] = result.signals_seen
    metrics["skipped_no_size"] = result.skipped_no_size

    # A zero-trade run must say WHY, or it reads as "the strategy found
    # nothing" when the real cause is that sizing rounded down to zero units.
    if not trades and result.skipped_no_size:
        metrics["sizing_warning"] = (
            f"{result.skipped_no_size} signals were skipped because the "
            f"position size rounded to 0 units — the instrument's unit price "
            f"exceeds the per-trade budget. Raise position_sizing."
            f"default_size_percent or trade a cheaper instrument."
        )
    elif result.skipped_no_size:
        metrics["sizing_warning"] = (
            f"{result.skipped_no_size} signals skipped (size rounded to 0 units)."
        )

    if len(trades) < MIN_MEANINGFUL_TRADES:
        metrics["sample_warning"] = (
            f"Only {len(trades)} trades — too few to be statistically meaningful. "
            f"Treat these figures as directional, not evidence."
        )
    return metrics


def _max_drawdown(curve: list[float]) -> float:
    """Largest peak-to-trough decline, as a positive percentage."""
    peak, worst = float("-inf"), 0.0
    for v in curve:
        peak = max(peak, v)
        if peak > 0:
            worst = min(worst, (v - peak) / peak)
    return abs(worst) * 100


def _sharpe(curve: list[float]) -> float | None:
    """Annualised Sharpe of daily equity returns (risk-free rate assumed 0)."""
    if len(curve) < 3:
        return None
    rets = [
        (curve[i] - curve[i - 1]) / curve[i - 1]
        for i in range(1, len(curve))
        if curve[i - 1]
    ]
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return None
    return round(mean / sd * math.sqrt(TRADING_DAYS), 3)


def _exit_breakdown(trades) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in trades:
        out[t.exit_reason] = out.get(t.exit_reason, 0) + 1
    return out
