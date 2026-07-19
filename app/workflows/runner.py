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

    # Per-node LLM accounting recorded by the agents into state["metrics"].
    for node, m in (final.get("metrics") or {}).items():
        trace.record(NodeTrace(
            node=node,
            duration_ms=float(m.get("duration_ms", 0.0)),
            prompt_tokens=int(m.get("prompt_tokens", 0)),
            completion_tokens=int(m.get("completion_tokens", 0)),
            cost_usd=float(m.get("cost_usd", 0.0)),
            note=f"{m.get('source', '?')}"
                 + (f" · {m['model']}" if m.get("model") else "")
                 + (f" · {m['reason']}" if m.get("reason") else ""),
        ))
    trace.wall_ms = t.ms

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
