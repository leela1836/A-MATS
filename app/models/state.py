"""Shared graph state and the Pydantic contracts passed between nodes.

The walking skeleton exercises the full node topology with simplified
payloads. Nested models are intentionally minimal for the MVP and will
grow as real agents replace the stubs.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional, TypedDict


from pydantic import BaseModel, Field


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


class ReasonedAnalysis(BaseModel):
    symbol: str
    thesis: str
    direction: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    entry_price: float
    stop_loss: float
    take_profit: float


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
    reasoned_analysis: Optional[ReasonedAnalysis]
    evaluation_scores: Optional[EvaluationScores]
    risk_assessment: Optional[RiskAssessment]
    decision: Optional[TradingDecision]
    execution_result: Optional[ExecutionResult]

    # Metadata
    errors: list[str]
    warnings: list[str]
    metrics: dict[str, Any]
    halted: bool
    halt_reason: str


def new_state(symbols: list[str], analysis_type: str = "combined") -> AgentState:
    """Construct a fresh state dict with metadata containers initialized."""
    return AgentState(
        symbols=symbols,
        analysis_type=analysis_type,
        market_analysis=None,
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
