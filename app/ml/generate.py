"""Mass-generate labeled training trades by backtesting the whole universe over
years of history — turning a handful of live paper trades into thousands of
labeled examples.

This is the honest route to the data volume that *legitimises* the ambitious
stuff (deeper nets, per-strategy weighting, RL): those techniques don't learn on
68 trades, they memorise noise — but on thousands of backtested trades they have
something real to fit. The cache is regenerated periodically (weekly on the cloud)
and blended into the learner as the bootstrap.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from app.journal.screener import load_universe
from app.ml.dataset import Dataset, build_dataset
from app.ml.features import FEATURE_NAMES

CACHE = Path(__file__).resolve().parent.parent.parent / "data" / "bootstrap.npz"


def generate(symbols: Optional[list[str]] = None, period: str = "5y",
             save: bool = True) -> Dataset:
    """Backtest `symbols` (default: the full universe) and emit a labeled Dataset.

    Backtests each symbol independently so a delisted/unfetchable name is skipped,
    not fatal — a universe-wide sweep must survive the odd bad ticker.
    """
    symbols = symbols or load_universe()
    Xs, ys, dates, syms, rets = [], [], [], [], []
    for sym in symbols:
        try:
            ds = build_dataset([sym], period=period)
        except Exception:
            continue  # delisted / no instrument / bad feed — skip
        if len(ds):
            Xs.append(ds.X)
            ys.append(ds.y)
            rets.append(ds.returns)
            dates.extend(ds.dates)
            syms.extend(ds.symbols)

    if not Xs:
        return Dataset(np.empty((0, len(FEATURE_NAMES))), np.empty(0),
                       [], [], np.empty(0), list(FEATURE_NAMES))
    ds = Dataset(np.vstack(Xs), np.concatenate(ys), dates, syms,
                 np.concatenate(rets), list(FEATURE_NAMES))
    if save and len(ds):
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            CACHE, X=ds.X, y=ds.y, returns=ds.returns,
            dates=np.array(ds.dates, dtype=object), symbols=np.array(ds.symbols, dtype=object),
        )
    return ds


def load_cached() -> Optional[Dataset]:
    """The cached mass-generated dataset, or None if it hasn't been built yet."""
    if not CACHE.exists():
        return None
    try:
        d = np.load(CACHE, allow_pickle=True)
        return Dataset(
            X=d["X"], y=d["y"], dates=list(d["dates"]), symbols=list(d["symbols"]),
            returns=d["returns"], feature_names=list(FEATURE_NAMES),
        )
    except Exception:
        return None


if __name__ == "__main__":
    ds = generate()
    print(f"generated {len(ds)} labeled trades from the universe -> {CACHE}")
    if len(ds):
        print(f"win rate {float(ds.y.mean()):.1%} · {ds.X.shape[1]} features")
