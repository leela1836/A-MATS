"""Universe screener — the funnel that turns hundreds of symbols into a shortlist.

Stage 1 (this module): run the DETERMINISTIC analysis over the whole universe
— the same one the pipeline uses, carrying every dependent signal (technical
signal + confidence, learned NN P(win), candlestick bias, support/resistance,
trend) — score each actionable setup, and keep the top N. No LLM, no order.

Stage 2 (scan.run_screen_scan): the survivors go through the full pipeline for
a reasoned plan and a paper fill. So the expensive work only ever touches the
finalists, not the whole universe.

Honest limits: this fetches one request per symbol from yfinance. Hundreds of
symbols is minutes of fetching and can trip Yahoo's rate limiting from a cloud
IP — throttle, cache, or move to a real data feed before scaling past ~200.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from app.collectors.market_collector import MarketDataError, get_market_provider
from app.config import get_config
from app.models.state import Direction, MarketAnalysis

UNIVERSE_FILE = Path(__file__).resolve().parent.parent.parent / "configs" / "universe.txt"


@dataclass
class Candidate:
    symbol: str
    direction: str          # long | short
    score: float            # 0..1 composite of the dependent signals
    confidence: float
    nn_score: Optional[float]
    trend: str
    last_price: float
    support: Optional[float]
    resistance: Optional[float]
    room_pct: float         # % room to the level the trade targets
    pattern_bias: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "direction": self.direction,
            "score": round(self.score, 4), "confidence": round(self.confidence, 3),
            "nn_score": self.nn_score, "trend": self.trend,
            "last_price": self.last_price, "support": self.support,
            "resistance": self.resistance, "room_pct": round(self.room_pct, 2),
            "pattern_bias": self.pattern_bias,
        }


def load_universe(path: Path = UNIVERSE_FILE) -> list[str]:
    """Tickers from configs/universe.txt, falling back to the config watchlist."""
    if path.exists():
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                out.append(s.upper())
        if out:
            return out
    syms = (get_config("market").get("symbols") or {}).get("equities") or []
    return [str(s).upper() for s in syms]


def _room_pct(ma: MarketAnalysis) -> float:
    """Percent room to the level the trade aims at: resistance for a long,
    support for a short. Missing opposing level => open road (capped)."""
    price = ma.last_price or 0.0
    if price <= 0:
        return 0.0
    if ma.signal == Direction.LONG:
        return (ma.resistance - price) / price * 100 if ma.resistance else 10.0
    if ma.signal == Direction.SHORT:
        return (price - ma.support) / price * 100 if ma.support else 10.0
    return 0.0


def _score(ma: MarketAnalysis) -> float:
    """Blend the dependent signals into one comparable 0..1 number.

    Weights favour the learned validator and the rule engine's own confidence,
    with candlestick agreement and room-to-target as tie-breakers.
    """
    nn = ma.nn_score if ma.nn_score is not None else 0.5
    conf = ma.confidence
    want = "bullish" if ma.signal == Direction.LONG else "bearish"
    if ma.pattern_bias == want:
        agree = 1.0
    elif ma.pattern_bias in ("none", "mixed"):
        agree = 0.5
    else:
        agree = 0.0  # candlesticks contradict the signal
    room = max(0.0, min(_room_pct(ma) / 10.0, 1.0))  # 10%+ room = full marks
    return round(0.40 * nn + 0.30 * conf + 0.20 * agree + 0.10 * room, 4)


def _to_candidate(ma: MarketAnalysis) -> Candidate:
    return Candidate(
        symbol=ma.symbol,
        direction=ma.signal.value,
        score=_score(ma),
        confidence=ma.confidence,
        nn_score=ma.nn_score,
        trend=ma.trend,
        last_price=ma.last_price,
        support=ma.support,
        resistance=ma.resistance,
        room_pct=_room_pct(ma),
        pattern_bias=ma.pattern_bias,
    )


def screen_universe(
    symbols: Optional[list[str]] = None,
    top_n: int = 20,
    throttle_s: float = 0.0,
) -> tuple[list[Candidate], dict[str, float]]:
    """Analyse every symbol; return (top-N ranked candidates, price map for ALL
    successfully-fetched symbols). The full price map lets the caller resolve
    open trades even for symbols that fell out of the shortlist.
    """
    symbols = symbols or load_universe()
    provider = get_market_provider()
    prices: dict[str, float] = {}
    candidates: list[Candidate] = []

    for sym in symbols:
        try:
            ma = provider.get_analysis(sym)
        except (MarketDataError, Exception):
            continue  # unresolved ticker / bad feed — skip, don't sink the sweep
        if isinstance(ma.last_price, (int, float)):
            prices[sym] = float(ma.last_price)
        if ma.signal in (Direction.LONG, Direction.SHORT):
            candidates.append(_to_candidate(ma))
        if throttle_s:
            time.sleep(throttle_s)

    candidates.sort(key=lambda c: -c.score)
    return candidates[:top_n], prices
