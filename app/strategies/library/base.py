"""Shared types for the strategy library: the Context a strategy reads and the
StratSignal it proposes, plus a liquidity threshold every strategy respects."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

import pandas as pd

# Average daily turnover (₹ close × volume) below which a name is too thin to
# trade honestly — signals are noise and slippage eats any edge. ₹5 crore/day.
MIN_TURNOVER = 5_00_00_000.0


@dataclass
class StratSignal:
    """A concrete trade proposal from one strategy."""
    strategy: str
    direction: str          # "long" | "short"
    confidence: float       # 0..1
    entry: float
    stop: float
    target: float
    rationale: str


@dataclass
class Context:
    """Everything a strategy needs to judge a symbol — computed once, shared."""
    symbol: str
    price: float
    trend: str              # "up" | "down" | "sideways"
    regime: str             # "bull" | "bear" | "neutral"
    rsi: float
    atr: float
    ema20: float
    ema50: float
    ema200: float
    support: Optional[float]
    resistance: Optional[float]
    avg_turnover: float     # ₹ average daily turnover (liquidity)
    df: pd.DataFrame

    @property
    def liquid(self) -> bool:
        return self.avg_turnover >= MIN_TURNOVER


@runtime_checkable
class Strategy(Protocol):
    name: str
    kind: str               # "trend" | "reversion" | "breakout" (for routing/metadata)

    def evaluate(self, ctx: Context) -> Optional[StratSignal]:
        """Propose a trade for this context, or None if the setup doesn't fit."""
        ...


def avg_turnover(df: pd.DataFrame, window: int = 20) -> float:
    """Mean daily ₹-turnover over the last `window` bars (0 if no volume)."""
    if "Volume" not in df.columns or df.empty:
        return 0.0
    tw = (df["Close"] * df["Volume"]).tail(window)
    return float(tw.mean()) if len(tw) else 0.0


def build_context(
    symbol: str, df: pd.DataFrame, ind: dict, trend: str, regime: str,
    support: Optional[float], resistance: Optional[float],
) -> Context:
    """Assemble a Context from an OHLCV frame + precomputed indicators."""
    return Context(
        symbol=symbol, price=ind["last_price"], trend=trend, regime=regime,
        rsi=ind.get("rsi_14", 50.0), atr=ind.get("atr_14", 0.0),
        ema20=ind.get("ema_20", 0.0), ema50=ind.get("ema_50", 0.0),
        ema200=ind.get("ema_200", 0.0), support=support, resistance=resistance,
        avg_turnover=avg_turnover(df), df=df,
    )
