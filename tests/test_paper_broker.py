"""Unit tests for the in-app paper-trading engine.

Uses a temp portfolio file so tests never touch the real data/portfolio.json.
"""
import pytest

from app.execution.paper_broker import PaperBroker, _apply_fill


@pytest.fixture
def broker(tmp_path):
    return PaperBroker(path=tmp_path / "pf.json")


def test_starting_state(broker):
    snap = broker.snapshot()
    assert snap["currency"] == "INR"
    assert snap["cash"] == snap["starting_cash"] == snap["equity"]
    assert snap["total_pnl"] == 0.0
    assert snap["open_positions"] == []


def test_buy_debits_cash_and_opens_position(broker):
    start = broker.snapshot()["cash"]
    trade = broker.place_order("RELIANCE.NS", "buy", 10, 1400.0)
    snap = broker.snapshot({"RELIANCE.NS": 1400.0})
    # Cash down by notional + commission.
    assert snap["cash"] == pytest.approx(start - 10 * 1400.0 - trade.commission)
    assert snap["open_positions"][0]["qty"] == 10
    assert snap["open_positions"][0]["avg_price"] == 1400.0
    # Marked at cost => unrealized 0; total_pnl == -commission (cost drag).
    assert snap["unrealized_pnl"] == 0.0
    assert snap["total_pnl"] == pytest.approx(-trade.commission)


def test_unrealized_pnl_tracks_mark(broker):
    broker.place_order("TCS.NS", "buy", 5, 3000.0)
    snap = broker.snapshot({"TCS.NS": 3200.0})
    assert snap["unrealized_pnl"] == pytest.approx(5 * (3200.0 - 3000.0))


def test_realized_pnl_on_close(broker):
    broker.place_order("INFY.NS", "buy", 10, 1500.0)
    broker.place_order("INFY.NS", "sell", 10, 1600.0)  # close for +100/share
    snap = broker.snapshot()
    assert snap["open_positions"] == []
    assert snap["realized_pnl"] == pytest.approx(10 * 100.0)


def test_average_price_on_scale_in(broker):
    broker.place_order("SBIN.NS", "buy", 10, 800.0)
    broker.place_order("SBIN.NS", "buy", 10, 900.0)
    pos = broker.snapshot()["open_positions"][0]
    assert pos["qty"] == 20
    assert pos["avg_price"] == pytest.approx(850.0)


def test_size_to_qty_uses_equity(broker):
    # 2% of ~1,000,000 equity at price 1000 => ~20 shares.
    qty = broker.size_to_qty(2.0, 1000.0, {})
    assert qty == 20


def test_persistence_round_trip(tmp_path):
    path = tmp_path / "pf.json"
    b1 = PaperBroker(path=path)
    b1.place_order("LT.NS", "buy", 3, 3500.0)
    # New broker instance loads the same file.
    b2 = PaperBroker(path=path)
    snap = b2.snapshot({"LT.NS": 3500.0})
    assert snap["open_positions"][0]["symbol"] == "LT.NS"
    assert snap["open_positions"][0]["qty"] == 3


def test_reset_restores_starting_cash(broker):
    broker.place_order("ITC.NS", "buy", 100, 450.0)
    broker.reset()
    snap = broker.snapshot()
    assert snap["cash"] == snap["starting_cash"]
    assert snap["open_positions"] == []


def test_apply_fill_flip_through_zero():
    # Long 10 @100, then sell 15 @120: close 10 (+200), open short 5 @120.
    qty, avg, realized = _apply_fill(10, 100.0, -15, 120.0)
    assert qty == -5
    assert avg == 120.0
    assert realized == pytest.approx(10 * (120.0 - 100.0))
