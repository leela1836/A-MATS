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
    RiskAssessment,
    TradingDecision,
)
from app.observability.trace import timed


def market_node(state: AgentState) -> dict:
    """Fetch live NSE data and derive a technical read.

    On a data failure we return a non-finite price so the evaluation gate
    halts the cycle rather than trading on a bad feed.
    """
    from app.collectors.market_collector import MarketDataError, get_market_provider

    symbol = state["symbols"][0]
    try:
        analysis = get_market_provider().get_analysis(symbol)
        return {"market_analysis": analysis}
    except MarketDataError as exc:
        bad = MarketAnalysis(
            symbol=symbol,
            last_price=float("nan"),
            trend="unknown",
            signal=Direction.HOLD,
            confidence=0.0,
            indicators={},
        )
        return {
            "market_analysis": bad,
            "warnings": [f"market data error: {exc}"],
        }


def reasoning_node(state: AgentState) -> dict:
    """Delegate to the Reasoning Engine (LLM, with deterministic fallback)."""
    from app.agents.reasoning import reason

    ma = state["market_analysis"]
    with timed() as t:
        reasoned, usage = reason(ma)

    metrics = dict(state.get("metrics") or {})
    metrics["reasoning"] = {**usage, "duration_ms": round(t.ms, 2)}
    return {"reasoned_analysis": reasoned, "metrics": metrics}


def evaluation_node(state: AgentState) -> dict:
    """Analytical gate: veto malformed proposals BEFORE risk sizing.

    Three outcomes:
      - non-finite feed        -> HALT (bad data, never trade on it)
      - HOLD signal (finite)   -> pass through as a legitimate no-trade
      - LONG/SHORT proposal    -> score ordering + R:R, pass/halt on threshold
    """
    r = state["reasoned_analysis"]
    agent_cfg = get_config("agent")["evaluation_engine"]
    min_pass = float(agent_cfg.get("min_pass_score", 0.6))

    prices_finite = all(
        _finite(v) for v in (r.entry_price, r.stop_loss, r.take_profit)
    )

    # Bad feed: halt hard.
    if not prices_finite:
        scores = EvaluationScores(
            passed=False, overall_score=0.0,
            dimensions={"prices_valid": 0.0},
            reason="non-finite prices (bad feed)",
        )
        return {
            "evaluation_scores": scores,
            "halted": True,
            "halt_reason": f"evaluation rejected: {scores.reason}",
        }

    # Legitimate no-trade: pass through, no order will be placed downstream.
    if r.direction == Direction.HOLD:
        return {"evaluation_scores": EvaluationScores(
            passed=True, overall_score=1.0,
            dimensions={"prices_valid": 1.0, "no_trade": 1.0},
            reason="no trade (hold signal)",
        )}

    # Tradeable proposal: score ordering, confidence, and risk/reward.
    if r.direction == Direction.LONG:
        ordered = r.stop_loss < r.entry_price < r.take_profit
    else:  # SHORT
        ordered = r.take_profit < r.entry_price < r.stop_loss

    reward = abs(r.take_profit - r.entry_price)
    risk = abs(r.entry_price - r.stop_loss)
    rr = reward / risk if risk else 0.0

    checks = {
        "prices_valid": 1.0,
        "levels_ordered": 1.0 if ordered else 0.0,
        "confidence": r.confidence,
        "risk_reward": min(rr / 3.0, 1.0),  # normalize against a 3:1 target
    }
    overall = 0.0 if not ordered else sum(checks.values()) / len(checks)
    passed = ordered and overall >= min_pass

    scores = EvaluationScores(
        passed=passed,
        overall_score=round(overall, 4),
        dimensions=checks,
        reason="ok" if passed else "failed ordering/scoring checks",
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

    # HOLD is a no-position, not a risk rejection: pass through with zero size.
    if r.direction == Direction.HOLD:
        return {"risk_assessment": RiskAssessment(
            approved=True, position_size_percent=0.0,
            risk_per_trade_percent=0.0, reason="no position (hold)",
        )}

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
    """Execute the decision against the in-app paper portfolio.

    No external broker: the order fills against our own virtual INR portfolio.
    HOLD decisions place no order. Order size comes from the risk-approved
    size_percent, converted to whole shares at the slippage-adjusted price.
    """
    from app.execution.paper_broker import get_broker

    trading_cfg = get_config("trading")["mode"]
    mode = trading_cfg.get("current", "paper")
    block = trading_cfg.get(mode, {})
    slippage_pct = float(block.get("percentage_slippage", 0.0))

    d = state["decision"]
    ma = state["market_analysis"]
    ref_price = ma.last_price

    # HOLD → no trade.
    if d.action == Direction.HOLD:
        return {"execution_result": ExecutionResult(
            symbol=d.symbol, filled=False, action=d.action, mode=mode,
            note="hold — no order placed",
        )}

    side = "buy" if d.action == Direction.LONG else "sell"
    # Slippage pushes the fill against us (worse) on both sides.
    fill_price = ref_price * (1 + slippage_pct) if side == "buy" else ref_price * (1 - slippage_pct)
    fill_price = round(fill_price, 2)

    broker = get_broker()
    qty = broker.size_to_qty(d.size_percent, fill_price, {d.symbol: ref_price})
    if qty <= 0:
        return {"execution_result": ExecutionResult(
            symbol=d.symbol, filled=False, action=d.action, fill_price=fill_price,
            size_percent=d.size_percent, mode=mode,
            note="size too small for one share at current equity",
        )}

    trade = broker.place_order(d.symbol, side, qty, fill_price, note=d.rationale[:120])
    return {"execution_result": ExecutionResult(
        symbol=d.symbol, filled=True, action=d.action, qty=qty,
        fill_price=trade.price, size_percent=d.size_percent, mode=mode,
        note=f"paper {side} {qty} @ {trade.price} (comm {trade.commission})",
    )}


def _finite(x: float) -> bool:
    return x == x and x not in (float("inf"), float("-inf"))
