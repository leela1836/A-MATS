"""Upstox market-data collector — real NSE prices that work from the cloud.

Yahoo Finance blocks datacenter IPs (so the GitHub agent got no data). Upstox's
**Analytics Token** (1-year, read-only) does NOT require a static IP for market
data, so it works from GitHub's changing IPs — the fix for autonomous operation.

This is a drop-in for `fetch_history`: it returns the SAME DataFrame shape
yfinance does (DatetimeIndex + Open/High/Low/Close/Volume), so nothing else in
the pipeline changes. Set the token in the `UPSTOX_ACCESS_TOKEN` env var
(locally in `.env`, in CI as a GitHub secret).

Upstox identifies instruments by ISIN-based keys (`NSE_EQ|INE002A01018`), not
`RELIANCE.NS`, so we download the NSE instruments master once (cached) and map
`trading_symbol -> instrument_key`.
"""
from __future__ import annotations

import gzip
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

HIST_BASE = "https://api.upstox.com/v3/historical-candle"
INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
TOKEN_ENV = "UPSTOX_ACCESS_TOKEN"
# Upstox's WAF returns 403 to the default python-urllib UA; a browser-like one
# is required on every request.
USER_AGENT = "Mozilla/5.0 (compatible; A-MATS/1.0)"

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"
INSTR_CACHE = CACHE_DIR / "upstox_nse_instruments.json"
INSTR_TTL = 7 * 86400  # refresh the instrument map weekly

_PERIOD_DAYS = {"6mo": 183, "1y": 365, "2y": 730, "3y": 1095, "5y": 1825, "10y": 3650, "max": 9000}
_UNIT = {"1d": ("days", 1), "1wk": ("weeks", 1), "1mo": ("months", 1)}

_instr_map: Optional[dict[str, str]] = None


def have_token() -> bool:
    return bool(os.environ.get(TOKEN_ENV, "").strip())


def _load_instruments() -> dict[str, str]:
    """{TRADING_SYMBOL: instrument_key} for NSE equities, cached on disk."""
    if INSTR_CACHE.exists() and (time.time() - INSTR_CACHE.stat().st_mtime) < INSTR_TTL:
        try:
            return json.loads(INSTR_CACHE.read_text())
        except Exception:
            pass
    req = urllib.request.Request(INSTRUMENTS_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        rows = json.loads(gzip.decompress(r.read()))
    mapping: dict[str, str] = {}
    for it in rows:
        ik = it.get("instrument_key", "")
        ts = it.get("trading_symbol") or it.get("tradingsymbol")
        # instrument_key encodes the segment; NSE_EQ| is cash-equity on NSE.
        if ik.startswith("NSE_EQ|") and ts:
            mapping[str(ts).upper()] = ik
    if mapping:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        INSTR_CACHE.write_text(json.dumps(mapping))
    return mapping


def instrument_key(symbol: str) -> Optional[str]:
    """'RELIANCE.NS' -> 'NSE_EQ|INE002A01018'."""
    global _instr_map
    if _instr_map is None:
        _instr_map = _load_instruments()
    base = symbol.upper().replace(".NS", "").replace(".BO", "").strip()
    return _instr_map.get(base)


def _candles_to_df(candles: list) -> pd.DataFrame:
    """Upstox candles ([ts, o, h, l, c, v, oi], newest-first) -> yfinance shape."""
    df = pd.DataFrame(candles, columns=["ts", "Open", "High", "Low", "Close", "Volume", "OI"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_localize(None)
    df = df.sort_values("ts").set_index("ts")
    out = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    out.index.name = "Date"
    return out


def fetch_history_upstox(symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    """Historical candles for `symbol` via Upstox. Raises on any failure so the
    caller can fall back (to a stale cache or yfinance)."""
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise RuntimeError("UPSTOX_ACCESS_TOKEN not set")
    ik = instrument_key(symbol)
    if not ik:
        raise RuntimeError(f"no Upstox instrument for {symbol}")

    unit, ivl = _UNIT.get(interval, ("days", 1))
    to_d = date.today()
    from_d = to_d - timedelta(days=_PERIOD_DAYS.get(period, 730))
    url = (f"{HIST_BASE}/{urllib.parse.quote(ik, safe='')}/{unit}/{ivl}"
           f"/{to_d.isoformat()}/{from_d.isoformat()}")
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json",
                 "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.loads(r.read())
    candles = ((payload or {}).get("data") or {}).get("candles") or []
    if not candles:
        raise RuntimeError(f"no candles returned for {symbol} ({ik})")
    return _candles_to_df(candles)
