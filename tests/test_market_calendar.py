"""NSE session guard tests.

All datetimes are fixed and explicit — a calendar test that depends on the
wall clock passes or fails depending on when CI runs.
"""
from datetime import datetime

import pytest

from app import market_calendar as mc
from app.market_calendar import IST, market_status, trading_allowed


def _ist(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


# 2026-07-17 is a Friday, 2026-07-18 Saturday, 2026-07-19 Sunday.

def test_open_during_regular_session():
    s = market_status(_ist(2026, 7, 17, 11, 0))
    assert s.is_open is True
    assert s.session == "regular"


@pytest.mark.parametrize("hh,mm,why", [
    (9, 0, "pre-open"),     # before 09:15
    (15, 45, "after close"),  # after 15:30
    (22, 0, "after close"),
    (3, 30, "pre-open"),
])
def test_closed_outside_session_hours(hh, mm, why):
    s = market_status(_ist(2026, 7, 17, hh, mm))
    assert s.is_open is False
    assert why in s.reason


def test_boundaries_are_inclusive():
    assert market_status(_ist(2026, 7, 17, 9, 15)).is_open is True
    assert market_status(_ist(2026, 7, 17, 15, 30)).is_open is True
    assert market_status(_ist(2026, 7, 17, 9, 14)).is_open is False
    assert market_status(_ist(2026, 7, 17, 15, 31)).is_open is False


@pytest.mark.parametrize("day", [18, 19])
def test_closed_on_weekend_even_during_session_hours(day):
    """The bug this guards: 11am Sunday looks like a normal session time."""
    s = market_status(_ist(2026, 7, day, 11, 0))
    assert s.is_open is False
    assert "weekend" in s.reason


def test_closed_on_configured_holiday():
    s = market_status(_ist(2026, 1, 26, 11, 0))  # Republic Day
    assert s.is_open is False
    assert "holiday" in s.reason


def test_unknown_date_is_treated_as_open():
    """A holiday missing from config must surface as a trade, not vanish."""
    s = market_status(_ist(2026, 3, 10, 11, 0))  # ordinary weekday
    assert s.is_open is True


def test_next_open_skips_the_weekend():
    s = market_status(_ist(2026, 7, 17, 16, 0))  # Friday after close
    assert s.next_open_ist is not None
    assert s.next_open_ist.startswith("2026-07-20")  # Monday, not Saturday


def test_orders_blocked_when_market_closed():
    allowed, why = trading_allowed(_ist(2026, 7, 19, 22, 0))  # Sunday night
    assert allowed is False
    assert "closed" in why


def test_orders_allowed_during_session():
    allowed, _ = trading_allowed(_ist(2026, 7, 17, 11, 0))
    assert allowed is True


def test_trading_hours_only_false_permits_off_session(monkeypatch):
    """Escape hatch for testing against the latest close."""
    real = mc.get_config

    def cfg(name):
        if name == "trading":
            d = dict(real("trading"))
            d["scheduling"] = {**d.get("scheduling", {}), "trading_hours_only": False}
            return d
        return real(name)

    monkeypatch.setattr(mc, "get_config", cfg)
    allowed, why = trading_allowed(_ist(2026, 7, 19, 22, 0))
    assert allowed is True
    assert "trading_hours_only=false" in why


def test_malformed_holiday_entry_is_ignored(monkeypatch):
    real = mc.get_config

    def cfg(name):
        if name == "trading":
            d = dict(real("trading"))
            d["scheduling"] = {**d.get("scheduling", {}),
                               "holiday_dates": ["not-a-date", "2026-01-26"]}
            return d
        return real(name)

    monkeypatch.setattr(mc, "get_config", cfg)
    assert mc.holiday_dates() == {__import__("datetime").date(2026, 1, 26)}
