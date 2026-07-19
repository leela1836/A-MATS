"""NSE trading-session calendar (IST).

Answers "can we trade right now?" so the agent never places an order against
a stale close — e.g. at 22:00 on a Sunday, where yfinance still happily
returns Friday's bar and nothing about the data looks wrong.

Holiday handling is deliberately explicit: `holiday_dates` in
configs/trading.yaml holds real YYYY-MM-DD dates. Fixed-date holidays are
seeded, but most NSE holidays track lunar festivals whose dates move every
year and cannot be derived — those must be copied from the official NSE
circular annually. Unknown dates are treated as OPEN, so a missing entry
shows up as an unexpected trade rather than silent, invisible skipping.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from app.config import get_config

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class MarketStatus:
    is_open: bool
    reason: str
    now_ist: str
    session: str  # "regular" | "closed"
    next_open_ist: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "is_open": self.is_open,
            "reason": self.reason,
            "now_ist": self.now_ist,
            "session": self.session,
            "next_open_ist": self.next_open_ist,
        }


def _hours() -> tuple[time, time]:
    cfg = get_config("market").get("market_hours", {}).get("regular", {})
    return (
        _parse(str(cfg.get("open", "09:15"))),
        _parse(str(cfg.get("close", "15:30"))),
    )


def _parse(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def holiday_dates() -> set[date]:
    raw = get_config("trading").get("scheduling", {}).get("holiday_dates", []) or []
    out: set[date] = set()
    for item in raw:
        try:
            out.add(date.fromisoformat(str(item).strip()))
        except ValueError:
            continue  # malformed entries are ignored, not fatal
    return out


def is_holiday(d: date) -> bool:
    return d in holiday_dates()


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # 5 = Saturday, 6 = Sunday


def market_status(now: Optional[datetime] = None) -> MarketStatus:
    """Evaluate the NSE session at `now` (defaults to current IST time)."""
    now = now.astimezone(IST) if now else datetime.now(IST)
    stamp = now.strftime("%Y-%m-%d %H:%M %Z")
    today = now.date()
    open_t, close_t = _hours()

    if is_weekend(today):
        return MarketStatus(False, f"weekend ({now:%A})", stamp, "closed",
                            _next_open(now))
    if is_holiday(today):
        return MarketStatus(False, "NSE holiday", stamp, "closed", _next_open(now))

    current = now.time()
    if current < open_t:
        return MarketStatus(
            False, f"pre-open (opens {open_t:%H:%M} IST)", stamp, "closed",
            _next_open(now),
        )
    if current > close_t:
        return MarketStatus(
            False, f"after close ({close_t:%H:%M} IST)", stamp, "closed",
            _next_open(now),
        )
    return MarketStatus(True, "regular session", stamp, "regular")


def _next_open(now: datetime) -> str:
    """Next session start, skipping weekends and known holidays."""
    open_t, _ = _hours()
    candidate = now.date()
    # If today's session hasn't started yet, today may still qualify.
    if now.time() >= open_t:
        candidate += timedelta(days=1)
    for _ in range(14):  # bounded scan
        if not is_weekend(candidate) and not is_holiday(candidate):
            return f"{candidate.isoformat()} {open_t:%H:%M} IST"
        candidate += timedelta(days=1)
    return "unknown"


def trading_allowed(now: Optional[datetime] = None) -> tuple[bool, str]:
    """Whether orders may be placed, honouring the scheduling config.

    With `trading_hours_only: false` the caller may trade any time (useful
    for testing against the most recent close).
    """
    sched = get_config("trading").get("scheduling", {})
    status = market_status(now)
    if status.is_open:
        return True, "market open"
    if not sched.get("trading_hours_only", True):
        return True, f"market closed ({status.reason}) but trading_hours_only=false"
    return False, f"market closed — {status.reason}"
