"""Derive the agent's *insights* from its journal — the conclusions, not just the
raw decisions. This is what turns "we store every trade" into "we know what the
agent is actually good and bad at", and (via journal.record_insight) lets those
conclusions accumulate over time instead of being recomputed and forgotten.

Everything here is read-only over the journal; it invents no new data.
"""
from __future__ import annotations

from typing import Any

from app.journal.store import ROUND_TRIP_COST_PCT, Journal, get_journal

NN_GATE = 0.40           # the P(win) level above which the validator has been predictive
SIGNIFICANT_N = 30       # below this many trades a win-rate is noise, not an edge


def _rate(wins: int, n: int) -> float | None:
    return round(100.0 * wins / n, 1) if n else None


def _bucket(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Win-rate and P&L for a set of trades, NET of modeled round-trip costs — so
    a trade that only cleared the spread reads as the loss it really is."""
    n = len(rows)
    nets = [float(r["pnl_pct"] or 0) - ROUND_TRIP_COST_PCT for r in rows]
    wins = sum(1 for p in nets if p > 0)
    net = sum(nets)
    return {
        "trades": n,
        "win_rate": _rate(wins, n),
        "net_pct": round(net, 2),
        "avg_pct": round(net / n, 2) if n else None,
    }


def compute_insights(journal: Journal | None = None) -> dict[str, Any]:
    """The agent's current edge: by direction, by NN-conviction, and vs buy-and-hold."""
    journal = journal or get_journal()
    with journal._conn() as c:
        closed = [dict(r) for r in c.execute(
            "SELECT direction, pnl_pct, nn_score FROM decisions "
            "WHERE status='closed' AND direction IN ('long','short') AND pnl_pct IS NOT NULL"
        ).fetchall()]

    longs = [r for r in closed if r["direction"] == "long"]
    shorts = [r for r in closed if r["direction"] == "short"]
    lg, sh = _bucket(longs), _bucket(shorts)

    scored = [r for r in closed if r["nn_score"] is not None]
    hi = _bucket([r for r in scored if r["nn_score"] >= NN_GATE])
    lo = _bucket([r for r in scored if r["nn_score"] < NN_GATE])

    curve = journal.equity_curve()
    latest = curve[-1] if curve else None
    agent_ret = latest["return_percent"] if latest else 0.0
    bench_ret = None
    if latest and latest.get("benchmark") is not None:
        from app.journal.benchmark import BuyHold
        bench_ret = BuyHold().return_percent(latest["benchmark"])
    spread = round(agent_ret - bench_ret, 2) if (bench_ret is not None and agent_ret is not None) else None

    headline, suggestion = _narrate(lg, sh, hi, lo, agent_ret, bench_ret, spread)
    n = len(closed)
    significant = n >= SIGNIFICANT_N
    caveat = (f"Small sample (n={n}) — treat as directional, not proven."
              if not significant else f"Based on {n} closed trades.")
    caveat += f" All figures are net of {ROUND_TRIP_COST_PCT:.2f}% modeled round-trip costs."
    return {
        "generated_at": None,  # filled by callers that snapshot it
        "overall": {
            "resolved": n,
            "agent_return": agent_ret,
            "benchmark_return": bench_ret,
            "spread_pct": spread,
        },
        "by_direction": {"long": lg, "short": sh},
        "nn_gate": {"threshold": NN_GATE, "hi": hi, "lo": lo},
        "headline": headline,
        "suggestion": suggestion,
        "significant": significant,
        "caveat": caveat,
        "cost_pct": ROUND_TRIP_COST_PCT,
    }


def _narrate(lg, sh, hi, lo, agent_ret, bench_ret, spread) -> tuple[str, str]:
    """Turn the numbers into one honest sentence + the action they argue for."""
    parts = []
    if lg["trades"] and sh["trades"]:
        parts.append(
            f"Longs {lg['win_rate']}% ({lg['net_pct']:+.1f}%) vs "
            f"shorts {sh['win_rate']}% ({sh['net_pct']:+.1f}%)"
        )
    if hi["trades"] and lo["trades"] and hi["win_rate"] is not None and lo["win_rate"] is not None:
        parts.append(f"NN≥{NN_GATE:.2f} wins {hi['win_rate']}% vs {lo['win_rate']}% below")
    if spread is not None:
        verb = "beating" if spread >= 0 else "trailing"
        parts.append(f"{verb} buy-and-hold by {abs(spread):.1f}%")
    headline = "; ".join(parts) + "." if parts else "Not enough closed trades yet to draw an edge."

    # The action the data argues for, in priority order.
    suggestion = "Keep gathering closed trades — the edge isn't resolvable yet."
    if sh["trades"] and lg["trades"] and (sh["net_pct"] or 0) < 0 and (sh["net_pct"] or 0) < (lg["net_pct"] or 0):
        suggestion = ("Shorts are the drag — gate them behind a bearish market regime "
                      "(index below its 200-EMA) so it stops fighting an uptrend.")
    elif hi["trades"] and lo["trades"] and (hi["win_rate"] or 0) > (lo["win_rate"] or 0) + 15:
        suggestion = (f"Raise the NN gate toward {NN_GATE:.2f} — low-conviction trades "
                      f"({lo['win_rate']}% win) are dragging the high-conviction ones down.")
    return headline, suggestion
