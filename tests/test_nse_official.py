"""Official NSE collector tests — parsing, caching, and graceful degradation.

No network: `_fetch` is stubbed everywhere. The behaviour that matters most
is that NSE being unreachable never breaks a trading cycle.
"""
from datetime import date

import pytest

from app.collectors import nse_official as nse
from app.collectors.nse_official import NSEUnavailable, to_nse_symbol

HOLIDAY_PAYLOAD = {
    "CM": [
        {"tradingDate": "26-Jan-2026", "weekDay": "Monday", "description": "Republic Day"},
        {"tradingDate": "03-Mar-2026", "weekDay": "Tuesday", "description": "Holi"},
        {"tradingDate": "08-Nov-2026", "weekDay": "Sunday", "description": "Diwali"},
    ],
    "FO": [{"tradingDate": "01-Jan-2026"}],
}

ASM_PAYLOAD = {
    "longterm": {"data": [{"symbol": "ADDICTIVE"}, {"symbol": "AEROFLEX"}]},
    "shortterm": {"data": [{"symbol": "HARDWYN"}]},
}


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(nse, "CACHE_DIR", tmp_path / "nse_cache")


def test_symbol_normalisation():
    assert to_nse_symbol("RELIANCE.NS") == "RELIANCE"
    assert to_nse_symbol("tcs.ns") == "TCS"
    assert to_nse_symbol("INFY") == "INFY"


def test_holidays_parsed_for_requested_segment(monkeypatch):
    monkeypatch.setattr(nse, "_fetch", lambda path: HOLIDAY_PAYLOAD)
    got = nse.fetch_trading_holidays("CM")
    assert date(2026, 3, 3) in got      # Holi — a movable date we can't derive
    assert date(2026, 1, 26) in got
    assert date(2026, 1, 1) not in got  # FO segment must not leak into CM


def test_holidays_are_cached_not_refetched(monkeypatch):
    calls = {"n": 0}

    def counting(path):
        calls["n"] += 1
        return HOLIDAY_PAYLOAD

    monkeypatch.setattr(nse, "_fetch", counting)
    nse.fetch_trading_holidays("CM")
    nse.fetch_trading_holidays("CM")
    assert calls["n"] == 1, "NSE rate-limits; the second call must hit cache"


def test_stale_cache_used_when_nse_unreachable(monkeypatch):
    monkeypatch.setattr(nse, "_fetch", lambda path: HOLIDAY_PAYLOAD)
    nse.fetch_trading_holidays("CM")  # populate

    def boom(path):
        raise NSEUnavailable("network down")

    monkeypatch.setattr(nse, "_fetch", boom)
    monkeypatch.setattr(nse, "TTL_HOLIDAYS", -1)  # force the cache to look stale
    got = nse.fetch_trading_holidays("CM")
    assert date(2026, 3, 3) in got, "a stale calendar beats no calendar"


def test_holidays_raise_when_no_data_at_all(monkeypatch):
    monkeypatch.setattr(nse, "_fetch", lambda path: {"CM": []})
    with pytest.raises(NSEUnavailable):
        nse.fetch_trading_holidays("CM")


def test_asm_merges_longterm_and_shortterm(monkeypatch):
    monkeypatch.setattr(nse, "_fetch", lambda path: ASM_PAYLOAD)
    got = nse.fetch_asm_symbols()
    assert got == {"ADDICTIVE", "AEROFLEX", "HARDWYN"}


def test_announcements_parsed(monkeypatch):
    monkeypatch.setattr(nse, "_fetch", lambda path: [
        {"symbol": "RELIANCE", "desc": "Board Meeting Intimation",
         "attchmntText": "RIL informed the Exchange...", "an_dt": "19-Jul-2026 21:54:15",
         "attchmntFile": "https://nsearchives.nseindia.com/x.pdf"},
        {"symbol": "", "desc": "no symbol — dropped"},
    ])
    got = nse.fetch_announcements()
    assert len(got) == 1
    assert got[0].symbol == "RELIANCE"
    assert got[0].title == "Board Meeting Intimation"


def test_market_state_extracts_capital_market(monkeypatch):
    monkeypatch.setattr(nse, "_fetch", lambda path: {"marketState": [
        {"market": "Currency", "marketStatus": "Close"},
        {"market": "Capital Market", "marketStatus": "Open", "tradeDate": "20-Jul-2026"},
    ]})
    st = nse.fetch_market_state()
    assert st["is_open"] is True
    assert st["market"] == "Capital Market"


def test_market_state_raises_when_segment_absent(monkeypatch):
    monkeypatch.setattr(nse, "_fetch", lambda path: {"marketState": []})
    with pytest.raises(NSEUnavailable):
        nse.fetch_market_state()
