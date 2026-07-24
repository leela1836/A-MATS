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


@app.get("/candles/{symbol}")
def candles(symbol: str, period: str = "1y", bars: int = 130) -> dict:
    """Recent OHLC bars with EMA overlays and trend-aware pattern markers.

    Powers the dashboard price chart. Costs no LLM quota — pure market data.
    EMAs are computed over the FULL fetched history, then the window is sliced,
    so the moving averages are correct at the left edge rather than warming up
    inside the visible range. Pattern markers use the same `detect()` the live
    provider uses, so the chart cannot disagree with the pipeline.
    """
    from app.collectors.market_collector import (
        _ema, classify, compute_indicators, fetch_history,
    )
    from app.strategies.candlesticks import detect

    df = fetch_history(symbol.upper(), period=period)
    if df is None or df.empty or len(df) < 60:
        raise HTTPException(status_code=400, detail=f"insufficient history for {symbol}")

    close = df["Close"]
    ema20, ema50, ema200 = _ema(close, 20), _ema(close, 50), _ema(close, 200)
    has_vol = "Volume" in df.columns
    n = len(df)
    start = max(50, n - max(bars, 20))  # keep left context for indicators

    out = []
    for i in range(start, n):
        row = df.iloc[i]
        window = df.iloc[: i + 1]
        trend = classify(compute_indicators(window))[0]
        pats = [p for p in detect(window, trend) if p.direction != "neutral"]
        top = pats[0] if pats else None
        out.append({
            "date": str(df.index[i].date()),
            "open": round(float(row["Open"]), 2),
            "high": round(float(row["High"]), 2),
            "low": round(float(row["Low"]), 2),
            "close": round(float(row["Close"]), 2),
            "volume": float(row["Volume"]) if has_vol else 0.0,
            "ema20": round(float(ema20.iloc[i]), 2),
            "ema50": round(float(ema50.iloc[i]), 2),
            "ema200": round(float(ema200.iloc[i]), 2),
            "pattern": top.name if top else None,
            "pattern_dir": top.direction if top else None,
        })
    return {"symbol": symbol.upper(), "period": period, "bars": out}


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
