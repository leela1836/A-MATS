"""The plain-English 'what is the agent doing' summary.

One structured object that answers, in order: what it did today, its running
track record, what it holds right now (and why), what it has learned, and what
its 'memory' actually is. Both the live dashboard (via /agent/summary) and the
GitHub Pages site (baked into docs/data.json) render from this exact shape, so
the two never drift.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.execution.paper_broker import get_broker
from app.journal.store import Journal, get_journal
from app.ml.features import FEATURE_NAMES
from app.ml.validator import DEFAULT_MODEL_PATH


def _model_meta(path: Path = DEFAULT_MODEL_PATH) -> dict[str, Any]:
    """The live validator's provenance: what it was trained on and when."""
    if not path.exists():
        return {"available": False}
    meta: dict[str, Any] = {}
    try:
        meta = json.loads(path.read_text(encoding="utf-8")).get("meta", {}) or {}
    except Exception:
        meta = {}
    updated = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return {
        "available": True,
        "updated_at": updated.isoformat(timespec="seconds"),
        "trained_on": meta.get("trained_on"),
        "experience_samples": meta.get("experience_samples"),
        "bootstrap_samples": meta.get("bootstrap_samples"),
        "oos_auc": meta.get("oos_auc"),
    }


def _headline(today: dict[str, Any], portfolio: dict[str, Any], open_ct: int) -> str:
    """One sentence a human can read at a glance."""
    if today["opened"] == 0 and today["closed"] == 0 and today["scans"] == 0:
        return (
            f"No scans yet today. The agent is holding {open_ct} open paper "
            f"position(s); equity {_inr(portfolio.get('equity'))} "
            f"({_pct(portfolio.get('return_percent'))} all-time)."
        )
    bits = [f"Today the agent ran {today['scans']} scan(s)"]
    if today["opened"]:
        bits.append(f"opened {today['opened']} ({today['longs']}L/{today['shorts']}S)")
    if today["closed"]:
        pnl = today["realized_pnl_pct"]
        bits.append(
            f"closed {today['closed']} (▲{today['wins']} ▼{today['losses']}, "
            f"{_pct(pnl)} realized)"
        )
    tail = (
        f"Now holding {open_ct} open; equity {_inr(portfolio.get('equity'))} "
        f"({_pct(portfolio.get('return_percent'))} all-time)."
    )
    return ", ".join(bits) + ". " + tail


def _inr(v: Any) -> str:
    if v is None:
        return "—"
    return "₹" + format(int(round(float(v))), ",d")


def _pct(v: Any) -> str:
    if v is None:
        return "—"
    v = float(v)
    return f"{'+' if v >= 0 else ''}{round(v, 2)}%"


def agent_summary(journal: Journal | None = None) -> dict[str, Any]:
    """Assemble the everything-at-a-glance summary."""
    journal = journal or get_journal()
    stats = journal.stats()
    today = journal.today_summary()
    portfolio = get_broker().snapshot()
    open_positions = journal.open_positions_detail(limit=20)
    learn_events = journal.learning_events(limit=10)
    experience = len(journal.training_rows())  # own closed trades it can learn from
    model = _model_meta()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "headline": _headline(today, portfolio, len(open_positions)),
        "today": today,
        "track_record": stats,
        "portfolio": {
            "equity": portfolio.get("equity"),
            "total_pnl": portfolio.get("total_pnl"),
            "return_percent": portfolio.get("return_percent"),
            "cash": portfolio.get("cash"),
            "realized_pnl": portfolio.get("realized_pnl"),
            "unrealized_pnl": portfolio.get("unrealized_pnl"),
        },
        "open_positions": [
            {
                "symbol": p["symbol"],
                "direction": p["direction"],
                "entry": p["entry_price"],
                "stop": p["stop_loss"],
                "target": p["take_profit"],
                "nn_score": p["nn_score"],
                "reasoned": p.get("source") == "llm",
                "thesis": (p.get("thesis") or "")[:220],
            }
            for p in open_positions
        ],
        "learning": {
            "events": learn_events,
            "last": learn_events[0] if learn_events else None,
            "experience_available": experience,   # trades it can learn from now
            "model": model,
        },
        "memory": {
            "what_it_is": (
                "The agent has no separate note-store. Its memory is two things: "
                "the journal (every decision + how it turned out = experience) and "
                "the neural-net weights (the lessons distilled from that experience)."
            ),
            "journal_experiences": experience,
            "journal_decisions_total": stats.get("decisions", 0),
            "model_path": str(DEFAULT_MODEL_PATH.name),
            "model_updated": model.get("updated_at"),
        },
        "factors": {
            "note": (
                "These are the inputs the agent records for every directional call "
                "(the 'features' column) and later learns from. It does NOT yet "
                "track fundamentals, macro, or order-flow — those are the missing factors."
            ),
            "tracked": list(FEATURE_NAMES),
        },
    }
