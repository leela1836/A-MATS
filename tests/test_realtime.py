from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pandas as pd
import pytest

from app.collectors import fyers_collector as feed
from app.execution import realtime as rt

NOW = datetime(2026, 9, 28, 5, 0, tzinfo=timezone.utc)


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setattr(rt, "market_status", lambda now: SimpleNamespace(is_open=True))
    monkeypatch.setattr(rt, "ACCOUNT", tmp_path / "account.json")
    monkeypatch.setattr(rt, "is_tradable", lambda name: name == "mean_reversion")
    obj = rt.RealtimeEngine(tmp_path / "account.json")
    obj.signals["TCS.NS"] = {"day": "2026-09-28", "long": True,
                             "confidence": .8, "stop": 960, "target": 1080,
                             "strategy": "mean_reversion", "close": 1000}
    return obj


def tick(price=1000, now=NOW, symbol="TCS.NS"):
    return feed.Tick(symbol, price, now.timestamp())


def test_entry_stop_gap_and_restart(engine):
    first = engine.on_tick(tick(), NOW)
    assert first.side == "buy" and first.qty > 0
    assert engine.state["protection"]["TCS.NS"]["stop"] < first.price
    engine.on_tick(tick(), NOW)
    assert engine.broker.snapshot()["trade_count"] == 1
    restarted = rt.RealtimeEngine(engine.broker._path)
    later = NOW + timedelta(minutes=2)
    closed = restarted.on_tick(tick(900, later), later)
    assert closed.side == "sell" and closed.price < 900  # gap, not idealized stop
    assert restarted.broker.snapshot()["open_positions"] == []
    assert restarted.state["protection"] == {}
    restarted.signals = engine.signals
    restarted.on_tick(tick(1000, later + timedelta(minutes=2)), later + timedelta(minutes=2))
    assert restarted.broker.snapshot()["trade_count"] == 2


@pytest.mark.parametrize("price,age", [(0, 0), (-1, 0), (float("nan"), 0),
                                    (float("inf"), 0), (1000, 31), (1000, -1)])
def test_bad_ticks_never_fill(engine, price, age):
    engine.on_tick(feed.Tick("TCS.NS", price, NOW.timestamp() - age), NOW)
    assert engine.broker.snapshot()["trade_count"] == 0


def test_closed_session_ignores_legacy_override(engine, monkeypatch):
    monkeypatch.setattr(rt, "market_status", lambda now: SimpleNamespace(is_open=False))
    engine.on_tick(tick(), NOW)
    assert engine.broker.snapshot()["trade_count"] == 0


def test_loss_halt_persists_and_allows_exit(engine):
    engine.on_tick(tick(), NOW)
    later = NOW + timedelta(seconds=1)
    closed = engine.on_tick(tick(100, later), later)
    assert closed.side == "sell"
    assert engine.state["halt"] == "daily loss limit"
    restarted = rt.RealtimeEngine(engine.broker._path)
    assert restarted.state["halt"] == "daily loss limit"


def test_missing_other_mark_blocks_entry_not_exit(engine):
    engine.on_tick(tick(), NOW)
    engine.signals["INFY.NS"] = dict(engine.signals["TCS.NS"])
    later = NOW + timedelta(minutes=2)
    engine.on_tick(tick(1000, later, "INFY.NS"), later)
    assert engine.broker.snapshot()["trade_count"] == 1
    engine.disconnect()
    assert engine.status(NOW)["fresh_symbols"] == []
    assert engine.on_tick(tick(1100, later), later).side == "sell"


def test_kill_file_blocks_only_entries(engine):
    engine.on_tick(tick(), NOW)
    (rt.ACCOUNT.parent / "paper.stop").touch()
    later = NOW + timedelta(minutes=2)
    assert engine.on_tick(tick(1100, later), later).side == "sell"
    engine.signals["INFY.NS"] = dict(engine.signals["TCS.NS"])
    engine.on_tick(tick(1000, later, "INFY.NS"), later)
    assert engine.broker.snapshot()["trade_count"] == 2


def test_rejected_fill_rolls_back_runtime(engine, monkeypatch):
    def reject(*a, **kw):
        raise ValueError("reserve breached")
    monkeypatch.setattr(engine.broker, "place_order", reject)
    engine.on_tick(tick(), NOW)
    assert engine.state["protection"] == {}
    assert engine.state["entered"] == {}
    assert engine.state["orders"] == 0


def test_tick_parse_requires_exchange_timestamp():
    mapping = {"NSE:TCS-EQ": "TCS.NS"}
    msg = {"type": "sf", "symbol": "NSE:TCS-EQ", "ltp": 1000}
    assert feed.parse_tick(msg, mapping) is None
    msg["last_traded_time"] = NOW.timestamp()
    assert feed.parse_tick(msg, mapping) == tick()
    assert feed.parse_tick({**msg, "symbol": "UNKNOWN"}, mapping) is None


