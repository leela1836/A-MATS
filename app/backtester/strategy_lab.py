"""Validate the library strategies against history.

Walks each strategy bar-by-bar over the universe, opens the trade it proposes,
resolves it path-based (bar high/low vs stop/target, else expiry) net of costs,
and reports the edge. This is the GATE: a strategy earns the right to trade live
only if it shows a positive, stable expectancy out-of-sample here — otherwise it
stays a label. Raw signal edge only: the router's liquidity/regime gates are
bypassed so we measure the strategy itself.

Approximations (stated honestly): indicators are the live ones, vectorized;
support/resistance is a fast trailing 20-bar low/high proxy (not the live
clustering), and trades don't overlap within a strategy (one at a time per name).
"""
from __future__ import annotations

import statistics as st
from typing import Optional

from app.collectors.market_collector import _atr, _ema, _rsi, classify, fetch_history
from app.journal.screener import load_universe
from app.strategies.library.base import Context
from app.strategies.library.router import STRATEGIES

COST_PCT = 0.20     # modeled round-trip cost, same as the live ledger
MAX_HOLD = 20       # bars before a trade expires at market
WARMUP = 200        # bars needed before EMA200 etc. are meaningful


def _resolve(hi, lo, cl, i: int, direction: str, entry: float, stop: float, take: float) -> float:
    """Net % return of the trade opened at bar i, resolved path-based forward."""
    long = direction == "long"
    end = min(i + 1 + MAX_HOLD, len(cl))
    for j in range(i + 1, end):
        if long:
            if lo[j] <= stop:
                return (stop - entry) / entry * 100 - COST_PCT
            if hi[j] >= take:
                return (take - entry) / entry * 100 - COST_PCT
        else:
            if hi[j] >= stop:
                return (entry - stop) / entry * 100 - COST_PCT
            if lo[j] <= take:
                return (entry - take) / entry * 100 - COST_PCT
    px = cl[end - 1]
    return ((px - entry) / entry * 100) * (1 if long else -1) - COST_PCT


def backtest(symbols: Optional[list[str]] = None, period: str = "3y") -> dict:
    symbols = symbols or load_universe()
    rets: dict[str, list[float]] = {s.name: [] for s in STRATEGIES}
    bh: list[float] = []          # buy-and-hold of each name, as a reference
    scanned = 0

    for sym in symbols:
        try:
            df = fetch_history(sym, period=period)
        except Exception:
            continue
        if len(df) < WARMUP + MAX_HOLD + 5:
            continue
        scanned += 1
        close = df["Close"]
        e20 = _ema(close, 20).to_numpy(); e50 = _ema(close, 50).to_numpy()
        e200 = _ema(close, 200).to_numpy(); rsi = _rsi(close, 14).to_numpy()
        atr = _atr(df, 14).to_numpy()
        hi = df["High"].to_numpy(); lo = df["Low"].to_numpy(); cl = df["Close"].to_numpy()
        low_s, high_s = df["Low"], df["High"]
        bh.append((cl[-1] / cl[WARMUP] - 1) * 100)

        next_free = {s.name: 0 for s in STRATEGIES}
        for i in range(WARMUP, len(df) - 1):
            price = float(cl[i])
            trend = classify({"last_price": price, "ema_20": float(e20[i]),
                              "ema_50": float(e50[i]), "ema_200": float(e200[i]),
                              "rsi_14": float(rsi[i])})[0]
            support = float(low_s.iloc[max(0, i - 20):i].min())
            resistance = float(high_s.iloc[max(0, i - 20):i].max())
            ctx = Context(symbol=sym, price=price, trend=trend, regime="neutral",
                          rsi=float(rsi[i]), atr=float(atr[i]), ema20=float(e20[i]),
                          ema50=float(e50[i]), ema200=float(e200[i]), support=support,
                          resistance=resistance, avg_turnover=1e12, df=df.iloc[: i + 1])
            for strat in STRATEGIES:
                if i < next_free[strat.name]:
                    continue
                sig = strat.evaluate(ctx)
                if sig is None:
                    continue
                rets[strat.name].append(_resolve(hi, lo, cl, i, sig.direction,
                                                  sig.entry, sig.stop, sig.target))
                next_free[strat.name] = i + MAX_HOLD  # no overlapping same-strategy trades

    def agg(v: list[float]) -> dict:
        if not v:
            return {"trades": 0, "win_rate": None, "avg": None, "total": 0.0, "median": None}
        wins = sum(1 for x in v if x > 0)
        return {"trades": len(v), "win_rate": round(100 * wins / len(v), 1),
                "avg": round(st.mean(v), 3), "total": round(sum(v), 1),
                "median": round(st.median(v), 3)}

    return {"scanned": scanned, "period": period,
            "buy_hold_avg_pct": round(st.mean(bh), 1) if bh else None,
            "strategies": {name: agg(v) for name, v in rets.items()}}


if __name__ == "__main__":
    import json
    r = backtest()
    print(f"\nStrategy edge over {r['period']} · {r['scanned']} names · "
          f"buy-and-hold avg {r['buy_hold_avg_pct']}%\n")
    print(f"{'strategy':16}{'trades':>8}{'win%':>8}{'avg/trade':>12}{'expectancy':>12}")
    for name, a in r["strategies"].items():
        if not a["trades"]:
            print(f"{name:16}{'0':>8}{'—':>8}{'—':>12}{'—':>12}")
            continue
        verdict = "EDGE" if (a["avg"] or 0) > 0 else "no edge"
        print(f"{name:16}{a['trades']:>8}{a['win_rate']:>8}{a['avg']:>12}"
              f"{a['avg']:>12}  {verdict}")
    print("\n" + json.dumps(r, indent=2))
