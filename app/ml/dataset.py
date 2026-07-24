"""Turn backtest trades into a labelled training set.

Each row is one entry the BASELINE rule strategy actually took, described by
the features visible at the decision bar, and labelled by whether that trade
made money. This is the reflection-engine idea in its cheapest form: the paper
book has no closed trades, but a 5-year backtest yields hundreds of known
outcomes today.

Labels are the UNFILTERED strategy's trades on purpose — the validator's job
is to learn which of those baseline entries to skip, so it must see the ones
the baseline would take, winners and losers alike.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.backtester.engine import run_backtest
from app.collectors.market_collector import fetch_history
from app.ml.features import FEATURE_NAMES, extract


@dataclass
class Dataset:
    X: np.ndarray            # (n, n_features)
    y: np.ndarray            # (n,) 1 = winning trade, 0 = losing
    dates: list[str]         # entry date per row (for TEMPORAL splitting)
    symbols: list[str]
    returns: np.ndarray      # (n,) realised return_pct, for return-weighted checks
    feature_names: list[str]

    def __len__(self) -> int:
        return len(self.y)


def build_dataset(
    symbols: list[str],
    period: str = "5y",
    params: Optional[dict] = None,
) -> Dataset:
    """Replay each symbol once; emit (features, outcome) for every trade.

    The SAME dataframe is handed to run_backtest and to the feature
    reconstruction, so `entry_index` indexes identical bars in both — no risk
    of a fetch drifting between the two.
    """
    rows_X, rows_y, dates, syms, rets = [], [], [], [], []
    for sym in symbols:
        df = fetch_history(sym, period=period, interval="1d")
        res = run_backtest(sym, df=df, signal_overrides=params)
        for t in res.trades:
            e = t.entry_index
            if e < 50:  # need enough history for indicators to be meaningful
                continue
            window = df.iloc[:e]  # decision bar is e-1; inclusive slice = :e
            feats = extract(window, t.direction, params)
            rows_X.append(feats)
            rows_y.append(1 if t.pnl > 0 else 0)
            dates.append(t.entry_date)
            syms.append(sym)
            rets.append(t.return_pct)

    if not rows_X:
        return Dataset(np.empty((0, len(FEATURE_NAMES))), np.empty(0),
                       [], [], np.empty(0), list(FEATURE_NAMES))
    return Dataset(
        X=np.vstack(rows_X),
        y=np.array(rows_y, dtype=float),
        dates=dates,
        symbols=syms,
        returns=np.array(rets, dtype=float),
        feature_names=list(FEATURE_NAMES),
    )


def temporal_split(ds: Dataset, train_frac: float = 0.7) -> tuple[Dataset, Dataset]:
    """Split by DATE, not at random.

    A random split lets the model peek at the same market regime it is tested
    on and reports a fantasy score. Sorting by entry date and cutting once puts
    every test trade strictly after every training trade — the only split that
    answers 'would this have worked going forward'.
    """
    order = np.argsort(np.array(ds.dates))
    cut = int(len(order) * train_frac)
    tr_idx, te_idx = order[:cut], order[cut:]

    def _take(idx: np.ndarray) -> Dataset:
        return Dataset(
            X=ds.X[idx], y=ds.y[idx],
            dates=[ds.dates[i] for i in idx],
            symbols=[ds.symbols[i] for i in idx],
            returns=ds.returns[idx],
            feature_names=ds.feature_names,
        )
    return _take(tr_idx), _take(te_idx)
