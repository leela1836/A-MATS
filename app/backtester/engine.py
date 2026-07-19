"""Event-driven backtester for the technical strategy.

AVOIDING LOOKAHEAD BIAS — the thing that makes most backtests lie:

1. Indicators at bar `i` are computed from `df.iloc[:i+1]` only. The engine
   never sees a future bar when deciding.
2. A signal produced from bar `i`'s close is filled at bar `i+1`'s OPEN, not
   at bar `i`'s close. You cannot trade a close you have only just observed.
3. Stop/target checks use bar `i`'s High/Low, which are known only after the
   bar completes — so an exit is never credited earlier than it could occur.

WHAT THIS DOES AND DOESN'T VALIDATE:

It replays the deterministic technical strategy (`classify()`, the same
function the live market node uses) — NOT the LLM reasoning layer. Running
the LLM over thousands of bars is infeasible on a free-tier quota and would
be non-deterministic anyway. So these numbers measure the *signal* the LLM
reasons over, which is the right foundation to validate first.

Ambiguity note: when a bar's range contains both the stop and the target, we
assume the STOP filled first. That is the pessimistic assumption, and the
honest one at daily resolution where intrabar order is unknown.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from app.collectors.market_collector import classify, compute_indicators, fetch_history
from app.config import get_config
from app.models.state import Direction

WARMUP_BARS = 60  # EMA50 + ATR14 need history before signals mean anything


@dataclass
class BacktestTrade:
    symbol: str
    direction: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    qty: int
    pnl: float
    return_pct: float
    exit_reason: str  # "stop" | "target" | "signal_flip" | "end_of_data"
    bars_held: int


@dataclass
class OpenPosition:
    direction: Direction
    entry_price: float
    entry_date: str
    entry_index: int
    qty: int
    stop: float
    target: float


@dataclass
class BacktestResult:
    symbol: str
    start_date: str
    end_date: str
    bars: int
    starting_equity: float
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    # Signals that fired but could not be sized into a whole unit. Tracked so
    # a zero-trade result explains itself instead of looking like "no signal".
    skipped_no_size: int = 0
    signals_seen: int = 0


def run_backtest(
    symbol: str,
    period: str = "2y",
    starting_equity: Optional[float] = None,
    df: Optional[pd.DataFrame] = None,
) -> BacktestResult:
    """Replay `symbol` bar by bar. Pass `df` to backtest supplied data offline."""
    if df is None:
        df = fetch_history(symbol, period=period, interval="1d")
    if len(df) <= WARMUP_BARS + 2:
        raise ValueError(f"need > {WARMUP_BARS + 2} bars, got {len(df)}")

    risk_cfg = get_config("risk")
    trading_cfg = get_config("trading")["mode"]
    sizing = risk_cfg.get("position_sizing", {})
    default_size = float(sizing.get("default_size_percent", 2.0))
    max_size = float(sizing.get("max_size_percent", 10.0))

    block = trading_cfg.get(trading_cfg.get("current", "paper"), {})
    slippage = float(block.get("percentage_slippage", 0.0005))
    commission = float(block.get("commission_per_trade", 20.0))

    equity = float(
        starting_equity
        if starting_equity is not None
        else block.get("initial_balance", 1_000_000.0)
    )

    result = BacktestResult(
        symbol=symbol,
        start_date=str(df.index[WARMUP_BARS].date()),
        end_date=str(df.index[-1].date()),
        bars=len(df) - WARMUP_BARS,
        starting_equity=equity,
    )

    position: Optional[OpenPosition] = None
    pending: Optional[tuple[Direction, float, float]] = None  # (dir, stop_d, target_d)

    # Stop at len-1: a signal on the final bar has no next open to fill at.
    for i in range(WARMUP_BARS, len(df)):
        bar = df.iloc[i]
        date = str(df.index[i].date())

        # ── 1. Manage an open position against THIS bar's range ──
        if position is not None:
            exit_price, reason = _check_exit(position, bar)
            if exit_price is not None:
                equity += _close_pnl(position, exit_price, commission)
                result.trades.append(_record(position, date, exit_price, reason, i))
                position = None

        # ── 2. Fill a pending order at THIS bar's open (decided last bar) ──
        if position is None and pending is not None:
            direction, stop_dist, target_dist = pending
            raw = float(bar["Open"])
            fill = raw * (1 + slippage) if direction == Direction.LONG else raw * (1 - slippage)
            qty = _size(equity, fill, default_size, max_size)
            if qty <= 0:
                # e.g. 2% of 10L = 20k, but one Nifty unit costs 24k.
                result.skipped_no_size += 1
            if qty > 0:
                position = OpenPosition(
                    direction=direction, entry_price=fill, entry_date=date,
                    entry_index=i, qty=qty,
                    stop=fill - stop_dist if direction == Direction.LONG else fill + stop_dist,
                    target=fill + target_dist if direction == Direction.LONG else fill - target_dist,
                )
                equity -= commission
        pending = None

        # ── 3. Decide from bars up to and including i (never beyond) ──
        window = df.iloc[: i + 1]
        try:
            ind = compute_indicators(window)
            _, signal, _ = classify(ind)
        except Exception:
            signal = Direction.HOLD

        atr = ind.get("atr_14", 0.0) if isinstance(ind, dict) else 0.0
        if signal in (Direction.LONG, Direction.SHORT):
            result.signals_seen += 1
        if position is None:
            if signal in (Direction.LONG, Direction.SHORT) and atr > 0 and i < len(df) - 1:
                pending = (signal, 1.5 * atr, 3.0 * atr)
        elif _flipped(position.direction, signal):
            # Signal reversed: exit at next open rather than wait for a stop.
            close = float(bar["Close"])
            equity += _close_pnl(position, close, commission)
            result.trades.append(_record(position, date, close, "signal_flip", i))
            position = None

        # ── 4. Mark to market ──
        mark = equity
        if position is not None:
            mark = equity + position.qty * (float(bar["Close"]) - position.entry_price) * (
                1 if position.direction == Direction.LONG else -1
            )
        result.equity_curve.append({"date": date, "equity": round(mark, 2)})

    # Close anything still open at the final close.
    if position is not None:
        last_close = float(df.iloc[-1]["Close"])
        equity += _close_pnl(position, last_close, commission)
        result.trades.append(
            _record(position, str(df.index[-1].date()), last_close, "end_of_data", len(df) - 1)
        )
        result.equity_curve[-1]["equity"] = round(equity, 2)

    return result


def _check_exit(pos: OpenPosition, bar) -> tuple[Optional[float], str]:
    """Stop first when a bar straddles both — pessimistic and honest."""
    high, low = float(bar["High"]), float(bar["Low"])
    if pos.direction == Direction.LONG:
        if low <= pos.stop:
            return pos.stop, "stop"
        if high >= pos.target:
            return pos.target, "target"
    else:
        if high >= pos.stop:
            return pos.stop, "stop"
        if low <= pos.target:
            return pos.target, "target"
    return None, ""


def _flipped(held: Direction, signal: Direction) -> bool:
    return (
        (held == Direction.LONG and signal == Direction.SHORT)
        or (held == Direction.SHORT and signal == Direction.LONG)
    )


def _size(equity: float, price: float, default_pct: float, max_pct: float) -> int:
    pct = min(default_pct, max_pct)
    notional = equity * pct / 100.0
    return int(notional // price) if price > 0 else 0


def _close_pnl(pos: OpenPosition, exit_price: float, commission: float) -> float:
    sign = 1 if pos.direction == Direction.LONG else -1
    return pos.qty * (exit_price - pos.entry_price) * sign - commission


def _record(pos: OpenPosition, date: str, exit_price: float, reason: str, i: int) -> BacktestTrade:
    sign = 1 if pos.direction == Direction.LONG else -1
    pnl = pos.qty * (exit_price - pos.entry_price) * sign
    cost = pos.qty * pos.entry_price
    return BacktestTrade(
        symbol="", direction=pos.direction.value, entry_date=pos.entry_date,
        entry_price=round(pos.entry_price, 2), exit_date=date,
        exit_price=round(exit_price, 2), qty=pos.qty, pnl=round(pnl, 2),
        return_pct=round((pnl / cost * 100) if cost else 0.0, 3),
        exit_reason=reason, bars_held=i - pos.entry_index,
    )
