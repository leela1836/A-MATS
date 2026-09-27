"""Shared-capital strategy evaluation on a reserved chronological tail.

Parameters remain fixed. This retrospective holdout is not an untouched test if
the same dates already informed earlier research. No automatic strategy promotion.
"""
from __future__ import annotations

from app.backtester.portfolio import replay
from app.collectors.market_collector import fetch_history
from app.journal.screener import load_universe
from app.strategies.library.router import STRATEGIES


def backtest(symbols=None, period="3y", *, frames=None, strategies=None, start=None):
    if frames is None:
        frames = {}
        for symbol in symbols or load_universe():
            try:
                frames[symbol] = fetch_history(symbol, period=period)
            except Exception:
                continue
    usable = {s: df for s, df in frames.items() if len(df) > 215}
    if not usable:
        raise ValueError("No usable history")
    dates = sorted(set().union(*(set(str(d.date()) for d in df.index[210:]) for df in usable.values())))
    start = start or dates[int(len(dates) * .7)]
    output = {}
    for name in strategies or [s.name for s in STRATEGIES]:
        report = replay(usable, strategies={name}, start=start)
        trades = report["trades"]
        entries, nets = {}, []
        for trade in trades:
            if trade["side"] == "buy":
                entries[trade["symbol"]] = trade
            else:
                entry = entries.pop(trade["symbol"])
                net = trade["realized_pnl"] - trade["commission"] - entry["commission"]
                nets.append(100 * net / (entry["qty"] * entry["price"]))
        output[name] = {"trades": len(nets),
                        "win_rate": 100 * sum(p > 0 for p in nets) / len(nets) if nets else None,
                        "avg": sum(nets) / len(nets) if nets else None,
                        "portfolio_return_pct": report["portfolio"]["return_percent"],
                        "monthly": report["monthly"], "halt": report.get("halt"),
                        "account": report, "promotion_eligible": False}
    holds = []
    for df in usable.values():
        window = df.loc[[str(d.date()) >= start for d in df.index]]
        if len(window):
            holds.append((float(window.Close.iloc[-1]) / float(window.Open.iloc[0]) - 1) * 100)
    return {"scanned": len(usable), "period": period, "evaluation_start": start,
            "buy_hold_avg_pct": sum(holds) / len(holds) if holds else None,
            "benchmark_note": "Gross equal-weight reference; different exposure, excludes costs",
            "validation": "retrospective chronological holdout; not prospective proof",
            "strategies": output}


if __name__ == "__main__":
    import json
    print(json.dumps(backtest(), indent=2))
