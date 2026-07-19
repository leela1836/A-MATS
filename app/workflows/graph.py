"""LangGraph state machine wiring.

Topology:

    START ─┬─> market ─┐
           └─> news   ─┴─> reasoning -> evaluation -> [gate] -> risk
                                                                 │
                          [gate] -> decision -> execution -> END

`market` and `news` are independent gathering nodes and run concurrently;
`reasoning` joins them (LangGraph waits for both incoming edges before
running it). Their shared metadata keys use reducers — see AgentState.

The [gate] edges route to END early when a node sets state["halted"], so a
rejected proposal never reaches risk sizing or execution.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.models.state import AgentState
from app.workflows import nodes


def _gate(state: AgentState) -> str:
    """Return 'halt' if a prior node halted the run, else 'continue'."""
    return "halt" if state.get("halted") else "continue"


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("market", nodes.market_node)
    g.add_node("news", nodes.news_node)
    g.add_node("reasoning", nodes.reasoning_node)
    g.add_node("evaluation", nodes.evaluation_node)
    g.add_node("risk", nodes.risk_node)
    g.add_node("decision", nodes.decision_node)
    g.add_node("execution", nodes.execution_node)

    # Fan out: gather market data and news concurrently.
    g.add_edge(START, "market")
    g.add_edge(START, "news")
    # Join: reasoning runs once both have landed.
    g.add_edge("market", "reasoning")
    g.add_edge("news", "reasoning")

    g.add_edge("reasoning", "evaluation")

    # Evaluation gate: veto before risk sizing.
    g.add_conditional_edges(
        "evaluation", _gate, {"continue": "risk", "halt": END}
    )
    # Risk gate: veto before committing a decision.
    g.add_conditional_edges(
        "risk", _gate, {"continue": "decision", "halt": END}
    )

    g.add_edge("decision", "execution")
    g.add_edge("execution", END)

    return g.compile()


# Compiled once at import; cheap and stateless.
GRAPH = build_graph()
