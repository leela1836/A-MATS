"""Runs one trading cycle through the compiled graph and shapes the result."""
from __future__ import annotations

from app.execution.paper_broker import get_broker
from app.models.state import AgentState, new_state
from app.observability.trace import NodeTrace, RunTrace, timed
from app.workflows.graph import GRAPH


def run_cycle(symbol: str, run_id: str = "run") -> dict:
    """Execute the skeleton graph for one symbol and return a serializable result."""
    state: AgentState = new_state([symbol])
    trace = RunTrace(run_id=run_id)

    with timed() as t:
        final: AgentState = GRAPH.invoke(state)
    trace.record(NodeTrace(node="graph", duration_ms=t.ms, note="full cycle"))

    # Mark the portfolio to the price this cycle saw so equity reflects the run.
    ma = final.get("market_analysis")
    last_prices = {symbol: ma.last_price} if ma and ma.last_price is not None else {}
    portfolio = get_broker().snapshot(last_prices)

    return {
        "run_id": run_id,
        "symbol": symbol,
        "halted": final.get("halted", False),
        "halt_reason": final.get("halt_reason", ""),
        "market_analysis": _dump(final.get("market_analysis")),
        "reasoned_analysis": _dump(final.get("reasoned_analysis")),
        "evaluation_scores": _dump(final.get("evaluation_scores")),
        "risk_assessment": _dump(final.get("risk_assessment")),
        "decision": _dump(final.get("decision")),
        "execution_result": _dump(final.get("execution_result")),
        "portfolio": portfolio,
        "trace": trace.as_dict(),
    }


def _dump(model):
    return model.model_dump(mode="json") if model is not None else None
