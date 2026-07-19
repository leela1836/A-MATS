"""Official NSE India data.

Yahoo Finance gives us prices; NSE gives us the things only the exchange
knows — its own trading calendar, which stocks are under surveillance, what
companies have formally disclosed, and the authoritative session state.

Several safety flags in configs/risk.yaml (`avoid_asm_gsm_stocks`,
`restricted_symbols`) were previously decorative because nothing supplied
the underlying lists. This module supplies them.

RELIABILITY NOTES
- NSE's JSON endpoints are public but undocumented, and require a cookie
  seeded from the homepage plus a browser-ish User-Agent. They rate-limit
  aggressively, so every result is cached to disk and served from cache by
  default. Nothing here is on the hot path of a trading cycle.
- Every fetch degrades gracefully: on failure callers fall back to config.
  A trading cycle must never fail because nseindia.com was slow.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

BASE = "https://www.nseindia.com"
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "nse_cache"

_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# Cache lifetimes, in seconds. Holidays change ~yearly; surveillance lists
# are revised periodically; announcements stream continuously.
TTL_HOLIDAYS = 7 * 24 * 3600
TTL_ASM = 24 * 3600
TTL_ANNOUNCEMENTS = 15 * 60
TTL_MARKET_STATE = 5 * 60


class NSEUnavailable(RuntimeError):
    """NSE could not be reached or returned something unusable."""


@dataclass
class Announcement:
    symbol: str
    title: str
    detail: str
    published: str
    url: str = ""


def to_nse_symbol(symbol: str) -> str:
    """RELIANCE.NS -> RELIANCE (NSE's own tickers carry no suffix)."""
    return symbol.split(".")[0].upper().strip()


# ── transport ──

def _fetch(path: str) -> Any:
    import httpx

    try:
        with httpx.Client(headers=_UA, timeout=25, follow_redirects=True) as c:
            c.get(BASE)  # seed cookies; NSE rejects cold requests
            resp = c.get(f"{BASE}{path}")
            if resp.status_code != 200:
                raise NSEUnavailable(f"{path}: HTTP {resp.status_code}")
            if "json" not in resp.headers.get("content-type", ""):
                raise NSEUnavailable(f"{path}: non-JSON response")
            return resp.json()
    except NSEUnavailable:
        raise
    except Exception as exc:
        raise NSEUnavailable(f"{path}: {type(exc).__name__}: {exc}") from exc


def _cache_path(name: str) -> Path:
    return CACHE_DIR / f"{name}.json"


def _read_cache(name: str, ttl: float) -> Optional[Any]:
    p = _cache_path(name)
    if not p.exists():
        return None
    try:
        blob = json.loads(p.read_text(encoding="utf-8"))
        if time.time() - float(blob.get("fetched_at", 0)) > ttl:
            return None
        return blob.get("data")
    except (ValueError, OSError):
        return None


def _write_cache(name: str, data: Any) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _cache_path(name).with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps({"fetched_at": time.time(), "data": data}, indent=2),
            encoding="utf-8",
        )
        tmp.replace(_cache_path(name))
    except OSError:
        pass  # caching is best-effort, never fatal


def _cached(name: str, ttl: float, path: str, refresh: bool = False) -> Any:
    if not refresh:
        hit = _read_cache(name, ttl)
        if hit is not None:
            return hit
    data = _fetch(path)
    _write_cache(name, data)
    return data


def _stale_cache(name: str) -> Optional[Any]:
    """Any cached copy regardless of age — better than nothing on failure."""
    p = _cache_path(name)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("data")
    except (ValueError, OSError):
        return None


# ── trading holidays ──

def fetch_trading_holidays(segment: str = "CM", refresh: bool = False) -> set[date]:
    """Official NSE holidays for a segment (CM = cash/equity).

    This is the authoritative source for dates that cannot be derived —
    lunar festivals move yearly, and NSE also closes for one-off events
    (e.g. a Maharashtra municipal election).
    """
    try:
        data = _cached("holidays", TTL_HOLIDAYS, "/api/holiday-master?type=trading", refresh)
    except NSEUnavailable:
        data = _stale_cache("holidays")
        if data is None:
            raise

    out: set[date] = set()
    for row in (data or {}).get(segment, []):
        raw = str(row.get("tradingDate", "")).strip()
        for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d"):
            try:
                out.add(datetime.strptime(raw, fmt).date())
                break
            except ValueError:
                continue
    if not out:
        raise NSEUnavailable(f"no holidays parsed for segment {segment}")
    return out


# ── surveillance (ASM) ──

def fetch_asm_symbols(refresh: bool = False) -> set[str]:
    """Symbols under Additional Surveillance Measure.

    ASM names carry punitive margins and heightened volatility; the risk
    config asks us to avoid them, and this is the list that makes that
    instruction real.
    """
    try:
        data = _cached("asm", TTL_ASM, "/api/reportASM", refresh)
    except NSEUnavailable:
        data = _stale_cache("asm")
        if data is None:
            raise

    out: set[str] = set()
    for bucket in ("longterm", "shortterm"):
        block = (data or {}).get(bucket) or {}
        rows = block.get("data", []) if isinstance(block, dict) else block
        for row in rows or []:
            sym = str(row.get("symbol", "")).strip().upper()
            if sym:
                out.add(sym)
    return out


# ── official session state ──

def fetch_market_state(refresh: bool = False) -> dict[str, Any]:
    """NSE's own view of whether the Capital Market segment is open."""
    data = _cached("market_state", TTL_MARKET_STATE, "/api/marketStatus", refresh)
    for m in (data or {}).get("marketState", []):
        if str(m.get("market", "")).lower().startswith("capital"):
            return {
                "market": m.get("market"),
                "status": m.get("marketStatus"),
                "is_open": str(m.get("marketStatus", "")).lower() == "open",
                "trade_date": m.get("tradeDate"),
            }
    raise NSEUnavailable("Capital Market state not present in response")


# ── corporate announcements ──

def fetch_announcements(refresh: bool = False) -> list[Announcement]:
    """Company disclosures filed with the exchange.

    Higher trust than media: these are the company's own filings, tagged
    with an exact NSE symbol, so relevance needs no keyword guessing.
    """
    try:
        data = _cached(
            "announcements", TTL_ANNOUNCEMENTS,
            "/api/corporate-announcements?index=equities", refresh,
        )
    except NSEUnavailable:
        data = _stale_cache("announcements")
        if data is None:
            raise

    out: list[Announcement] = []
    for row in data or []:
        sym = str(row.get("symbol", "")).strip().upper()
        if not sym:
            continue
        out.append(Announcement(
            symbol=sym,
            title=str(row.get("desc", "")).strip() or "Corporate announcement",
            detail=str(row.get("attchmntText", "")).strip()[:400],
            published=str(row.get("an_dt", "")).strip(),
            url=str(row.get("attchmntFile", "")).strip(),
        ))
    return out
