"""Read-only FYERS data: completed daily candles and timestamped WebSocket ticks."""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
import pandas as pd

from app.market_calendar import IST


def fyers_symbol(symbol: str) -> str:
    if not re.fullmatch(r"[A-Z0-9&-]+\.NS", symbol):
        raise ValueError("Only NSE cash equities ending in .NS are supported")
    return f"NSE:{symbol[:-3]}-EQ"


def credentials() -> str:
    app_id = os.getenv("FYERS_APP_ID", "").strip()
    token = os.getenv("FYERS_ACCESS_TOKEN", "").strip()
    if not app_id or not token:
        raise ValueError("Set FYERS_APP_ID and FYERS_ACCESS_TOKEN in .env")
    return f"{app_id}:{token}"


@dataclass(frozen=True)
class Tick:
    symbol: str
    price: float
    timestamp: float

    def fresh(self, now: datetime, max_age: float = 30) -> bool:
        return (math.isfinite(self.price) and self.price > 0
                and math.isfinite(self.timestamp)
                and 0 <= now.timestamp() - self.timestamp <= max_age)


def parse_tick(message: dict, mapping: dict[str, str]) -> Tick | None:
    symbol = mapping.get(message.get("symbol"))
    if not symbol or message.get("type") != "sf":
        return None
    try:
        # Missing exchange time must never be replaced by local receipt time.
        tick = Tick(symbol, float(message["ltp"]), float(message["last_traded_time"]))
        return tick if math.isfinite(tick.price) and tick.price > 0 else None
    except (KeyError, TypeError, ValueError):
        return None


def fetch_completed_history(symbol: str, now: datetime | None = None) -> pd.DataFrame:
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(IST).date()
    rows = []
    # Two bounded requests supply enough warmup for EMA200.
    with httpx.Client(timeout=20, headers={"Authorization": credentials()}) as client:
        for start, end in ((today - timedelta(days=730), today - timedelta(days=366)),
                           (today - timedelta(days=365), today - timedelta(days=1))):
            response = client.get("https://api-t1.fyers.in/data/history", params={
                "symbol": fyers_symbol(symbol), "resolution": "D", "date_format": "1",
                "range_from": start.isoformat(), "range_to": end.isoformat(), "cont_flag": "1",
            })
            response.raise_for_status()
            payload = response.json()
            if payload.get("s") != "ok":
                raise ValueError(f"FYERS history rejected (code {payload.get('code')})")
            rows.extend(payload.get("candles", []))
    df = pd.DataFrame(rows, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
    df.index = pd.to_datetime(df.pop("timestamp"), unit="s", utc=True).dt.tz_convert(IST)
    return validate_history(df, now)


def validate_history(df, now):
    today = now.astimezone(IST).date()
    df = df.sort_index().astype(float)
    if df.index.has_duplicates or len(df) < 210 or df.isna().any().any():
        raise ValueError("Missing or duplicate daily history")
    if not all(math.isfinite(v) for v in df.to_numpy().flat):
        raise ValueError("Non-finite history")
    if ((df[["Open", "High", "Low", "Close"]] <= 0).any().any()
            or (df.Volume < 0).any()
            or (df.High < df[["Open", "Low", "Close"]].max(axis=1)).any()
            or (df.Low > df[["Open", "High", "Close"]].min(axis=1)).any()):
        raise ValueError("Invalid OHLCV history")
    if df.index[-1].date() >= today or (today - df.index[-1].date()).days > 7:
        raise ValueError("Incomplete or stale daily history")
    return df


def connect(symbols, on_tick, on_disconnect):
    """No order client is instantiated; only the official data socket is used."""
    from fyers_apiv3.FyersWebsocket import data_ws

    mapping = {fyers_symbol(s): s for s in symbols}

    def opened():
        on_disconnect()  # discard pre-reconnect quotes until fresh ticks arrive
        socket.subscribe(symbols=list(mapping), data_type="SymbolUpdate")

    def received(message):
        if isinstance(message, dict):
            tick = parse_tick(message, mapping)
            if tick:
                on_tick(tick)

    socket = data_ws.FyersDataSocket(
        access_token=credentials(), log_path="", litemode=False,
        write_to_file=False, reconnect=True, on_connect=opened,
        on_message=received, on_error=lambda *_: on_disconnect(),
        on_close=lambda *_: on_disconnect(),
    )
    socket.connect()
    return socket
