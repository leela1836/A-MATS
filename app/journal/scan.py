"""Autonomous watchlist scan — the system's heartbeat.

One call sweeps the whole watchlist through the SAME pipeline the dashboard
uses, records every decision to the journal, resolves any prior open trades
against the fresh prices, and snapshots equity. Run it on a schedule and the
project stops being a thing you poke and starts being a system with a track
record.

Reasoning defaults to the DETERMINISTIC path so a full sweep costs zero LLM
quota — the free budget cannot survive scanning ten symbols with the model.
Pass use_llm=True to spend quota deliberately on a small watchlist.
"""
from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timezone
from typing import Any, Optional

from app.agents.reasoning import deterministic
from app.config import get_config
from app.execution.paper_broker import get_broker
from app.journal.store import Journal, get_journal
from app.workflows.runner import run_cycle

# Survival guard: if the paper account is down more than this from its start,
# stop opening NEW positions (still resolve open ones and snapshot equity).
# Keeps the book alive to learn another day instead of averaging into ruin.
SURVIVAL_DD_LIMIT = 30.0


def _watchlist() -> list[str]:
    syms = (get_config("market").get("symbols") or {}).get("equities") or []
    return [str(s).upper() for s in syms]


def _features_json(symbol: str, direction: str) -> Optional[str]:
    """Feature vector behind a directional call, stored so the agent can later
    learn from how the trade turned out. Uses the cached history (fast)."""
    if direction not in ("long", "short"):
        return None
    try:
        import json
        from app.collectors.market_collector import fetch_history
        from app.ml.features import extract
        df = fetch_history(symbol, period="2y")
        return json.dumps([round(float(x), 6) for x in extract(df, direction)])
    except Exception:
        return None


def _resolve_open(journal: Journal, prices: dict[str, float]) -> int:
    """Close any open decision whose stop or target the latest price has hit.

    Uses only the price we just observed — no lookahead, no second fetch. A
    decision with no fresh price for its symbol simply stays open.
    """
    closed = 0
    for d in journal.open_decisions():
        px = prices.get(d["symbol"])
        entry, stop, take = d.get("entry_price"), d.get("stop_loss"), d.get("take_profit")
        if px is None or entry in (None, 0) or stop is None or take is None:
            continue
        long = d["direction"] == "long"
        hit_stop = px <= stop if long else px >= stop
        hit_take = px >= take if long else px <= take
        if not (hit_stop or hit_take):
            continue
        pnl_pct = ((px - entry) / entry * 100.0) * (1 if long else -1)
        outcome = "win" if hit_take and not hit_stop else "loss"
        journal.close_decision(d["id"], round(px, 2), outcome, pnl_pct)
        closed += 1
    return closed


def scan_watchlist(
    symbols: Optional[list[str]] = None,
    use_llm: bool = False,
    journal: Optional[Journal] = None,
    session: Optional[str] = None,
) -> dict[str, Any]:
    """Run one full sweep and journal it. Returns a summary of the scan.

    `session` (e.g. "pre" / "post") labels the scan_id so a pre-open plan and a
    post-close resolution are distinguishable in the journal.
    """
    journal = journal or get_journal()
    symbols = symbols or _watchlist()
    scan_id = datetime.now(timezone.utc).strftime("scan-%Y%m%dT%H%M%S")
    if session:
        scan_id = f"{scan_id}-{session}"

    prices: dict[str, float] = {}
    pending: list[tuple[str, dict[str, Any]]] = []

    ctx = nullcontext() if use_llm else deterministic()
    with ctx:
        for sym in symbols:
            try:
                res = run_cycle(sym, run_id=f"{scan_id}-{sym.lower()}")
            except Exception as exc:  # one bad symbol must not sink the sweep
                pending.append((sym, {"direction": "hold", "thesis": f"scan error: {exc}"}))
                continue
            ma = res.get("market_analysis") or {}
            ra = res.get("reasoned_analysis") or {}
            dec = res.get("decision") or {}
            if isinstance(ma.get("last_price"), (int, float)):
                prices[sym] = float(ma["last_price"])
            src = next(
                (n.get("note", "") for n in (res.get("trace") or {}).get("nodes", [])
                 if n.get("node") == "reasoning"),
                "",
            )
            pending.append((sym, {
                "direction": (ra.get("direction") or dec.get("action") or "hold"),
                "signal": ma.get("signal"),
                "confidence": ra.get("confidence"),
                "entry_price": ra.get("entry_price"),
                "stop_loss": ra.get("stop_loss"),
                "take_profit": ra.get("take_profit"),
                "risk_reward": ra.get("risk_reward"),
                "est_hold_days": ra.get("est_hold_days"),
                "nn_score": ma.get("nn_score"),
                "support": ma.get("support"),
                "resistance": ma.get("resistance"),
                "trend": ma.get("trend"),
                "thesis": ra.get("thesis"),
                "source": "llm" if src.startswith("llm") else "fallback",
                "features": _features_json(sym, ra.get("direction") or dec.get("action") or "hold"),
            }))

    # Resolve prior open trades against the fresh prices BEFORE logging new ones,
    # so a brand-new entry can't be "resolved" against its own entry price.
    closed = _resolve_open(journal, prices)
    # One trade per symbol: don't re-open a directional call already open.
    open_syms = {d["symbol"] for d in journal.open_decisions()}
    for sym, fields in pending:
        if fields["direction"] in ("long", "short") and sym in open_syms:
            continue
        journal.record_decision(scan_id, sym, fields)

    snapshot = get_broker().snapshot(prices)
    journal.record_equity(scan_id, snapshot)

    directional = sum(1 for _, f in pending if f["direction"] in ("long", "short"))
    return {
        "scan_id": scan_id,
        "scanned": len(symbols),
        "directional_calls": directional,
        "closed_this_scan": closed,
        "equity": snapshot.get("equity"),
        "return_percent": snapshot.get("return_percent"),
        "used_llm": use_llm,
        "stats": journal.stats(),
    }


