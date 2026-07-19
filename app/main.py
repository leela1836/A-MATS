"""FastAPI entry point for A-MATS.

Phase 1 surface: health, config introspection, and a synchronous
run-cycle endpoint that drives the walking-skeleton graph so the Next.js
dashboard has real data to render from day one.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import all_configs, get_config
from app.execution.paper_broker import get_broker
from app.workflows.runner import run_cycle

app = FastAPI(title="A-MATS", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "a-mats", "version": app.version}


@app.get("/config/{name}")
def config(name: str) -> dict:
    try:
        return get_config(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/config")
def configs() -> dict:
    return all_configs()


@app.post("/run/{symbol}")
def run(symbol: str) -> dict:
    """Run one trading cycle through the graph for a single symbol."""
    return run_cycle(symbol.upper(), run_id=f"api-{symbol.lower()}")


@app.get("/market/status")
def market() -> dict:
    """Whether the NSE session is open right now (IST)."""
    from app.market_calendar import market_status, trading_allowed

    status = market_status().as_dict()
    allowed, why = trading_allowed()
    return {**status, "orders_allowed": allowed, "orders_reason": why}


@app.post("/backtest/{symbol}")
def backtest(symbol: str, period: str = "2y", include_trades: bool = True) -> dict:
    """Replay the deterministic technical strategy over history.

    Note this validates the SIGNAL, not the LLM reasoning layer (see
    app/backtester/engine.py) and makes no LLM calls, so it costs no quota.
    """
    from app.backtester.analytics import analyse
    from app.backtester.engine import run_backtest

    try:
        result = run_backtest(symbol.upper(), period=period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"backtest failed: {exc}")

    payload = {"metrics": analyse(result), "equity_curve": result.equity_curve}
    if include_trades:
        payload["trades"] = [t.__dict__ for t in result.trades]
    return payload


@app.get("/portfolio")
def portfolio() -> dict:
    """Current virtual paper portfolio (cash, positions, P&L)."""
    return get_broker().snapshot()


@app.get("/trades")
def trades(limit: int = 50) -> dict:
    """Most recent paper trades, newest first."""
    return {"trades": get_broker().recent_trades(limit)}


@app.post("/portfolio/reset")
def portfolio_reset() -> dict:
    """Reset the virtual portfolio to its starting cash."""
    get_broker().reset()
    return get_broker().snapshot()
