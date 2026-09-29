import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.collectors import upstox_stream
from app.collectors.fyers_collector import Tick
from app.execution import cloud, realtime
from app.execution.accounting import paper_report


@pytest.fixture
def account(tmp_path, monkeypatch):
    path = tmp_path / 'account.json'
    monkeypatch.setattr(cloud, 'ACCOUNT', path)
    monkeypatch.setattr(cloud, 'STATUS', tmp_path / 'status.json')
    monkeypatch.setattr(cloud, 'market_status', lambda now: SimpleNamespace(is_open=True))
    monkeypatch.setattr(realtime, 'market_status', lambda now: SimpleNamespace(is_open=True))
    cloud.initialize_account(path)
    return path


def test_funding_is_real_persisted_cash_and_never_resets_existing_account(account):
    before = account.read_bytes()
    cloud.initialize_account(account)
    assert account.read_bytes() == before
    report = paper_report(account)
    assert report['available']
    assert report['portfolio']['equity'] == 100000
    assert report['portfolio']['return_percent'] == 0
    assert report['trades'] == []


def test_closed_session_publishes_without_feed_or_fills(account, monkeypatch):
    monkeypatch.setattr(cloud, 'market_status', lambda now: SimpleNamespace(is_open=False, reason='closed'))
    monkeypatch.setattr(upstox_stream, 'connect', lambda *args: pytest.fail('Must not connect'))
    cloud.run()
    assert paper_report(account)['trades'] == []
    status = json.loads(cloud.STATUS.read_text())
    assert status['event'] == 'closed; no orders attempted'
    assert not status['running']


def test_cloud_fills_persist_across_sessions_and_missing_ticks_report_failure(account, monkeypatch):
    monkeypatch.setattr(upstox_stream, 'credentials', lambda: 'test')
    monkeypatch.setattr(upstox_stream, 'fetch_completed_history', lambda *args: None)
    monkeypatch.setattr(realtime, 'is_tradable', lambda name: True)

    def prepare(self, symbol, df, now):
        self.signals[symbol] = {'day': now.astimezone(realtime.IST).date().isoformat(),
                               'long': True, 'strategy': 'mean_reversion',
                               'stop': 960, 'target': 1080, 'confidence': .8, 'close': 1000}
    monkeypatch.setattr(realtime.RealtimeEngine, 'prepare', prepare)
    stream = SimpleNamespace(auto_reconnect=lambda *args: None, disconnect=lambda: None)

    def connect(symbols, receive, disconnect):
        receive(Tick('TCS.NS', 1000, datetime.now(timezone.utc).timestamp()))
        return stream
    monkeypatch.setattr(upstox_stream, 'connect', connect)
    cloud.run(.001)
    first = paper_report(account)
    assert len(first['trades']) == 1
    assert first['portfolio']['equity'] < 100000  # actual fee and slippage
    cloud.run(.001)
    assert len(paper_report(account)['trades']) == 1  # no duplicate entry on restart
    before = account.read_bytes()
    monkeypatch.setattr(upstox_stream, 'connect', lambda *args: stream)
    with pytest.raises(RuntimeError, match='No fresh market ticks'):
        cloud.run(.001)
    assert account.read_bytes() == before
    assert json.loads(cloud.STATUS.read_text())['errors']


def test_missing_account_fails_instead_of_refunding(account):
    account.unlink()
    with pytest.raises(RuntimeError, match='refusing to silently reset'):
        cloud.run()
