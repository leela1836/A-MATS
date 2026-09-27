"""Continuous, long-only paper execution using broker data; never sends real orders.

Run with python -m app.execution.realtime. The account is isolated from scans.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app.collectors.fyers_collector import Tick, fetch_completed_history
from app.collectors.market_collector import classify, compute_indicators
from app.config import get_config
from app.execution.paper_broker import PaperBroker
from app.market_calendar import IST, market_status
from app.strategies.library import STRATEGIES, build_context
from app.strategies.library.roster import is_tradable
from app.strategies.support_resistance import summarise

ACCOUNT = Path(__file__).resolve().parents[2] / "data" / "realtime_portfolio.json"
STATUS = ACCOUNT.with_name("realtime_status.json")


class RealtimeEngine:
    def __init__(self, path=ACCOUNT, *, allowed_strategies=None, session_check=None):
        if get_config("trading")["mode"]["current"] != "paper":
            raise ValueError("Realtime runner requires paper mode")
        self.broker = PaperBroker(path)
        self.lock = threading.RLock()
        self.quotes: dict[str, Tick] = {}
        self.signals: dict[str, dict] = {}
        self.cfg = get_config("trading").get("realtime", {})
        self.risk = copy.deepcopy(get_config("risk"))
        self.allowed_strategies = allowed_strategies
        self.session_check = session_check or (lambda now: market_status(now).is_open)
        self.state = self.broker._pf.runtime
        self.state.setdefault("protection", {})
        self.state.setdefault("entered", {})
        self.state.setdefault("halt", "")
        self.state.setdefault("peak", self.broker._pf.starting_cash)
        self.state.setdefault("months", {})
        self.state.setdefault("daily_equity", {})
        self.last_event = "waiting for fresh ticks"
        if set(self.broker._pf.positions) != set(self.state["protection"]):
            raise ValueError("Paper positions/protection mismatch; inspect account before restarting")

    def prepare(self, symbol, df, now):
        ind = compute_indicators(df)
        trend, _, _ = classify(ind)
        if not all(math.isfinite(v) for v in ind.values()):
            raise ValueError("Invalid indicators")
        levels = summarise(df)
        ctx = build_context(symbol, df, ind, trend, "neutral",
                            levels["support"], levels["resistance"])
        proposals = [s.evaluate(ctx) for s in STRATEGIES if self._eligible(s.name)] if ctx.liquid else []
        proposals = [p for p in proposals if p and p.direction == "long"]
        proposal = max(proposals, key=lambda p: p.confidence) if proposals else None
        with self.lock:
            self.signals[symbol] = {"day": now.astimezone(IST).date().isoformat(),
                                    "long": proposal is not None,
                                    "strategy": proposal.strategy if proposal else "none",
                                    "stop": proposal.stop if proposal else 0,
                                    "target": proposal.target if proposal else 0,
                                    "confidence": proposal.confidence if proposal else 0,
                                    "close": ind["last_price"]}

    def _eligible(self, name):
        return name in self.allowed_strategies if self.allowed_strategies is not None else is_tradable(name)

    def disconnect(self):
        with self.lock:
            self.quotes.clear()
            self.last_event = "feed disconnected/reconnecting; entries blocked"

    def _fresh(self, symbol, now):
        tick = self.quotes.get(symbol)
        return tick is not None and tick.fresh(now, self.cfg.get("max_tick_age_seconds", 30))

    def _save(self):
        self.broker._save()

    def _record_mark(self, now, marks):
        """Only complete fresh marks enter the accounting series."""
        if not all(self._fresh(s, now) for s in self.broker._pf.positions):
            return
        snapshot = self.broker.snapshot(marks)
        equity = snapshot["equity"]
        stamp = now.isoformat()
        day = now.astimezone(IST).date().isoformat()
        month = day[:7]
        opening = self.state.get("last_equity", self.broker._pf.starting_cash)
        row = self.state["months"].setdefault(month, {"opening_equity": opening})
        row.update(equity=equity, ts=stamp)
        self.state["daily_equity"][day] = {"ts": stamp, "equity": equity,
                                                 "return_percent": snapshot["return_percent"]}
        self.state.update(last_snapshot=snapshot, last_mark_ts=stamp, last_equity=equity,
                          last_mark_seq=self.broker._pf.seq)
        self.state["peak"] = max(self.state["peak"], equity)
        month_limit = get_config("trading")["portfolio"]["loss_management"]["max_monthly_loss_percent"]
        if 100 * (1 - equity / row["opening_equity"]) >= month_limit:
            self.state["halt"] = "monthly loss limit"
        if self.state.get("day_equity") and 100 * (1 - equity / self.state["day_equity"]) >= self.risk["portfolio"]["max_daily_loss_percent"]:
            self.state["halt"] = "daily loss limit"
        if 100 * (1 - equity / self.state["peak"]) >= self.risk["portfolio"]["max_drawdown_percent"]:
            self.state["halt"] = "peak drawdown limit"

    def _fill(self, symbol, side, qty, price, reason, now, protection=None):
        before = copy.deepcopy(self.state)
        day = now.astimezone(IST).date().isoformat()
        if side == "buy":
            protection = {**protection, "entry_date": day, "strategy": reason}
            self.state["protection"][symbol] = protection
            self.state["entered"][symbol] = day
        else:
            self.state["protection"].pop(symbol, None)
        self.state["orders"] += 1
        self.state["last_order"] = now.timestamp()
        try:
            # Runtime guards, stop/target and portfolio are written in one atomic file.
            trade = self.broker.place_order(symbol, side, qty, price,
                                           note=f"{now.isoformat()} {reason}",
                                           last_prices={s: q.price for s, q in self.quotes.items()
                                                        if self._fresh(s, now)})
        except ValueError:
            self.state.clear()
            self.state.update(before)
            raise
        self.last_event = f"{reason}: {side} {qty} {symbol} @ {trade.price}"
        self._record_mark(now, {s: q.price for s, q in self.quotes.items() if self._fresh(s, now)})
        self._save()
        return trade

    def on_tick(self, tick: Tick, now=None):
        realtime_clock = now is None
        now = now or datetime.now(timezone.utc)
        with self.lock:
            if get_config("trading")["mode"]["current"] != "paper":
                raise ValueError("Paper mode required")
            if not tick.fresh(now, self.cfg.get("max_tick_age_seconds", 30)):
                self.last_event = "stale/invalid tick rejected"
                return
            previous = self.quotes.get(tick.symbol)
            if previous and tick.timestamp < previous.timestamp:
                return
            self.quotes[tick.symbol] = tick
            # Strict session check; legacy trading_hours_only override is ignored.
            if not self.session_check(now):
                self.last_event = "market closed"
                return
            if realtime_clock:
                # Calendar/network lookup may have taken time; never fill a tick
                # that expired while that lookup was in flight.
                now = datetime.now(timezone.utc)
                if not tick.fresh(now, self.cfg.get("max_tick_age_seconds", 30)):
                    self.last_event = "tick expired during session check"
                    return
            day = now.astimezone(IST).date().isoformat()
            positions = self.broker._pf.positions
            all_fresh = all(self._fresh(s, now) for s in positions)
            marks = {s: q.price for s, q in self.quotes.items() if self._fresh(s, now)}
            equity = self.broker.equity(marks)
            if all_fresh:
                if self.state.get("day") != day:
                    # Previous closing mark includes overnight gap risk in today's loss.
                    self.state.update(day=day, day_equity=self.state.get("last_equity", equity),
                                      orders=0, entered={})
                self.state["peak"] = max(self.state["peak"], equity)
                limits = self.risk["portfolio"]
                daily_loss = 100 * (1 - equity / self.state["day_equity"])
                drawdown = 100 * (1 - equity / self.state["peak"])
                if daily_loss >= limits["max_daily_loss_percent"]:
                    self.state["halt"] = "daily loss limit"
                if drawdown >= limits["max_drawdown_percent"]:
                    self.state["halt"] = "peak drawdown limit"
                self._record_mark(now, marks)
                self._save()

            # Protective exits remain available even when another holding is stale.
            pos = positions.get(tick.symbol)
            slip = float(get_config("trading")["mode"]["paper"].get("percentage_slippage", 0))
            if pos:
                protection = self.state["protection"][tick.symbol]
                reason = self.state["halt"]
                if tick.price <= protection["stop"]:
                    reason = "stop loss"
                elif tick.price >= protection["target"]:
                    reason = "take profit"
                elif protection.get("entry_date") and (now.astimezone(IST).date() -
                      datetime.fromisoformat(protection["entry_date"]).date()).days >= self.risk["per_trade"].get("max_position_hold_days", 30):
                    reason = "maximum holding period"
                if reason:
                    self.state.setdefault("orders", 0)
                    return self._fill(tick.symbol, "sell", pos.qty,
                                      round(tick.price * (1 - slip), 2), reason, now)
                return
            if not all_fresh or self.state["halt"]:
                return
            if (self.broker._path.parent / "paper.stop").exists():
                self.last_event = "paper.stop blocks new entries"
                return
            signal = self.signals.get(tick.symbol)
            if not signal or signal["day"] != day or not signal["long"]:
                return
            if not self._eligible(signal["strategy"]):
                return
            if self.state["entered"].get(tick.symbol) == day:
                return
            compliance = self.risk["compliance"]
            if self.state["orders"] >= compliance["max_trades_per_day"]:
                return
            if now.timestamp() - self.state.get("last_order", 0) < 60 * compliance["min_trade_interval_minutes"]:
                return
            if signal["confidence"] < self.risk["per_trade"]["min_confidence_score"]:
                return
            if abs(tick.price / signal["close"] - 1) * 100 > self.cfg.get("max_entry_gap_percent", 3):
                self.last_event = "entry too far from signal close"
                return
            restricted = {s.upper().removesuffix(".NS") for s in compliance.get("restricted_symbols", [])}
            if tick.symbol.removesuffix(".NS") in restricted:
                return
            # Conservative fixed-fraction risk with a notional cap; never average up.
            price = round(tick.price * (1 + slip), 2)
            stop, target = signal["stop"], signal["target"]
            if not 0 < stop < price < target:
                return
            distance = price - stop
            if (target - price) / distance < self.cfg.get("min_reward_risk", 1.2):
                return
            commission = self.broker._commission()
            budget = equity * self.risk["per_trade"]["max_risk_percent"] / 100
            sizing = self.risk["position_sizing"]
            cap = min(sizing["default_size_percent"], sizing["max_size_percent"],
                      self.risk["portfolio"]["max_position_concentration"])
            qty = min(int(max(0, budget - 2 * commission) / (distance + stop * slip)),
                      int(equity * cap / 100 / price))
            if qty <= 0:
                return
            try:
                return self._fill(tick.symbol, "buy", qty, price, signal["strategy"], now,
                                  {"stop": stop, "target": target})
            except ValueError as exc:
                self.last_event = f"order rejected: {exc}"

    def status(self, now=None):
        now = now or datetime.now(timezone.utc)
        with self.lock:
            fresh = {s: q.price for s, q in self.quotes.items() if self._fresh(s, now)}
            return {"mode": "paper", "provider": self.cfg.get("provider", "upstox"), "event": self.last_event,
                    "heartbeat": now.isoformat(),
                    "halt": self.state["halt"], "fresh_symbols": sorted(fresh),
                    "unmarked_positions": sorted(set(self.broker._pf.positions) - set(fresh)),
                    "portfolio": self.broker.snapshot(fresh)}


@contextmanager
def account_lock(path):
    """OS releases this lock after a crash; a second runner cannot overwrite state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a+b") as handle:
        handle.seek(0)
        handle.write(b"0")
        handle.flush()
        handle.seek(0)
        if __import__("os").name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate setup without connecting")
    args = parser.parse_args()
    provider_name = get_config("trading").get("realtime", {}).get("provider", "upstox")
    if provider_name == "upstox":
        from app.collectors import upstox_stream as provider
    elif provider_name == "fyers":
        from app.collectors import fyers_collector as provider
    else:
        parser.error("Unsupported realtime data provider")
    with account_lock(ACCOUNT):
        engine = RealtimeEngine()
        try:
            provider.credentials()
        except ValueError as exc:
            parser.exit(2, f"{exc}\n")
        symbols = get_config("market")["symbols"]["equities"]
        symbols = sorted(set(symbols) | set(engine.broker._pf.positions))
        if args.check:
            print(json.dumps({"configured": True, "provider": provider_name,
                              "symbols": symbols, "mode": "paper"}))
            return
        fatal = threading.Event()

        def receive(tick):
            if fatal.is_set():
                return
            try:
                engine.on_tick(tick)
            except Exception:
                fatal.set()  # Fail closed on persistence or unexpected processing errors.

        socket = provider.connect(symbols, receive, engine.disconnect)
        prepared_day = None
        try:
            while not fatal.is_set():
                now = datetime.now(timezone.utc)
                day = now.astimezone(IST).date()
                if market_status(now).is_open and prepared_day != day:
                    for symbol in symbols:
                        try:
                            engine.prepare(symbol, provider.fetch_completed_history(symbol, now), now)
                        except Exception as exc:
                            print(f"{symbol}: history unavailable ({type(exc).__name__}); no entry")
                    prepared_day = day
                report = json.dumps(engine.status(), allow_nan=False)
                temporary = STATUS.with_suffix(".json.tmp")
                temporary.write_text(report, encoding="utf-8")
                temporary.replace(STATUS)
                print(report, flush=True)
                fatal.wait(5)
            raise RuntimeError("Paper runner stopped after processing/persistence error; inspect account")
        except KeyboardInterrupt:
            pass
        finally:
            if provider_name == "upstox":
                socket.disconnect()
            else:
                socket.close_connection()


if __name__ == "__main__":
    main()
