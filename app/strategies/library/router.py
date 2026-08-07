"""The router: liquidity gate + regime rules + pick the best-fitting strategy.

Selection is RULE-BASED (each strategy fires only when its conditions hold; the
router keeps the highest-confidence one that survives the gates). It never picks
by "which strategy has the best recent P&L" — that would data-mine noise on a
tiny sample. Performance weighting is a deliberate future step, gated on a real
out-of-sample record.
"""
from __future__ import annotations

from typing import Optional

from app.strategies.library.base import Context, StratSignal
from app.strategies.library.strategies import Breakout, MeanReversion, TrendFollowing
from app.strategies.regime import shorts_allowed

# Registry — order is the tie-breaker priority when confidences match.
STRATEGIES = [TrendFollowing(), Breakout(), MeanReversion()]


def route(ctx: Context, want_direction: Optional[str] = None) -> Optional[StratSignal]:
    """Best strategy proposal for this context, or None if nothing qualifies.

    Gates, in order: liquidity (thin names dropped), each strategy's own fit,
    the requested direction (if given), and the regime rule (shorts only in a
    confirmed bear tape). Among survivors, highest confidence wins.
    """
    if not ctx.liquid:
        return None
    props = [s.evaluate(ctx) for s in STRATEGIES]
    props = [p for p in props if p is not None]
    if want_direction:
        props = [p for p in props if p.direction == want_direction]
    props = [p for p in props
             if p.direction != "short" or shorts_allowed({"regime": ctx.regime})]
    if not props:
        return None
    props.sort(key=lambda p: -p.confidence)
    return props[0]


def classify_strategy(ctx: Context, direction: str) -> str:
    """Which library strategy best *explains* an already-chosen setup — used to
    tag journal decisions so pattern/strategy efficacy can be measured later.
    Falls back to trend_following (the screener's own engine)."""
    sig = route(ctx, want_direction=direction)
    return sig.strategy if sig else "trend_following"
