"""Strategy library — pluggable, self-describing trade strategies + a router.

Each strategy reads the same `Context` (price history, indicators, trend, regime,
liquidity) and either proposes a `StratSignal` or passes. The `router` applies the
liquidity gate + regime rules and picks the best-fitting proposal per symbol — so
the agent selects a strategy *per trade by its conditions* (rule-based), not by
data-mining which one "won" recently.
"""
from app.strategies.library.base import (
    MIN_TURNOVER, Context, StratSignal, Strategy, build_context,
)
from app.strategies.library.router import STRATEGIES, classify_strategy, route

__all__ = [
    "MIN_TURNOVER", "Context", "StratSignal", "Strategy", "build_context",
    "STRATEGIES", "classify_strategy", "route",
]
