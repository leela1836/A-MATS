from datetime import datetime, timedelta, timezone
import json

import numpy as np
import pandas as pd
import pytest

from tests.test_realtime import engine, NOW, tick
from app.backtester import engine as backtester
from app.collectors import upstox_stream
from app.execution.accounting import paper_report
from app.execution.realtime import RealtimeEngine
from app.ml.dataset import Dataset, temporal_split
from app.models.state import Direction


def fixture_bars(monkeypatch, flip=False):
    n = backtester.WARMUP_BARS + 6
    df = pd.DataFrame({"Open": 100., "High": 101., "Low": 99., "Close": 100.,
                       "Volume": 1e6}, index=pd.date_range("2024-01-01", periods=n, freq="B"))
    monkeypatch.setattr(backtester, "compute_indicators", lambda window:
                        {"last_price": 100, "atr_14": 2, "length": len(window)})
    def classify(ind, *_):
        i = ind["length"] - 1
        direction = Direction.LONG if i == backtester.WARMUP_BARS else Direction.HOLD
        if flip and i == backtester.WARMUP_BARS + 1:
            direction = Direction.SHORT
        return "up", direction, .8
    monkeypatch.setattr(backtester, "classify", classify)
    return df


def test_entry_bar_stop_is_not_skipped(monkeypatch):
    df = fixture_bars(monkeypatch)
    df.iloc[211, df.columns.get_loc("Low")] = 90
    report = backtester.run_backtest("A.NS", df=df)
    assert len(report.trades) == 1
    trade = report.trades[0]
    assert trade.entry_date == trade.exit_date and trade.exit_reason == "stop"
    assert trade.pnl < 0


def test_flip_uses_next_open_not_observed_close(monkeypatch):
    df = fixture_bars(monkeypatch, flip=True)
    df.iloc[212, df.columns.get_loc("Open")] = 90
    df.iloc[212, df.columns.get_loc("Low")] = 89
    report = backtester.run_backtest("A.NS", df=df)
    trade = report.trades[0]
    assert trade.exit_date == str(df.index[212].date())
    assert trade.exit_reason == "signal_flip" and trade.exit_price < 90


@pytest.mark.parametrize("direction,opening,expected", [(Direction.LONG, 80, 80),
                                                       (Direction.SHORT, 120, 120)])
def test_stop_gaps_use_open(direction, opening, expected):
    pos = backtester.OpenPosition(direction, 100, "2024-01-01", 0, 1,
                                  95 if direction == Direction.LONG else 105,
                                  110 if direction == Direction.LONG else 90)
    assert backtester._check_exit(pos, {"Open": opening, "High": opening+1, "Low": opening-1}) == (expected, "stop")


def test_monthly_halt_survives_restart_and_preserves_history(engine, monkeypatch):
    from app.config import get_config
    monkeypatch.setitem(get_config("trading")["portfolio"]["loss_management"], "max_monthly_loss_percent", .1)
    engine.on_tick(tick(), NOW)
    later = NOW + timedelta(minutes=2)
    engine.on_tick(tick(980, later), later)
    assert engine.state["halt"] == "monthly loss limit"
    assert engine.broker.snapshot()["open_positions"] == []
    restored = RealtimeEngine(engine.broker._path)
    assert restored.state["halt"] == "monthly loss limit"
    report = paper_report(engine.broker._path)
    assert report["monthly"][0]["pnl"] < 0
    assert report["portfolio"]["total_pnl"] == pytest.approx(report["monthly"][0]["pnl"])


def test_month_rollover_uses_previous_mark_and_keeps_latch(engine):
    engine.on_tick(tick(), NOW)
    previous = engine.state["last_equity"]
    next_month = datetime(2026, 10, 1, 5, tzinfo=timezone.utc)
    engine.on_tick(tick(990, next_month), next_month)
    assert engine.state["months"]["2026-10"]["opening_equity"] == previous
    assert engine.state["months"]["2026-10"]["equity"] < previous


