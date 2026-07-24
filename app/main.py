"""FastAPI entry point for A-MATS.

Phase 1 surface: health, config introspection, and a synchronous
run-cycle endpoint that drives the walking-skeleton graph so the Next.js
dashboard has real data to render from day one.
"""
from __future__ import annotations

from typing import Optional

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


def _norm_symbol(symbol: str) -> str:
    """Normalise a user-typed ticker. Yahoo tickers never contain spaces, so a
    'NTPC GREEN.NS' is a typo for 'NTPCGREEN.NS' — strip whitespace and upper-case."""
    return "".join(symbol.split()).upper()


@app.post("/run/{symbol}")
def run(symbol: str) -> dict:
    """Run one trading cycle through the graph for a single symbol."""
    sym = _norm_symbol(symbol)
    return run_cycle(sym, run_id=f"api-{sym.lower()}")


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
        result = run_backtest(_norm_symbol(symbol), period=period)
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
    from app.strategies.support_resistance import summarise as sr_summarise

    sym = _norm_symbol(symbol)
    try:
        df = fetch_history(sym, period=period)
    except Exception as exc:
        # A bad/unknown ticker makes yfinance raise; surface a clean 502, not a 500.
        raise HTTPException(status_code=502, detail=f"could not fetch data for {sym}: {exc}")
    if df is None or df.empty or len(df) < 60:
        raise HTTPException(
            status_code=404,
            detail=f"no usable history for {sym} — check the ticker (e.g. NTPCGREEN.NS, not 'NTPC GREEN.NS')",
        )

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
    # Support/resistance computed on the FULL fetched history for stability,
    # then drawn across the visible window.
    sr = sr_summarise(df)
    return {
        "symbol": sym, "period": period, "bars": out,
        "levels": sr["levels"],
        "support": sr["support"],
        "resistance": sr["resistance"],
    }


@app.post("/scan")
def scan(use_llm: bool = False) -> dict:
    """Run one autonomous sweep of the watchlist and journal it.

    Deterministic by default (zero LLM quota). Pass use_llm=true to spend the
    free budget deliberately. This is the heartbeat — schedule it to build a
    real track record over time.
    """
    from app.journal.scan import scan_watchlist

    return scan_watchlist(use_llm=use_llm)


@app.post("/screen")
def screen(top_n: int = 20, use_llm: bool = False) -> dict:
    """Screen the whole universe (configs/universe.txt) on the dependent signals,
    then run the full pipeline on the top_n survivors and journal them.
    Deterministic by default (no LLM quota)."""
    from app.journal.scan import run_screen_scan

    return run_screen_scan(top_n=top_n, use_llm=use_llm)


@app.post("/learn")
def learn(bootstrap: bool = True) -> dict:
    """Retrain the trade validator on the agent's own closed trades (blended
    with backtest bootstrap early on), and save it as the live model."""
    from app.ml.learn import learn as _learn

    return _learn(bootstrap=bootstrap)


@app.get("/journal/decisions")
def journal_decisions(limit: int = 50, symbol: Optional[str] = None) -> dict:
    """Recent journaled decisions (newest first), optionally by symbol."""
    from app.journal.store import get_journal

    return {"decisions": get_journal().recent_decisions(limit=limit, symbol=symbol)}


@app.get("/journal/equity")
def journal_equity(limit: int = 500) -> dict:
    """The accumulated equity curve plus a track-record summary."""
    from app.journal.store import get_journal

    j = get_journal()
    return {"equity_curve": j.equity_curve(limit=limit), "stats": j.stats()}


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
