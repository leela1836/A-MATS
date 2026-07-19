"""Walking-skeleton end-to-end tests.

Proves that one symbol flows through the whole graph and that the
evaluation gate halts a malformed proposal before it reaches risk/decision.
"""
from fastapi.testclient import TestClient

from app.main import app
from app.models.state import Direction, new_state
from app.workflows.graph import GRAPH
from app.workflows.runner import run_cycle

client = TestClient(app)


def test_happy_path_reaches_execution():
    result = run_cycle("RELIANCE.NS")
    assert result["halted"] is False
    assert result["decision"] is not None
    assert result["execution_result"]["filled"] is True
    assert result["execution_result"]["mode"] == "paper"
    assert result["execution_result"]["qty"] >= 1
    # Paper order actually moved the portfolio.
    assert result["portfolio"]["open_positions"][0]["symbol"] == "RELIANCE.NS"
    # Contract shape: every stage populated.
    for stage in ("market_analysis", "reasoned_analysis", "evaluation_scores",
                  "risk_assessment", "decision", "execution_result"):
        assert result[stage] is not None, f"{stage} missing"


def test_evaluation_gate_halts_bad_feed():
    """A non-finite price feed must be vetoed BEFORE risk sizing/decision."""
    state = new_state(["__BADFEED__"])
    final = GRAPH.invoke(state)
    assert final["halted"] is True
    assert "evaluation" in final["halt_reason"]
    assert final.get("evaluation_scores") is not None
    assert final["evaluation_scores"].passed is False
    # Gate must short-circuit: no risk assessment, no decision, no execution.
    assert final.get("risk_assessment") is None
    assert final.get("decision") is None
    assert final.get("execution_result") is None


def test_evaluation_levels_ordered_for_long():
    result = run_cycle("TCS.NS")
    r = result["reasoned_analysis"]
    assert r["direction"] == Direction.LONG.value
    assert r["stop_loss"] < r["entry_price"] < r["take_profit"]


def test_no_order_placed_when_market_is_closed(monkeypatch):
    """Outside the NSE session yfinance still returns the previous close, and
    nothing about it looks stale — so the guard must block the fill."""
    from app import market_calendar

    monkeypatch.setattr(
        market_calendar, "trading_allowed",
        lambda now=None: (False, "market closed — weekend (Sunday)"),
    )
    result = run_cycle("RELIANCE.NS")
    assert result["halted"] is False           # analysis still runs
    assert result["decision"] is not None      # a decision is still produced
    assert result["execution_result"]["filled"] is False
    assert "market closed" in result["execution_result"]["note"]
    assert result["portfolio"]["open_positions"] == []


def test_hold_signal_places_no_order():
    """A sideways/HOLD read passes evaluation but places no paper order."""
    result = run_cycle("SIDEWAYS.NS")
    assert result["halted"] is False
    assert result["evaluation_scores"]["passed"] is True
    assert result["decision"]["action"] == Direction.HOLD.value
    assert result["execution_result"]["filled"] is False
    assert result["portfolio"]["open_positions"] == []


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_run_endpoint_end_to_end():
    resp = client.post("/run/RELIANCE.NS")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "RELIANCE.NS"
    assert body["execution_result"]["filled"] is True
    assert body["trace"]["total_ms"] >= 0


def test_config_endpoint():
    resp = client.get("/config/risk")
    assert resp.status_code == 200
    assert "portfolio" in resp.json()
    assert client.get("/config/nonexistent").status_code == 404