def test_symbol_and_credential_validation():
    assert feed.fyers_symbol("M&M.NS") == "NSE:M&M-EQ"
    with pytest.raises(ValueError):
        feed.fyers_symbol("TCS.BO")
    with pytest.raises(ValueError, match="FYERS_APP_ID"):
        feed.credentials()


def test_history_chunking_validation(monkeypatch):
    monkeypatch.setenv("FYERS_APP_ID", "fake")
    monkeypatch.setenv("FYERS_ACCESS_TOKEN", "fake")
    requests = []

    def handle(request):
        requests.append(request)
        start = request.url.params["range_from"]
        end = request.url.params["range_to"]
        dates = pd.date_range(start, end, freq="B", tz="Asia/Kolkata")
        rows = [[int(d.timestamp()), 100, 110, 90, 101, 10000] for d in dates]
        return httpx.Response(200, json={"s": "ok", "candles": rows})

    client = httpx.Client(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(feed.httpx, "Client", lambda **kw: client)
    df = feed.fetch_completed_history("TCS.NS", NOW)
    assert len(requests) == 2 and len(df) > 210
    assert df.index[-1].date() < NOW.date()


@pytest.mark.parametrize("qty,price", [(float("nan"), 100), (float("inf"), 100), (1, 0), (1, -1)])
def test_broker_rejects_invalid_numbers(isolated_broker, qty, price):
    with pytest.raises(ValueError):
        isolated_broker.place_order("TEST.NS", "buy", qty, price)
    assert isolated_broker.snapshot()["trade_count"] == 0


def test_account_lock_prevents_two_writers(tmp_path):
    with rt.account_lock(tmp_path / "account.json"):
        with pytest.raises(OSError):
            with rt.account_lock(tmp_path / "account.json"):
                pytest.fail("second runner acquired lock")


def test_prepare_uses_eligible_library_strategy(engine, monkeypatch):
    from app.strategies.library.base import StratSignal
    import numpy as np
    close = np.linspace(900, 1000, 250)
    df = pd.DataFrame({"Open": close, "High": close + 5, "Low": close - 5,
                       "Close": close, "Volume": 1_000_000})
    eligible = SimpleNamespace(name="mean_reversion", evaluate=lambda ctx:
                              StratSignal("mean_reversion", "long", .8, 1000, 960, 1080, "test"))
    def forbidden(ctx):
        pytest.fail("benched strategy evaluated")
    benched = SimpleNamespace(name="trend_following", evaluate=forbidden)
    monkeypatch.setattr(rt, "STRATEGIES", [benched, eligible])
    engine.prepare("TCS.NS", df, NOW)
    assert engine.signals["TCS.NS"]["strategy"] == "mean_reversion"
    assert engine.on_tick(tick(), NOW).side == "buy"


def test_benched_signal_cannot_enter(engine, monkeypatch):
    monkeypatch.setattr(rt, "is_tradable", lambda name: False)
    assert engine.on_tick(tick(), NOW) is None
    assert engine.broker.snapshot()["trade_count"] == 0


def test_websocket_adapter_only_subscribes(monkeypatch):
    data_ws = pytest.importorskip("fyers_apiv3.FyersWebsocket.data_ws")
    monkeypatch.setenv("FYERS_APP_ID", "fake")
    monkeypatch.setenv("FYERS_ACCESS_TOKEN", "fake")
    seen, closed = [], []

    class Socket:
        def __init__(self, **kwargs):
            self.kw = kwargs
        def connect(self):
            self.kw["on_connect"]()
        def subscribe(self, **kwargs):
            assert kwargs == {"symbols": ["NSE:TCS-EQ"], "data_type": "SymbolUpdate"}
    monkeypatch.setattr(data_ws, "FyersDataSocket", Socket)
    socket = feed.connect(["TCS.NS"], seen.append, lambda: closed.append(True))
    socket.kw["on_message"]({"type": "sf", "symbol": "NSE:TCS-EQ", "ltp": 1000,
                               "last_traded_time": NOW.timestamp()})
    assert seen == [tick()] and closed == [True]
    socket.kw["on_error"]("error")
    assert closed == [True, True]


def test_status_endpoint_marks_old_heartbeat_stopped(tmp_path, monkeypatch):
    import json
    from app.main import realtime_status
    path = tmp_path / "status.json"
    monkeypatch.setattr(rt, "STATUS", path)
    assert realtime_status()["running"] is False
    path.write_text(json.dumps({"heartbeat": "2020-01-01T00:00:00+00:00"}))
    assert realtime_status()["running"] is False
