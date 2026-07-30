"""Screener + screen-scan tests — offline (conftest injects a fake market provider)."""
import pytest

from app.journal.scan import run_screen_scan
from app.journal.screener import load_universe, screen_universe
from app.journal.store import Journal


@pytest.fixture
def journal(tmp_path):
    return Journal(path=tmp_path / "j.db")


def test_load_universe_reads_file():
    uni = load_universe()
    assert len(uni) >= 10
    assert all(s.endswith(".NS") for s in uni)
    assert "RELIANCE.NS" in uni


def test_screen_returns_ranked_candidates_and_prices():
    cands, prices = screen_universe(["RELIANCE.NS", "TCS.NS", "INFY.NS"], top_n=5)
    # Every fetched symbol contributes a price, even if it's a hold.
    assert set(prices).issubset({"RELIANCE.NS", "TCS.NS", "INFY.NS"})
    assert prices  # fake provider returns finite prices
    # Candidates are only directional setups, ranked by score descending.
    for c in cands:
        assert c.direction in ("long", "short")
        assert 0.0 <= c.score <= 1.0
    assert cands == sorted(cands, key=lambda c: -c.score)


def test_top_n_caps_the_shortlist():
    cands, _ = screen_universe(["RELIANCE.NS", "TCS.NS", "INFY.NS", "SBIN.NS"], top_n=1)
    assert len(cands) <= 1


def test_bad_ticker_is_skipped_not_fatal(monkeypatch):
    """A symbol whose provider raises must be skipped, not crash the sweep."""
    from app.collectors.market_collector import MarketDataError
    from app.models.state import Direction, MarketAnalysis
    import app.journal.screener as screener

    good = MarketAnalysis(
        symbol="GOOD.NS", last_price=100.0, trend="up", signal=Direction.LONG,
        confidence=0.6, indicators={}, nn_score=0.4, resistance=110.0,
    )

    class _FakeProvider:
        def get_analysis(self, sym):
            if sym == "BAD.NS":
                raise MarketDataError("no data for BAD.NS")
            return good

    monkeypatch.setattr(screener, "get_market_provider", lambda: _FakeProvider())
    cands, prices = screen_universe(["GOOD.NS", "BAD.NS"], top_n=5)
    assert "BAD.NS" not in prices
    assert "GOOD.NS" in prices
    assert [c.symbol for c in cands] == ["GOOD.NS"]


def test_screen_scan_does_not_reopen_already_open_symbols(journal):
    """Scanning the same names twice must NOT create duplicate open trades —
    one open decision per symbol until it resolves."""
    uni = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "SBIN.NS"]
    run_screen_scan(universe=uni, top_n=4, journal=journal)
    after_first = len(journal.open_decisions())
    s2 = run_screen_scan(universe=uni, top_n=4, journal=journal)
    after_second = len(journal.open_decisions())
    assert after_first > 0, "first scan should open some trades"
    assert after_second == after_first, "second scan must not duplicate open trades"
    assert s2["held_open"] >= after_first  # they were skipped as already-open


def test_stale_open_trade_expires_and_feeds_learning(journal):
    """A trade that neither hits stop nor target within its horizon is closed at
    market (reason 'expiry') and becomes a learning example."""
    import datetime as _dt
    from app.journal.scan import _resolve_open

    old_ts = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=30)).isoformat(timespec="seconds")
    did = journal.record_decision("scan-x", "TEST.NS", {
        "direction": "long", "entry_price": 100.0, "stop_loss": 90.0,
        "take_profit": 120.0, "est_hold_days": 10,
        "features": "[0,0,0,0,0,0,0,0,0,0,0,0,0]",
    })
    with journal._conn() as c:
        c.execute("UPDATE decisions SET ts=? WHERE id=?", (old_ts, did))

    # 105 hits neither the 90 stop nor the 120 target, but it is 30d > 10d old.
    closed = _resolve_open(journal, {"TEST.NS": 105.0})
    row = journal.recent_decisions(1)[0]
    assert closed == 1
    assert row["status"] == "closed"
    assert row["exit_reason"] == "expiry"
    assert row["outcome"] == "win"  # +5% at exit
    assert len(journal.training_rows()) == 1  # now available to learn from