def run_screen_scan(
    universe: Optional[list[str]] = None,
    top_n: int = 20,
    use_llm: bool = False,
    llm_top: int = 0,
    session: Optional[str] = None,
    throttle_s: float = 0.0,
    journal: Optional[Journal] = None,
) -> dict[str, Any]:
    """Screen the whole universe, then run the full pipeline on the shortlist.

    Stage 1: rank hundreds of symbols on the dependent signals (no LLM, no
    orders). Stage 2: the top `top_n` go through run_cycle for a reasoned plan
    and a paper fill.

    Quota-aware reasoning: the LLM actually reasons only on the top `llm_top`
    finalists (a few calls per scan, within the free budget); the rest use the
    deterministic path. `use_llm=True` forces the LLM for all finalists.
    """
    from app.journal.screener import screen_universe

    journal = journal or get_journal()
    scan_id = datetime.now(timezone.utc).strftime("scan-%Y%m%dT%H%M%S")
    if session:
        scan_id = f"{scan_id}-{session}"

    candidates, prices = screen_universe(universe, top_n=top_n, throttle_s=throttle_s)

    # Resolve prior open trades against the full price map (every screened
    # symbol), so a name that dropped off the shortlist is still marked out.
    closed = _resolve_open(journal, prices)

    # Survival guard: if the account is drawn down past the limit, open nothing
    # new this scan — resolve and snapshot only, so the book lives to learn on.
    dd = get_broker().snapshot(prices).get("return_percent", 0.0)
    survival_halt = dd is not None and dd < -SURVIVAL_DD_LIMIT
    if survival_halt:
        candidates = []

    # One trade per symbol: skip any name that already has an OPEN decision, so
    # a setup isn't re-opened (and re-filled, and re-counted) on every scan. When
    # it resolves via stop/target, the next scan is free to enter again.
    open_syms = {d["symbol"] for d in journal.open_decisions()}

    llm_used, held_open = 0, 0
    for rank, c in enumerate(candidates, start=1):
        if c.symbol in open_syms:
            held_open += 1
            continue
        # Reason with the LLM only on the strongest few picks — real reasoning
        # where it matters, within the daily quota; deterministic for the rest.
        llm_this = use_llm or rank <= llm_top
        ctx = nullcontext() if llm_this else deterministic()
        try:
            with ctx:
                res = run_cycle(c.symbol, run_id=f"{scan_id}-{c.symbol.lower()}")
        except Exception:
            continue
        ma = res.get("market_analysis") or {}
        ra = res.get("reasoned_analysis") or {}
        dec = res.get("decision") or {}
        src = next(
            (n.get("note", "") for n in (res.get("trace") or {}).get("nodes", [])
             if n.get("node") == "reasoning"), "",
        )
        if src.startswith("llm"):
            llm_used += 1
        journal.record_decision(scan_id, c.symbol, {
            "direction": (ra.get("direction") or dec.get("action") or "hold"),
            "signal": ma.get("signal"),
            "confidence": ra.get("confidence"),
            "entry_price": ra.get("entry_price"),
            "stop_loss": ra.get("stop_loss"),
            "take_profit": ra.get("take_profit"),
            "risk_reward": ra.get("risk_reward"),
            "est_hold_days": ra.get("est_hold_days"),
            "nn_score": ma.get("nn_score"),
            "support": ma.get("support"),
            "resistance": ma.get("resistance"),
            "trend": ma.get("trend"),
            "thesis": ra.get("thesis"),
            "source": "llm" if src.startswith("llm") else "fallback",
            "screen_score": c.score,
            "screen_rank": rank,
            "features": _features_json(c.symbol, ra.get("direction") or dec.get("action") or "hold"),
        })

    snapshot = get_broker().snapshot(prices)
    journal.record_equity(scan_id, snapshot)
    return {
        "scan_id": scan_id,
        "universe": len(universe or []) or "config",
        "screened": len(prices),
        "shortlisted": len(candidates),
        "closed_this_scan": closed,
        "held_open": held_open,
        "survival_halt": survival_halt,
        "equity": snapshot.get("equity"),
        "llm_reasoned": llm_used,
        "top": [c.as_dict() for c in candidates[:10]],
        "stats": journal.stats(),
    }


if __name__ == "__main__":
    import json
    import os

    sess = os.environ.get("SCAN_SESSION")
    llm_top = int(os.environ.get("SCAN_LLM_TOP", "0"))  # LLM-reason the top-N picks
    if os.environ.get("SCAN_MODE", "screen") == "watchlist":
        summary = scan_watchlist(session=sess)
    else:
        summary = run_screen_scan(session=sess, llm_top=llm_top)
    print(json.dumps(summary, indent=2))
