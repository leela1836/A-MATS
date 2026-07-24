"""Shared graph state and the Pydantic contracts passed between nodes.

The walking skeleton exercises the full node topology with simplified
payloads. Nested models are intentionally minimal for the MVP and will
grow as real agents replace the stubs.
"""
from __future__ import annotations

import operator
from enum import Enum
from typing import Annotated, Any, Optional, TypedDict


from pydantic import BaseModel, Field


def merge_metrics(a: Optional[dict], b: Optional[dict]) -> dict:
    """Reducer so parallel nodes can each contribute their own metrics key."""
    return {**(a or {}), **(b or {})}


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"
    HOLD = "hold"


class MarketAnalysis(BaseModel):
    symbol: str
    last_price: float
    trend: str  # "up" | "down" | "sideways"
    signal: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    indicators: dict[str, float] = Field(default_factory=dict)
    # Candlestick context: detected patterns plus their netted bias.
    patterns: list[dict[str, Any]] = Field(default_factory=list)
    pattern_bias: str = "none"
    pattern_score: float = 0.0
    # Learned validator's P(win) for the proposed entry (None if untrained).
    nn_score: Optional[float] = None


class NewsArticleRef(BaseModel):
    title: str
    source: str
    url: str = ""
    relevance: str = "market"
    age_hours: Optional[float] = None


class NewsSignals(BaseModel):
    symbol: str
    sentiment_score: float = Field(ge=-1.0, le=1.0)  # -1 bearish .. +1 bullish
    sentiment_label: str = "neutral"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    key_events: list[str] = Field(default_factory=list)
    summary: str = ""
    article_count: int = 0
    sources_used: list[str] = Field(default_factory=list)
    articles: list[NewsArticleRef] = Field(default_factory=list)


class ReasonedAnalysis(BaseModel):
    symbol: str
    thesis: str
    direction: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    entry_price: float
    stop_loss: float
    take_profit: float
    # Trade-plan narrative + derived numbers, so a proposal reads as a plan,
    # not three bare prices.
    entry_rationale: str = ""      # why THIS level is a good entry
    confirmation: str = ""         # what must happen to trigger/validate it
    invalidation: str = ""         # what would prove the thesis wrong
    risk_reward: float = 0.0       # |target-entry| / |entry-stop| (computed)
    est_hold_days: Optional[int] = None  # ATR-based holding-duration estimate


class EvaluationScores(BaseModel):
    passed: bool
    overall_score: float = Field(ge=0.0, le=1.0)
    dimensions: dict[str, float] = Field(default_factory=dict)
    reason: str = ""


class RiskAssessment(BaseModel):
    approved: bool
    position_size_percent: float = Field(ge=0.0)
    risk_per_trade_percent: float = Field(ge=0.0)
    reason: str = ""


class TradingDecision(BaseModel):
    symbol: str
    action: Direction
    size_percent: float = Field(ge=0.0)
    entry_price: float
    stop_loss: float
    take_profit: float
    rationale: str = ""


class ExecutionResult(BaseModel):
    symbol: str
    filled: bool
    action: Direction = Direction.HOLD
    qty: int = 0
    fill_price: float = 0.0
    size_percent: float = 0.0
    mode: str = "paper"  # "simulation" | "paper" | "live"
    note: str = ""


class AgentState(TypedDict, total=False):
    """State threaded through the LangGraph state machine."""

    # Input
    symbols: list[str]
    analysis_type: str

    # Agent / engine outputs
    market_analysis: Optional[MarketAnalysis]
    news_signals: Optional[NewsSignals]
    reasoned_analysis: Optional[ReasonedAnalysis]
    evaluation_scores: Optional[EvaluationScores]
    risk_assessment: Optional[RiskAssessment]
    decision: Optional[TradingDecision]
    execution_result: Optional[ExecutionResult]

    # Metadata. These carry reducers because market and news run concurrently
    # and would otherwise conflict writing the same key in one superstep.
    errors: Annotated[list[str], operator.add]
    warnings: Annotated[list[str], operator.add]
    metrics: Annotated[dict[str, Any], merge_metrics]
    halted: bool
    halt_reason: str


def new_state(symbols: list[str], analysis_type: str = "combined") -> AgentState:
    """Construct a fresh state dict with metadata containers initialized."""
    return AgentState(
        symbols=symbols,
        analysis_type=analysis_type,
        market_analysis=None,
        news_signals=None,
        reasoned_analysis=None,
        evaluation_scores=None,
        risk_assessment=None,
        decision=None,
        execution_result=None,
        errors=[],
        warnings=[],
        metrics={},
        halted=False,
        halt_reason="",
    )
