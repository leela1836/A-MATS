"""Bounded read-only Upstox diagnostic. Never prints credentials or socket URLs."""
import json
import threading
from datetime import datetime, timezone

from app.config import get_config
from app.collectors import upstox_stream


def main():
    result = {"provider": "upstox", "orders_sent": 0, "connected": False,
              "ticks": 0, "fresh_ticks": 0}
    done = threading.Event()
    stream = None
    try:
        upstox_stream.credentials()
        history = upstox_stream.fetch_completed_history("RELIANCE.NS")
        result.update(history_bars=len(history), last_completed_bar=str(history.index[-1]))

        def received(tick):
            result["ticks"] += 1
            result["fresh_ticks"] += int(tick.fresh(datetime.now(timezone.utc)))
            done.set()

        stream = upstox_stream.connect(["RELIANCE.NS"], received, lambda: None)
        stream.on("open", lambda: result.update(connected=True))
        done.wait(15)
    except Exception as exc:
        result["error_type"] = type(exc).__name__
    finally:
        if stream:
            stream.auto_reconnect(False)
            stream.disconnect()
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
