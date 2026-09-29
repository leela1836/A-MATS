"""Bounded paper sessions for GitHub Actions, using the persistent real-time account.

No broker orders. Positions are only monitored while this process is running.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from datetime import datetime, timezone

from app.config import get_config
from app.execution.realtime import ACCOUNT, STATUS, RealtimeEngine, account_lock
from app.market_calendar import market_status


def initialize_account(path=ACCOUNT):
    """Fund a new virtual account once; never reset an existing account."""
    with account_lock(path):
        engine = RealtimeEngine(path)
        if not path.exists():
            now = datetime.now(timezone.utc)
            engine.state['funded_at'] = now.isoformat()
            engine._record_mark(now, {})  # Cash-only funding needs no market price.
            engine._save()


def run(seconds=60):
    if not ACCOUNT.exists():
        raise RuntimeError('Persistent paper account missing; refusing to silently reset it')
    with account_lock(ACCOUNT):
        engine = RealtimeEngine(ACCOUNT)
        now = datetime.now(timezone.utc)
        stream = None
        failures = []
        received = set()
        preparation_errors = []
        started = now.isoformat()
        try:
            session = market_status(now)
            if not session.is_open:
                engine.last_event = session.reason + '; no orders attempted'
                if not engine.broker._pf.positions:
                    engine._record_mark(now, {})
                    engine._save()
                return
            if get_config('trading').get('realtime', {}).get('provider', 'upstox') != 'upstox':
                raise ValueError('Cloud sessions require the configured Upstox provider')
            from app.collectors import upstox_stream as provider
            provider.credentials()
            symbols = sorted(set(get_config('market')['symbols']['equities']) |
                             set(engine.broker._pf.positions))
            for symbol in symbols:
                try:
                    engine.prepare(symbol, provider.fetch_completed_history(symbol, now), now)
                except Exception as exc:
                    preparation_errors.append({'symbol': symbol, 'error': type(exc).__name__})
            stopped = threading.Event()

            def receive(tick):
                if stopped.is_set():
                    return
                try:
                    if tick.fresh(datetime.now(timezone.utc)):
                        received.add(tick.symbol)
                    engine.on_tick(tick)
                except Exception as exc:
                    failures.append(type(exc).__name__)
                    stopped.set()

            stream = provider.connect(symbols, receive, engine.disconnect)
            deadline = time.monotonic() + seconds
            while not stopped.is_set() and time.monotonic() < deadline:
                stopped.wait(min(1, max(0, deadline - time.monotonic())))
            stopped.set()
            if failures:
                raise RuntimeError('Paper tick processing failed: ' + failures[0])
            if not received:
                raise RuntimeError('No fresh market ticks received; account was not repriced')
            mark = engine.state.get('last_mark_ts')
            if not mark or datetime.fromisoformat(mark) < now:
                raise RuntimeError('No complete fresh account mark; one or more holdings remain unpriced')
            engine.last_event = 'Scheduled paper session completed; monitoring paused between runs'
        except Exception as exc:
            engine.last_event = 'Paper session failed: ' + type(exc).__name__
            failures.append(type(exc).__name__)
            raise
        finally:
            if stream:
                stream.auto_reconnect(False)
                stream.disconnect()
            report = engine.status()
            report.update(event=engine.last_event if not stream else
                          ('Paper session failed' if failures else 'Scheduled session complete'),
                          execution_mode='scheduled', running=False, started_at=started,
                          fresh_symbols_received=sorted(received), preparation_errors=preparation_errors,
                          errors=failures,
                          note='Positions are monitored only during workflow runs; schedules may be delayed.')
            temporary = STATUS.with_suffix('.json.tmp')
            temporary.write_text(json.dumps(report, allow_nan=False), encoding='utf-8')
            temporary.replace(STATUS)
            print(json.dumps(report, allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initialize', action='store_true', help='Fund a new virtual account once')
    parser.add_argument('--seconds', type=int, default=60)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 300:
        parser.error('--seconds must be between 1 and 300')
    if args.initialize:
        initialize_account()
    else:
        run(args.seconds)


if __name__ == '__main__':
    main()