def test_accounting_reconciles_fees_and_unrealized(engine):
    engine.on_tick(tick(), NOW)
    report = paper_report(engine.broker._path)
    portfolio = report["portfolio"]
    assert portfolio["cash"] + portfolio["positions_value"] == pytest.approx(portfolio["equity"])
    assert portfolio["total_pnl"] == pytest.approx(portfolio["realized_pnl"] + portfolio["unrealized_pnl"])
    assert report["accounting_basis"] == "paper_fills"


def test_accounting_detects_unmarked_fill(engine):
    engine.on_tick(tick(), NOW)
    raw = json.loads(engine.broker._path.read_text())
    raw["runtime"]["last_mark_seq"] -= 1
    engine.broker._path.write_text(json.dumps(raw))
    assert not paper_report(engine.broker._path)["available"]


def test_no_account_does_not_invent_flat_returns(tmp_path):
    report = paper_report(tmp_path / "missing.json")
    assert report["portfolio"]["equity"] is None
    assert report["monthly"] == []


def test_temporal_split_purges_overlapping_outcomes():
    ds = Dataset(np.zeros((5, 1)), np.zeros(5),
                 [f"2024-01-0{i}" for i in range(1, 6)], ["A"]*5,
                 np.zeros(5), ["x"],
                 ["2024-01-02", "2024-01-05", "2024-01-04", "2024-01-05", "2024-01-06"])
    train, test = temporal_split(ds, .6)
    assert train.dates == ["2024-01-01"]
    assert test.dates == ["2024-01-04", "2024-01-05"]
    ds.dates = ["2024-01-01"] * 5
    with pytest.raises(ValueError):
        temporal_split(ds)


def test_journal_small_gross_gain_is_net_losing_label(tmp_path):
    from app.journal.store import Journal
    from app.ml.features import FEATURE_NAMES
    from app.ml.learn import dataset_from_journal
    journal = Journal(tmp_path / "j.db")
    key = journal.record_decision("x", "A", {"direction": "long", "features": json.dumps([0]*len(FEATURE_NAMES))})
    journal.close_decision(key, 100.1, "win", .1)
    ds = dataset_from_journal(journal)
    assert ds.y[0] == 0 and ds.returns[0] == pytest.approx(-.1)


def test_upstox_timestamp_not_receipt_time():
    raw = {"feeds": {"key": {"ltpc": {"ltp": 1000, "ltt": str(int(NOW.timestamp()*1000))}}}}
    assert upstox_stream.parse_ticks(raw, {"key": "TCS.NS"}) == [tick()]
    del raw["feeds"]["key"]["ltpc"]["ltt"]
    assert upstox_stream.parse_ticks(raw, {"key": "TCS.NS"}) == []


def test_legacy_execution_can_be_disabled(monkeypatch):
    from app.config import get_config
    from app.workflows.runner import run_cycle
    monkeypatch.setitem(get_config("trading"), "legacy_execution_enabled", False)
    result = run_cycle("RELIANCE.NS")
    assert not result["execution_result"]["filled"]
    assert "research only" in result["execution_result"]["note"]


def test_portfolio_replay_respects_shared_cash_and_position_cap(monkeypatch):
    from app.backtester.portfolio import replay
    def prepare(self, symbol, df, now):
        self.signals[symbol] = {"day": now.date().isoformat(), "long": True,
                                "strategy": "test", "confidence": .9,
                                "stop": 90., "target": 120., "close": 100.}
    monkeypatch.setattr(RealtimeEngine, "prepare", prepare)
    dates = pd.date_range("2024-01-01", periods=218, freq="B")
    frame = pd.DataFrame({"Open": 100., "High": 101., "Low": 99., "Close": 100.,
                          "Volume": 1e6}, index=dates)
    report = replay({f"S{i}.NS": frame for i in range(8)}, strategies={"test"})
    assert 0 < len(report["open_positions"]) <= 5
    assert report["portfolio"]["cash"] >= 10000
    assert report["portfolio"]["positions_value"] <= report["portfolio"]["equity"]
    assert report["portfolio"]["equity"] < 100000  # fees and slippage, never free fills
