"""Deterministic stub nodes for the walking skeleton.

Each node takes the shared AgentState and returns a partial update dict, the
LangGraph node contract. There are NO LLM calls here yet — these stubs prove
the graph topology, the evaluation gate, and the simulation logging end to
end. Real agents (app/agents/*) will replace these one node at a time.
"""
from __future__ import annotations

from app.config import get_config
from app.models.state import (
    AgentState,
    Direction,
    EvaluationScores,
    ExecutionResult,
    MarketAnalysis,
    ReasonedAnalysis,
    RiskAssessment,
    TradingDecision,
)


# A tiny fixed price book so the skeleton runs without any data feed.
_FIXTURE_PRICES: dict[str, float] = {
    "AAPL": 190.0,
    "MSFT": 420.0,
    "SPY": 540.0,
    "NVDA": 120.0,
    "__BADFEED__": float("nan"),  # used by tests to trip the evaluation gate
}


def market_node(state: AgentState) -> dict:
    symbol = state["symbols"][0]
    price = _FIXTURE_PRICES.get(symbol, 100.0)
    analysis = MarketAnalysis(
        symbol=symbol,
        last_price=price,
        trend="up",
        signal=Direction.LONG,
        confidence=0.72,
        indicators={"rsi": 58.0, "ema_20": price * 0.98},
    )
    return {"market_analysis": analysis}


def reasoning_node(state: AgentState) -> dict:
    ma = state["market_analysis"]
    entry = ma.last_price
    reasoned = ReasonedAnalysis(
        symbol=ma.symbol,
        thesis=f"{ma.symbol} trend is {ma.trend}; momentum supports a {ma.signal.value} bias.",
        direction=ma.signal,
        confidence=ma.confidence,
        entry_price=entry,
        stop_loss=entry * 0.97,
        take_profit=entry * 1.09,
    )
    return {"reasoned_analysis": reasoned}


def evaluation_node(state: AgentState) -> dict:
    """Analytical gate: veto illogical or malformed proposals BEFORE risk sizing."""
    r = state["reasoned_analysis"]
    agent_cfg = get_config("agent")["evaluation_engine"]
    min_pass = float(agent_cfg.get("min_pass_score", 0.6))

    checks: dict[str, float] = {}

    # Sanity: prices must be finite and ordered for the stated direction.
    prices_finite = all(
        _finite(v) for v in (r.entry_price, r.stop_loss, r.take_profit)
    )
    checks["prices_valid"] = 1.0 if prices_finite else 0.0

    if prices_finite and r.direction == Direction.LONG:
        ordered = r.stop_loss < r.entry_price < r.take_profit
    elif prices_finite and r.direction == Direction.SHORT:
        ordered = r.take_profit < r.entry_price < r.stop_loss
    else:
        ordered = False
    checks["levels_ordered"] = 1.0 if ordered else 0.0
    checks["confidence"] = r.confidence

    # Risk/reward must clear 1.0 to be worth taking.
    if prices_finite and ordered:
        reward = abs(r.take_profit - r.entry_price)
        risk = abs(r.entry_price - r.stop_loss)
        rr = reward / risk if risk else 0.0
    else:
        rr = 0.0
    checks["risk_reward"] = min(rr / 3.0, 1.0)  # normalize against a 3:1 target

    hard_fail = not (prices_finite and ordered)
    overall = 0.0 if hard_fail else sum(checks.values()) / len(checks)
    passed = (not hard_fail) and overall >= min_pass

    scores = EvaluationScores(
        passed=passed,
        overall_score=round(overall, 4),
        dimensions=checks,
        reason="ok" if passed else "failed sanity/scoring checks",
    )
    update: dict = {"evaluation_scores": scores}
    if not passed:
        update["halted"] = True
        update["halt_reason"] = f"evaluation rejected: {scores.reason}"
    return update


def risk_node(state: AgentState) -> dict:
    risk_cfg = get_config("risk")
    per_trade = risk_cfg["per_trade"]
    sizing = risk_cfg["position_sizing"]

    r = state["reasoned_analysis"]
    size = float(sizing.get("default_size_percent", 2.0))
    max_size = float(sizing.get("max_size_percent", 10.0))
    size = min(size * (1.0 + r.confidence), max_size)

    approved = r.confidence >= float(per_trade.get("min_confidence_score", 0.4))
    assessment = RiskAssessment(
        approved=approved,
        position_size_percent=round(size, 3),
        risk_per_trade_percent=float(per_trade.get("max_risk_percent", 1.0)),
        reason="within limits" if approved else "confidence below min_confidence_score",
    )
    update: dict = {"risk_assessment": assessment}
    if not approved:
        update["halted"] = True
        update["halt_reason"] = f"risk rejected: {assessment.reason}"
    return update


def decision_node(state: AgentState) -> dict:
    r = state["reasoned_analysis"]
    ra = state["risk_assessment"]
    decision = TradingDecision(
        symbol=r.symbol,
        action=r.direction,
        size_percent=ra.position_size_percent,
        entry_price=r.entry_price,
        stop_loss=r.stop_loss,
        take_profit=r.take_profit,
        rationale=r.thesis,
    )
    return {"decision": decision}


def execution_node(state: AgentState) -> dict:
    """Simulation-only fill. Never touches a broker in the skeleton."""
    trading_cfg = get_config("trading")
    mode = trading_cfg["mode"].get("current", "simulation")
    sim = trading_cfg["mode"].get("simulation", {})
    slippage = float(sim.get("fixed_slippage", 0.0))

    d = state["decision"]
    fill_price = d.entry_price + (slippage if d.action == Direction.LONG else -slippage)
    result = ExecutionResult(
        symbol=d.symbol,
        filled=True,
        fill_price=round(fill_price, 4),
        size_percent=d.size_percent,
        mode=mode,
        note="simulated fill (skeleton)",
    )
    return {"execution_result": result}


def _finite(x: float) -> bool:
    return x == x and x not in (float("inf"), float("-inf"))
