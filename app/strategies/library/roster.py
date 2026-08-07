"""Champion / challenger governance for the strategy library.

Every strategy holds one of three statuses, and the status decides whether it may
open trades:
  • live     — trades into the book (proven, or the incumbent on probation)
  • shadow   — a challenger on trial; still trades (it's all paper) but is watched
  • benched  — a validated loser; it may still *label* a setup, but opens nothing

Seeds come from the out-of-sample validation backtest (strategy_lab). Thereafter
LIVE results govern: a shadow that proves positive over enough closed trades is
promoted; a live strategy that goes negative over enough trades is benched. So a
strategy improves its standing only by earning it out-of-sample — a run of luck
can't crown it, and the original signal is never edited, only its *permission*.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROSTER_FILE = Path(__file__).resolve().parent.parent.parent.parent / "data" / "strategy_roster.json"

MIN_LIVE_N = 30                # closed trades before live results can move a status
from app.journal.store import ROUND_TRIP_COST_PCT  # net cost, consistent with the ledger

# Seeded from strategy_lab (3y, 49 names, net of costs): only mean_reversion showed
# a (marginal) edge; the incumbent trend_following was negative but keeps trading on
# probation; breakout & candlestick were validated losers.
SEED: dict[str, dict[str, Any]] = {
    "trend_following": {"status": "live", "backtest_edge": -0.34, "note": "incumbent — on probation"},
    "mean_reversion": {"status": "shadow", "backtest_edge": 0.22, "note": "only validated edge — on trial"},
    "breakout": {"status": "benched", "backtest_edge": -0.86, "note": "validated loser"},
    "candlestick": {"status": "benched", "backtest_edge": -0.36, "note": "validated loser"},
}


def _load() -> dict[str, dict[str, Any]]:
    if ROSTER_FILE.exists():
        try:
            data = json.loads(ROSTER_FILE.read_text(encoding="utf-8"))
            # keep any newly-added strategy that isn't in the file yet
            return {**{k: dict(v) for k, v in SEED.items()}, **data}
        except Exception:
            pass
    return {k: dict(v) for k, v in SEED.items()}


def _save(roster: dict[str, dict[str, Any]]) -> None:
    ROSTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    ROSTER_FILE.write_text(json.dumps(roster, indent=2), encoding="utf-8")


def get_roster() -> dict[str, dict[str, Any]]:
    return _load()


def status_of(name: str) -> str:
    return _load().get(name, {}).get("status", "shadow")   # unknown ⇒ unproven, never auto-live


def is_tradable(name: str) -> bool:
    """May this strategy open a trade? (benched strategies only label.)"""
    return status_of(name) != "benched"


def evaluate_and_update(journal=None, save: bool = True) -> dict[str, dict[str, Any]]:
    """Promote/demote from LIVE closed-trade results. The gate, not vibes:
    shadow → live only if its net live edge is positive over ≥ MIN_LIVE_N trades;
    live → benched if it's negative over ≥ MIN_LIVE_N trades."""
    from app.journal.store import get_journal
    journal = journal or get_journal()
    roster = _load()
    perf = journal.strategy_performance()
    for name, info in roster.items():
        p = perf.get(name, {})
        n, avg = p.get("trades", 0), p.get("avg")
        info["live_trades"], info["live_avg"] = n, avg
        if n < MIN_LIVE_N or avg is None:
            continue
        if info["status"] == "shadow" and avg > 0:
            info["status"] = "live"
            info["note"] = f"promoted — live edge {avg:+.2f}%/trade over {n}"
        elif info["status"] == "live" and avg < 0:
            info["status"] = "benched"
            info["note"] = f"demoted — live edge {avg:+.2f}%/trade over {n}"
    if save:
        _save(roster)
    return roster


if __name__ == "__main__":
    print(json.dumps(evaluate_and_update(save=True), indent=2))
