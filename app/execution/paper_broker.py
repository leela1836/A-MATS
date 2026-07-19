"""In-app paper-trading engine.

A self-contained virtual portfolio in INR. No external broker: the agent's
decisions execute here against virtual cash and positions, and the whole
state is persisted to disk so it survives restarts and can be rendered on
the web app.

Signed-position model: qty > 0 is long, qty < 0 is short. Realized P&L is
booked when an order reduces or flips a position. Everything is quoted in
rupees.
"""
from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.config import get_config

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PORTFOLIO_FILE = DATA_DIR / "portfolio.json"


@dataclass
class Position:
    symbol: str
    qty: float = 0.0          # signed: +long / -short
    avg_price: float = 0.0    # average entry of the open quantity

    def is_flat(self) -> bool:
        return abs(self.qty) < 1e-9


@dataclass
class Trade:
    seq: int
    symbol: str
    side: str          # "buy" | "sell"
    qty: float
    price: float
    commission: float
    realized_pnl: float
    cash_after: float
    note: str = ""


@dataclass
class Portfolio:
    starting_cash: float
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)
    seq: int = 0

    # ── serialization ──
    def to_dict(self) -> dict:
        return {
            "starting_cash": self.starting_cash,
            "cash": self.cash,
            "seq": self.seq,
            "positions": {
                s: {"symbol": p.symbol, "qty": p.qty, "avg_price": p.avg_price}
                for s, p in self.positions.items()
            },
            "trades": [t.__dict__ for t in self.trades],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Portfolio":
        pf = cls(starting_cash=d["starting_cash"], cash=d["cash"], seq=d.get("seq", 0))
        for s, p in d.get("positions", {}).items():
            pf.positions[s] = Position(symbol=p["symbol"], qty=p["qty"], avg_price=p["avg_price"])
        pf.trades = [Trade(**t) for t in d.get("trades", [])]
        return pf


def _apply_fill(qty: float, avg: float, delta: float, price: float) -> tuple[float, float, float]:
    """Apply a signed fill `delta` at `price` to a position (qty, avg).

    Returns (new_qty, new_avg, realized_pnl).
    """
    realized = 0.0
    if qty == 0 or (qty > 0) == (delta > 0):
        # Opening or increasing in the same direction: weighted-average entry.
        total = abs(qty) + abs(delta)
        new_avg = (abs(qty) * avg + abs(delta) * price) / total if total else 0.0
        return qty + delta, new_avg, 0.0

    # Opposite direction: reducing, closing, or flipping.
    closing = min(abs(delta), abs(qty))
    direction = 1.0 if qty > 0 else -1.0
    realized = closing * (price - avg) * direction

    new_qty = qty + delta
    if abs(new_qty) < 1e-9:
        return 0.0, 0.0, realized
    if (new_qty > 0) == (qty > 0):
        # Partial close, same direction remains: avg unchanged.
        return new_qty, avg, realized
    # Flipped past zero: the remainder opens a new position at `price`.
    return new_qty, price, realized


class PaperBroker:
    """Thread-safe façade over a persisted Portfolio."""

    def __init__(self, path: Path = PORTFOLIO_FILE):
        self._path = path
        self._lock = threading.Lock()
        self._pf = self._load()

    # ── persistence ──
    def _starting_cash(self) -> float:
        trading = get_config("trading")["mode"]
        mode = trading.get("current", "paper")
        block = trading.get(mode, {}) if isinstance(trading.get(mode), dict) else {}
        return float(block.get("initial_balance", 1_000_000.0))

    def _load(self) -> Portfolio:
        if self._path.exists():
            with self._path.open("r", encoding="utf-8") as fh:
                return Portfolio.from_dict(json.load(fh))
        cash = self._starting_cash()
        return Portfolio(starting_cash=cash, cash=cash)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(self._pf.to_dict(), fh, indent=2)
        tmp.replace(self._path)

    def _commission(self) -> float:
        trading = get_config("trading")["mode"]
        mode = trading.get("current", "paper")
        block = trading.get(mode, {})
        # Paper block may omit commission; fall back to the simulation figure.
        if isinstance(block, dict) and "commission_per_trade" in block:
            return float(block["commission_per_trade"])
        return float(trading.get("simulation", {}).get("commission_per_trade", 20.0))

    # ── trading ──
    def place_order(self, symbol: str, side: str, qty: float, price: float,
                    note: str = "") -> Trade:
        """Execute a market paper order. side is 'buy' or 'sell'."""
        if qty <= 0:
            raise ValueError("qty must be positive")
        if not (price == price and price not in (float("inf"), float("-inf"))):
            raise ValueError("price must be finite")

        with self._lock:
            delta = qty if side == "buy" else -qty
            pos = self._pf.positions.get(symbol, Position(symbol=symbol))
            new_qty, new_avg, realized = _apply_fill(pos.qty, pos.avg_price, delta, price)

            commission = self._commission()
            # Cash: buys spend, sells receive; commission always debits.
            # Realized P&L is already embedded in these price flows (buy low /
            # sell high), so it is reported but NOT added to cash separately.
            self._pf.cash += (-delta) * price - commission

            pos.qty, pos.avg_price = new_qty, new_avg
            if pos.is_flat():
                self._pf.positions.pop(symbol, None)
            else:
                self._pf.positions[symbol] = pos

            self._pf.seq += 1
            trade = Trade(
                seq=self._pf.seq, symbol=symbol, side=side, qty=qty, price=price,
                commission=commission, realized_pnl=round(realized, 2),
                cash_after=round(self._pf.cash, 2), note=note,
            )
            self._pf.trades.append(trade)
            self._save()
            return trade

    def size_to_qty(self, size_percent: float, price: float, last_prices: dict[str, float]) -> int:
        """Convert a target position size (% of equity) into whole-share qty."""
        equity = self.equity(last_prices)
        notional = (size_percent / 100.0) * equity
        return max(int(math.floor(notional / price)), 0) if price > 0 else 0

    # ── valuation ──
    def equity(self, last_prices: dict[str, float]) -> float:
        with self._lock:
            return self._pf.cash + self._positions_value(last_prices)

    def _positions_value(self, last_prices: dict[str, float]) -> float:
        total = 0.0
        for s, p in self._pf.positions.items():
            mark = last_prices.get(s, p.avg_price)
            total += p.qty * mark
        return total

    def snapshot(self, last_prices: Optional[dict[str, float]] = None) -> dict:
        last_prices = last_prices or {}
        with self._lock:
            positions = []
            unrealized = 0.0
            for s, p in self._pf.positions.items():
                mark = last_prices.get(s, p.avg_price)
                pnl = (mark - p.avg_price) * p.qty
                unrealized += pnl
                positions.append({
                    "symbol": s, "qty": p.qty, "avg_price": round(p.avg_price, 2),
                    "mark_price": round(mark, 2), "unrealized_pnl": round(pnl, 2),
                })
            realized = sum(t.realized_pnl for t in self._pf.trades)
            positions_value = self._positions_value(last_prices)
            equity = self._pf.cash + positions_value
            return {
                "currency": "INR",
                "starting_cash": self._pf.starting_cash,
                "cash": round(self._pf.cash, 2),
                "positions_value": round(positions_value, 2),
                "equity": round(equity, 2),
                "realized_pnl": round(realized, 2),
                "unrealized_pnl": round(unrealized, 2),
                "total_pnl": round(equity - self._pf.starting_cash, 2),
                "return_percent": round((equity / self._pf.starting_cash - 1) * 100, 3),
                "open_positions": positions,
                "trade_count": len(self._pf.trades),
            }

    def recent_trades(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return [t.__dict__ for t in self._pf.trades[-limit:]][::-1]

    def reset(self) -> None:
        with self._lock:
            cash = self._starting_cash()
            self._pf = Portfolio(starting_cash=cash, cash=cash)
            self._save()


# Process-wide singleton for the running web app.
_broker: Optional[PaperBroker] = None


def get_broker() -> PaperBroker:
    global _broker
    if _broker is None:
        _broker = PaperBroker()
    return _broker
