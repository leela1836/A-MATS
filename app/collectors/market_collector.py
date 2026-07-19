"""Live NSE/BSE market data via Yahoo Finance (yfinance).

Fetches OHLCV for `.NS` symbols and Indian index tickers, computes a small
set of indicators with pandas (no TA-Lib dependency), and derives a trend /
signal / confidence read that the market node turns into a MarketAnalysis.

A short in-memory TTL cache avoids hammering Yahoo on repeated runs of the
same symbol. Network failures raise MarketDataError; the market node treats
that as a non-finite feed so the evaluation gate halts the cycle.
"""
from __future__ import annotations

import time
import warnings
from typing import Optional

import pandas as pd

from app.config import get_config
from app.models.state import Direction, MarketAnalysis

warnings.filterwarnings("ignore", category=FutureWarning)


class MarketDataError(RuntimeError):
    """Raised when live data cannot be fetched for a symbol."""


# ── indicators (pandas) ──

def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, 1e-9)
    return 100.0 - 100.0 / (1.0 + rs)


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def compute_indicators(df: pd.DataFrame) -> dict[str, float]:
    close = df["Close"]
    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    ema200 = _ema(close, 200)
    rsi = _rsi(close, 14)
    atr = _atr(df, 14)
    return {
        "last_price": float(close.iloc[-1]),
        "ema_20": float(ema20.iloc[-1]),
        "ema_50": float(ema50.iloc[-1]),
        "ema_200": float(ema200.iloc[-1]),
        "rsi_14": float(rsi.iloc[-1]),
        "atr_14": float(atr.iloc[-1]),
    }


def signal_params(overrides: Optional[dict] = None) -> dict:
    """Signal thresholds from configs/market.yaml, overridable for A/B tests."""
    cfg = dict(get_config("market").get("signal", {}) or {})
    defaults = {
        "regime_filter": True,
        "min_trend_separation": 0.002,
        "rsi_long_max": 68.0,
        "rsi_short_min": 32.0,
    }
    merged = {**defaults, **cfg}
    if overrides:
        merged.update(overrides)
    return merged


def classify(
    ind: dict[str, float], params: Optional[dict] = None
) -> tuple[str, Direction, float]:
    """Derive (trend, signal, confidence) from indicator values.

    The regime filter is the important part: EMA20/EMA50 crossovers fire
    constantly in choppy markets, and taking every one is what made the
    unfiltered strategy bleed. Requiring price to agree with the long-term
    EMA200 trend suppresses counter-trend entries.
    """
    p = signal_params(params)
    price, ema20, ema50, rsi = (
        ind["last_price"], ind["ema_20"], ind["ema_50"], ind["rsi_14"],
    )
    ema200 = ind.get("ema_200", 0.0)
    sep = (ema20 - ema50) / ema50 if ema50 else 0.0
    min_sep = float(p["min_trend_separation"])

    if sep > min_sep and price > ema20:
        trend = "up"
    elif sep < -min_sep and price < ema20:
        trend = "down"
    else:
        trend = "sideways"

    # Long-term regime: only trade in the direction of the primary trend.
    if p.get("regime_filter") and ema200 > 0:
        regime_up, regime_down = price > ema200, price < ema200
    else:
        regime_up = regime_down = True

    if trend == "up" and rsi < float(p["rsi_long_max"]) and regime_up:
        signal = Direction.LONG
    elif trend == "down" and rsi > float(p["rsi_short_min"]) and regime_down:
        signal = Direction.SHORT
    else:
        signal = Direction.HOLD

    # Confidence: trend separation + momentum distance from neutral, clamped.
    strength = min(abs(sep) * 12.0, 0.5) + min(abs(rsi - 50) / 50.0 * 0.4, 0.4)
    confidence = round(min(max(0.3 + strength, 0.0), 0.95), 3) if signal != Direction.HOLD else 0.2
    return trend, signal, confidence


# ── provider ──

def fetch_history(symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    """Raw OHLCV history. Shared by the live provider and the backtester."""
    import yfinance as yf

    try:
        df = yf.Ticker(symbol).history(period=period, interval=interval)
    except Exception as exc:
        raise MarketDataError(f"fetch failed for {symbol}: {exc}") from exc
    if df is None or df.empty:
        raise MarketDataError(f"no data for {symbol}")
    return df


class YFinanceProvider:
    """Fetches and caches MarketAnalysis for a symbol."""

    def __init__(self):
        self._cache: dict[str, tuple[float, MarketAnalysis]] = {}
        market = get_config("market")
        self._ttl = float(market.get("data_fetching", {}).get("cache_ttl_seconds", 60))
        self._lookback = int(market.get("data_fetching", {}).get("lookback_days", 365))

    def get_analysis(self, symbol: str) -> MarketAnalysis:
        now = time.time()
        cached = self._cache.get(symbol)
        if cached and now - cached[0] < self._ttl:
            return cached[1]

        analysis = self._fetch(symbol)
        self._cache[symbol] = (now, analysis)
        return analysis

    def _fetch(self, symbol: str) -> MarketAnalysis:
        import yfinance as yf

        period = "6mo" if self._lookback >= 120 else "3mo"
        try:
            df = yf.Ticker(symbol).history(period=period, interval="1d")
        except Exception as exc:  # network / library errors
            raise MarketDataError(f"fetch failed for {symbol}: {exc}") from exc

        if df is None or df.empty or len(df) < 50:
            raise MarketDataError(f"insufficient data for {symbol}")

        ind = compute_indicators(df)
        trend, signal, confidence = classify(ind)
        return MarketAnalysis(
            symbol=symbol,
            last_price=round(ind["last_price"], 2),
            trend=trend,
            signal=signal,
            confidence=confidence,
            indicators={
                "ema_20": round(ind["ema_20"], 2),
                "ema_50": round(ind["ema_50"], 2),
                "rsi_14": round(ind["rsi_14"], 2),
                "atr_14": round(ind["atr_14"], 2),
            },
        )


_provider: Optional[YFinanceProvider] = None


def get_market_provider() -> YFinanceProvider:
    global _provider
    if _provider is None:
        _provider = YFinanceProvider()
    return _provider