def test_fresh_open_trade_does_not_expire(journal):
    """A trade opened just now stays open — expiry only fires past the horizon."""
    from app.journal.scan import _resolve_open

    journal.record_decision("scan-y", "NEW.NS", {
        "direction": "long", "entry_price": 100.0, "stop_loss": 90.0, "take_profit": 120.0,
    })
    assert _resolve_open(journal, {"NEW.NS": 105.0}) == 0
    assert len(journal.open_decisions()) == 1


def test_equity_curve_reflects_realized_journal_pnl(journal):
    """The agent equity line is built from persisted realized P&L (10%/trade),
    not the broker — so it moves with actual trade outcomes."""
    from app.journal.store import POSITION_FRACTION

    did = journal.record_decision("scan-1", "X.NS", {
        "direction": "long", "entry_price": 100.0, "stop_loss": 90.0, "take_profit": 110.0,
    })
    journal.record_equity("scan-1", {"equity": 0, "open_positions": []}, benchmark=100_000.0)
    journal.close_decision(did, 110.0, "win", 10.0, exit_reason="target")
    journal.record_equity("scan-2", {"equity": 0, "open_positions": []}, benchmark=101_000.0)
    # Pin a clean chronology: snapshot1 < trade exit < snapshot2, so the first
    # snapshot predates the win and the second reflects it.
    with journal._conn() as c:
        c.execute("UPDATE equity SET ts=? WHERE scan_id='scan-1'", ("2026-01-01T00:00:00+00:00",))
        c.execute("UPDATE decisions SET exit_ts=? WHERE id=?", ("2026-01-01T00:00:05+00:00", did))
        c.execute("UPDATE equity SET ts=? WHERE scan_id='scan-2'", ("2026-01-01T00:00:10+00:00",))

    curve = journal.equity_curve(starting_cash=100_000.0)
    assert curve[0]["equity"] == pytest.approx(100_000.0)          # before the win
    gain = 100_000.0 * POSITION_FRACTION * 0.10                     # 10% of 10% trade
    assert curve[-1]["equity"] == pytest.approx(100_000.0 + gain)  # after the win
    assert curve[-1]["return_percent"] == pytest.approx(1.0)


def test_benchmark_tracks_buy_and_hold(tmp_path):
    """The buy-and-hold basket initializes on first prices and marks to market."""
    from app.journal.benchmark import BuyHold

    b = BuyHold(path=tmp_path / "bench.json", starting_cash=100_000.0)
    assert b.mark({"A.NS": 100.0, "B.NS": 200.0}) == pytest.approx(100_000.0)  # inception
    # A doubles, B flat: equal-weight ⇒ +50%.
    assert b.mark({"A.NS": 200.0, "B.NS": 200.0}) == pytest.approx(150_000.0)
    assert b.return_percent(150_000.0) == pytest.approx(50.0)


def test_screen_scan_journals_shortlist_with_scores(journal):
    summary = run_screen_scan(
        universe=["RELIANCE.NS", "TCS.NS", "INFY.NS"], top_n=3, journal=journal,
    )
    assert summary["screened"] >= 1
    assert summary["llm_reasoned"] == 0  # deterministic scan uses no LLM
    assert len(journal.equity_curve()) == 1
    rows = journal.recent_decisions()
    if rows:  # at least the directional survivors get journaled
        assert any(r["screen_rank"] is not None for r in rows)
        assert any(r["screen_score"] is not None for r in rows)


def test_migration_adds_columns_to_old_db(tmp_path):
    """A journal created before the screen columns existed gains them on open,
    then round-trips a decision that uses them."""
    import sqlite3
    from app.journal.store import _SCHEMA

    p = tmp_path / "old.db"
    con = sqlite3.connect(p)
    # Real pre-screen schema = current schema minus the two screen columns.
    old_schema = _SCHEMA.replace("    screen_score  REAL,                   -- composite screen score (0..1)\n", "")
    old_schema = old_schema.replace("    screen_rank   INTEGER                 -- rank within the scan's shortlist\n", "")
    # Drop the trailing comma left on the previous column.
    old_schema = old_schema.replace("pnl_pct       REAL,\n);", "pnl_pct       REAL\n);")
    con.executescript(old_schema)
    con.commit(); con.close()

    cols_before = {r[1] for r in sqlite3.connect(p).execute("PRAGMA table_info(decisions)").fetchall()}
    assert "screen_score" not in cols_before

    j = Journal(path=p)  # __init__ runs the migration
    j.record_decision("s", "X.NS", {"direction": "long", "screen_score": 0.7, "screen_rank": 1})
    assert j.recent_decisions()[0]["screen_score"] == 0.7
