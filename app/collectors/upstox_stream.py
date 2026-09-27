"""Read-only Upstox V3 stream, using the existing Analytics Token."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd

from app.collectors.fyers_collector import Tick, validate_history
from app.collectors.upstox_collector import fetch_history_upstox, instrument_key
from app.market_calendar import IST


def credentials():
    token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
    if not token:
        raise ValueError("Set UPSTOX_ACCESS_TOKEN in .env")
    return token


def fetch_completed_history(symbol, now=None):
    now = now or datetime.now(timezone.utc)
    df = fetch_history_upstox(symbol, period="2y", interval="1d")
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(IST)
    df = df[df.index.date < now.astimezone(IST).date()]
    return validate_history(df, now)


def parse_ticks(message, mapping):
    if not isinstance(message, dict):
        return []
    ticks = []
    for key, item in (message.get("feeds") or {}).items():
        if key not in mapping or not isinstance(item, dict):
            continue
        quote = item.get("ltpc") or {}
        try:
            # ltt is exchange last-trade time in milliseconds, not receipt time.
            ticks.append(Tick(mapping[key], float(quote["ltp"]), float(quote["ltt"]) / 1000))
        except (KeyError, TypeError, ValueError):
            continue
    return ticks


def connect(symbols, on_tick, on_disconnect):
    import upstox_client

    mapping = {}
    for symbol in symbols:
        if not symbol.endswith(".NS"):
            raise ValueError("Only NSE cash equities supported")
        key = instrument_key(symbol)
        if not key:
            raise ValueError(f"No Upstox instrument for {symbol}")
        mapping[key] = symbol
    configuration = upstox_client.Configuration()
    configuration.access_token = credentials()
    stream = upstox_client.MarketDataStreamerV3(
        upstox_client.ApiClient(configuration), list(mapping), "ltpc")
    stream.auto_reconnect(True, 5, 10)

    def received(message):
        for tick in parse_ticks(message, mapping):
            on_tick(tick)

    stream.on("message", received)
    for event in ("open", "close", "error", "reconnecting", "autoReconnectStopped"):
        stream.on(event, lambda *_: on_disconnect())
    stream.connect()
    return stream
