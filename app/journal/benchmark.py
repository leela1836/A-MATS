"""The fair yardstick: an equal-weight buy-and-hold of the tradable basket.

Research on this universe is unambiguous — timing and selection do NOT beat
simply holding (see docs/HANDOFF.md). So the honest thing is to always show the
agent's equity against this line. On the first scan that sees prices, we split
the same starting cash equally across those names and hold forever; every later
scan marks that fixed basket to the latest prices the agent already fetched — no
extra data source, perfectly comparable to the agent's own book.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
BENCH_FILE = DATA_DIR / "benchmark.json"


class BuyHold:
    def __init__(self, path: Path = BENCH_FILE, starting_cash: float = 100_000.0):
        self._path = path
        self._starting = starting_cash
        self._s = self._load()

    def _fresh(self) -> dict:
        return {"initialized": False, "starting_cash": self._starting,
                "cash": self._starting, "holdings": {}, "start_prices": {}, "start_ts": None}

    def _load(self) -> dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return self._fresh()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._s, indent=2), encoding="utf-8")

    def mark(self, prices: Optional[dict[str, float]]) -> float:
        """Value the buy-and-hold basket at the given prices. Initializes the
        basket (equal-weight across the priced names) on the first call that has
        prices, so it starts at the same moment and cash as the agent's book."""
        valid = {s: float(p) for s, p in (prices or {}).items()
                 if isinstance(p, (int, float)) and p > 0}
        if not self._s.get("initialized"):
            if not valid:
                return self._s["starting_cash"]  # nothing to buy yet
            per = self._s["starting_cash"] / len(valid)
            self._s["holdings"] = {s: per / px for s, px in valid.items()}  # fractional ok
            self._s["start_prices"] = valid
            self._s["cash"] = 0.0
            self._s["initialized"] = True
            self._s["start_ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._save()

        equity = float(self._s.get("cash", 0.0))
        for sym, shares in self._s.get("holdings", {}).items():
            px = valid.get(sym) or self._s.get("start_prices", {}).get(sym)
            if px:
                equity += shares * px
        return round(equity, 2)

    def return_percent(self, equity: Optional[float] = None) -> Optional[float]:
        if not self._s.get("initialized"):
            return None
        eq = equity if equity is not None else self.mark({})
        base = self._s.get("starting_cash") or self._starting
        return round((eq / base - 1) * 100, 3)

    def reset(self) -> None:
        self._s = self._fresh()
        self._save()
