"""Journal + autonomous scan tests — fully offline (conftest fakes providers)."""
import pytest

from app.journal.scan import _resolve_open, scan_watchlist
from app.journal.store import Journal


@pytest.fixture
def journal(tmp_path):
    return Journal(path=tmp_path / "j.db")


def test_records_and_reads_a_decision(journal):
    jid = journal.record_decision("scan-1", "TCS.NS", {
        "direction": "long", "signal": "long", "confidence": 0.6,
        "entry_price": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
        "risk_reward": 2.0, "nn_score": 0.4, "support": 96.0, "resistance": 108.0,
        "trend": "up", "thesis": "t", "source": "fallback",
    })
    assert jid > 0
    rows = journal.recent_decisions()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "TCS.NS"
    assert rows[0]["status"] == "open"           # directional call stays open
    assert rows[0]["direction"] == "long"


def test_hold_is_not_left_open(journal):
    journal.record_decision("scan-1", "ITC.NS", {"direction": "hold", "thesis": "sideways"})
    assert journal.open_decisions() == []
    assert journal.recent_decisions()[0]["status"] == "closed"


def test_resolve_closes_on_target_and_stop(journal):
    journal.record_decision("s", "A.NS", {
        "direction": "long", "entry_price": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
    })
    journal.record_decision("s", "B.NS", {
        "direction": "long", "entry_price": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
    })
    # A hits target, B hits stop.
    closed = _resolve_open(journal, {"A.NS": 111.0, "B.NS": 94.0})
    assert closed == 2
    by_sym = {d["symbol"]: d for d in journal.recent_decisions()}
    assert by_sym["A.NS"]["outcome"] == "win" and by_sym["A.NS"]["pnl_pct"] > 0
    assert by_sym["B.NS"]["outcome"] == "loss" and by_sym["B.NS"]["pnl_pct"] < 0
    assert journal.open_decisions() == []


def test_resolve_leaves_untriggered_open(journal):
    journal.record_decision("s", "C.NS", {
        "direction": "long", "entry_price": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
    })
    assert _resolve_open(journal, {"C.NS": 102.0}) == 0
    assert len(journal.open_decisions()) == 1


def test_short_resolves_correctly(journal):
    journal.record_decision("s", "D.NS", {
        "direction": "short", "entry_price": 100.0, "stop_loss": 105.0, "take_profit": 90.0,
    })
    assert _resolve_open(journal, {"D.NS": 89.0}) == 1  # price fell to target
    assert journal.recent_decisions()[0]["outcome"] == "win"


def test_equity_curve_and_stats(journal):
    journal.record_equity("s1", {"equity": 100000, "cash": 100000, "positions_value": 0,
                                 "open_positions": [], "return_percent": 0.0})
    journal.record_equity("s2", {"equity": 101000, "cash": 50000, "positions_value": 51000,
                                 "open_positions": [{"symbol": "X"}], "return_percent": 1.0})
    curve = journal.equity_curve()
    assert len(curve) == 2 and curve[0]["equity"] == 100000  # oldest first
    assert journal.stats()["scans"] == 0  # equity rows don't create decisions


def test_full_scan_writes_track_record(journal):
    """End-to-end: a deterministic scan over the fake watchlist journals
    decisions + an equity snapshot, spending no LLM quota."""
    summary = scan_watchlist(symbols=["RELIANCE.NS", "TCS.NS"], use_llm=False, journal=journal)
    assert summary["scanned"] == 2
    assert summary["used_llm"] is False
    assert summary["equity"] is not None
    assert len(journal.recent_decisions()) == 2
    assert len(journal.equity_curve()) == 1
    assert summary["stats"]["scans"] == 1
