"""The concrete strategies. Each is small, self-describing, and returns a
StratSignal only when its own preconditions fit — so applicability is encoded in
the strategy, and the router just collects whatever fired."""
from __future__ import annotations

from typing import Optional

from app.strategies.library.base import Context, StratSignal


def _levels(direction: str, price: float, atr: float, rr: float = 2.0,
            k: float = 1.5) -> tuple[float, float, float]:
    """ATR-based entry/stop/target with a reward:risk of `rr`."""
    dist = max(k * atr, price * 0.005)  # floor so a zero-ATR name still gets a stop
    if direction == "long":
        return price, round(price - dist, 2), round(price + dist * rr, 2)
    return price, round(price + dist, 2), round(price - dist * rr, 2)


class TrendFollowing:
    """Ride an established trend confirmed by the long-term EMA regime."""
    name = "trend_following"
    kind = "trend"

    def evaluate(self, ctx: Context) -> Optional[StratSignal]:
        if ctx.trend == "up" and ctx.price > ctx.ema200 and ctx.rsi < 68:
            sep = (ctx.ema20 - ctx.ema50) / ctx.ema50 if ctx.ema50 else 0.0
            conf = round(min(max(0.45 + sep * 12.0, 0.4), 0.9), 3)
            e, s, t = _levels("long", ctx.price, ctx.atr)
            return StratSignal(self.name, "long", conf, e, s, t,
                               "uptrend above the 200-EMA, momentum intact")
        if ctx.trend == "down" and ctx.price < ctx.ema200 and ctx.rsi > 32:
            e, s, t = _levels("short", ctx.price, ctx.atr)
            return StratSignal(self.name, "short", 0.55, e, s, t,
                               "downtrend below the 200-EMA")
        return None


class MeanReversion:
    """Fade an extreme back toward the mean — for ranging, not trending, tape."""
    name = "mean_reversion"
    kind = "reversion"

    def evaluate(self, ctx: Context) -> Optional[StratSignal]:
        if ctx.rsi < 32 and ctx.support and ctx.price <= ctx.support * 1.03:
            conf = round(min(0.4 + (32 - ctx.rsi) / 32 * 0.4, 0.85), 3)
            e, s, t = _levels("long", ctx.price, ctx.atr, rr=1.5)
            return StratSignal(self.name, "long", conf, e, s, t,
                               "oversold bounce off support")
        if ctx.rsi > 68 and ctx.resistance and ctx.price >= ctx.resistance * 0.97:
            conf = round(min(0.4 + (ctx.rsi - 68) / 32 * 0.4, 0.85), 3)
            e, s, t = _levels("short", ctx.price, ctx.atr, rr=1.5)
            return StratSignal(self.name, "short", conf, e, s, t,
                               "overbought fade at resistance")
        return None


class Breakout:
    """Enter on a volume-confirmed break of a support/resistance level."""
    name = "breakout"
    kind = "breakout"

    def evaluate(self, ctx: Context) -> Optional[StratSignal]:
        if "Volume" not in ctx.df.columns or len(ctx.df) < 20:
            return None
        vol = ctx.df["Volume"]
        if float(vol.iloc[-1]) <= 1.5 * float(vol.tail(20).mean() or 0):
            return None  # needs a genuine volume surge
        if ctx.resistance and ctx.price > ctx.resistance and ctx.trend != "down":
            e, s, t = _levels("long", ctx.price, ctx.atr, rr=2.5)
            return StratSignal(self.name, "long", 0.6, e, s, t,
                               "volume breakout above resistance")
        if ctx.support and ctx.price < ctx.support and ctx.trend != "up":
            e, s, t = _levels("short", ctx.price, ctx.atr, rr=2.5)
            return StratSignal(self.name, "short", 0.6, e, s, t,
                               "volume breakdown below support")
        return None
