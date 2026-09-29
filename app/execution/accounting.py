"""Read-only reporting from the persisted continuous paper account.

Research decisions are never converted into fills or capital allocations here.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ACCOUNT = Path(__file__).resolve().parents[2] / "data" / "realtime_portfolio.json"


def paper_report(path: Path | None = None) -> dict:
    path = path or ACCOUNT
    empty = {"available": False, "accounting_basis": "paper_fills",
             "equity_curve": [], "monthly": [], "trades": [], "open_positions": [],
             "portfolio": {"equity": None, "cash": None, "total_pnl": None,
                           "return_percent": None, "realized_pnl": None,
                           "unrealized_pnl": None}}
    if not path.exists():
        return {**empty, "reason": "No continuous paper account yet"}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        state = raw.get("runtime", {})
        samples = sorted(state.get("daily_equity", {}).values(), key=lambda p: p["ts"])
        monthly = []
        for month, values in sorted(state.get("months", {}).items()):
            opening, closing = values["opening_equity"], values["equity"]
            monthly.append({"month": month, "opening_equity": opening, "equity": closing,
                            "pnl": round(closing - opening, 2),
                            "return_percent": round(100 * (closing / opening - 1), 4),
                            "as_of": values["ts"], "partial": True})
        last = state.get("last_snapshot")
        if state.get("last_mark_seq") != raw.get("seq"):
            last = None  # crash between a fill and its equity snapshot: fail closed
        return {**empty, "available": last is not None, "portfolio": last or empty["portfolio"],
                "funded_at": state.get("funded_at"),
                "as_of": state.get("last_mark_ts"),
                "mark_age_seconds": ((datetime.now(timezone.utc) - datetime.fromisoformat(
                    state["last_mark_ts"])).total_seconds() if state.get("last_mark_ts") else None),
                "equity_curve": samples, "monthly": monthly,
                "trades": raw.get("trades", []), "halt": state.get("halt", ""),
                "open_positions": [{**p, "direction": "long" if p["qty"] > 0 else "short",
                                    "entry": p["avg_price"],
                                    "stop": state.get("protection", {}).get(s, {}).get("stop"),
                                    "target": state.get("protection", {}).get(s, {}).get("target"),
                                    "nn_score": None, "reasoned": False, "thesis": "Paper fill"}
                                   for s, p in raw.get("positions", {}).items()],
                "note": "Last complete mark, not a live quote. Months remain partial until reviewed."}
    except (ValueError, KeyError, TypeError, OSError):
        return {**empty, "reason": "Paper account is unreadable; no synthetic fallback"}
