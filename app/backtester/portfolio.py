"""Chronological, shared-capital daily-bar replay of the continuous paper engine.

Uses the deployed strategy, sizing and account guards. Daily bars cannot reproduce
tick ordering; open entries and conservative stop-first intrabar exits are explicit
approximations. Results are not prospective/live validation.
"""
from __future__ import annotations

import tempfile
from datetime import datetime, time
from pathlib import Path

import numpy as np
import pandas as pd

from app.collectors.fyers_collector import Tick
from app.execution.realtime import RealtimeEngine
from app.execution.accounting import paper_report
from app.market_calendar import IST


def replay(frames: dict[str, pd.DataFrame], *, strategies=None, start=None, end=None):
    prepared = {}
    for symbol, df in frames.items():
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy().astype(float)
        df.index = pd.Index(pd.to_datetime(df.index).date)
        if (df.index.has_duplicates or not df.index.is_monotonic_increasing
                or not np.isfinite(df.to_numpy()).all()
                or (df[["Open", "High", "Low", "Close"]] <= 0).any().any()
                or (df.High < df[["Open", "Low", "Close"]].max(axis=1)).any()
                or (df.Low > df[["Open", "High", "Close"]].min(axis=1)).any()
                or (df.Volume < 0).any()):
            raise ValueError(f"Invalid history: {symbol}")
        if len(df) > 210:
            prepared[symbol] = df
    if not prepared:
        raise ValueError("No symbols with sufficient history")
    days = sorted(set().union(*(set(df.index[210:]) for df in prepared.values())))
    days = [d for d in days if (start is None or str(d) >= start) and (end is None or str(d) <= end)]
    if not days:
        raise ValueError("No evaluation days")
    with tempfile.TemporaryDirectory(prefix="amats-replay-") as temp:
        path = Path(temp) / "account.json"
        engine = RealtimeEngine(path, allowed_strategies=strategies, session_check=lambda _: True)
        skipped = []
        for day in days:
            opening = datetime.combine(day, time(9, 15), IST)
            available = {s: df.loc[day] for s, df in prepared.items() if day in df.index}
            # Never silently mark a missing/delisted holding at its entry price.
            if set(engine.broker._pf.positions) - set(available):
                skipped.append(str(day))
                continue
            engine.quotes.clear()
            for symbol, row in available.items():
                engine.quotes[symbol] = Tick(symbol, float(row.Open), opening.timestamp())
                history = prepared[symbol].loc[prepared[symbol].index < day].copy()
                if len(history) >= 210:
                    engine.prepare(symbol, history, opening)
            for symbol in sorted(available):
                engine.on_tick(engine.quotes[symbol], opening)
            # Each held symbol's unknown intrabar path assumes stop first.
            # Other holdings retain open marks: ordering is an approximation.
            for symbol in sorted(list(engine.broker._pf.positions)):
                row = available[symbol]
                levels = engine.state["protection"][symbol]
                price = None
                if row.Low <= levels["stop"]:
                    price = min(float(row.Open), levels["stop"])
                elif row.High >= levels["target"]:
                    price = levels["target"]
                if price is not None:
                    engine.on_tick(Tick(symbol, price, opening.timestamp()), opening)
            closing = datetime.combine(day, time(15, 29), IST)
            engine.quotes = {s: Tick(s, float(row.Close), closing.timestamp()) for s, row in available.items()}
            # Refresh accounting and exits, but don't create entries at a close
            # whose price was only just observed by this bar-based simulation.
            engine.signals.clear()
            for symbol in sorted(available):
                engine.on_tick(engine.quotes[symbol], closing)
        report = paper_report(path)
        report.update(evaluation_start=str(days[0]), evaluation_end=str(days[-1]),
                      skipped_missing_holdings=skipped, symbols=sorted(prepared),
                      validation="historical_daily_bar_approximation",
                      limitations=["No intra-bar tick ordering or partial fills",
                                   "Simultaneous daily opens and order spacing permit at most one new entry per day",
                                   "Flat commissions and slippage do not cover all Indian taxes and fees",
                                   "Current universe may contain survivorship bias",
                                   "Historical account rules do not prove future profitability"])
        return report
