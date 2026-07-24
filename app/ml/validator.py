"""Runtime side of the learned validator: load a trained model and gate trades.

`apply_nn_filter` is the mirror of `apply_pattern_filter` — same shape, same
opt-in discipline (default OFF), and BOTH the live provider and the backtester
call it so the two can never silently diverge. If no model file is present or
the feature contract has drifted, the gate fails OPEN (returns the signal
unchanged) rather than silently blocking every trade.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from app.models.state import Direction

DEFAULT_MODEL_PATH = Path(__file__).parent / "models" / "trade_validator.json"


class TradeValidator:
    def __init__(self, bundle: dict):
        self.mlp = bundle["mlp"]
        self.scaler = bundle["scaler"]
        self.feature_names = bundle["feature_names"]
        self.threshold = float(bundle["threshold"])
        self.meta = bundle.get("meta", {})

    def predict_proba(self, window: pd.DataFrame, direction) -> float:
        """P(this specific entry ends profitable)."""
        from app.ml.features import FEATURE_NAMES, extract

        # Contract guard: refuse to score if the live feature order no longer
        # matches what the model was trained on. Silent misalignment would feed
        # RSI into the ATR weight and look like a working model.
        if self.feature_names != FEATURE_NAMES:
            raise ValueError("feature contract drift: retrain the validator")
        x = extract(window, direction).reshape(1, -1)
        return float(self.mlp.predict_proba(self.scaler.transform(x))[0])

    def should_take(self, window: pd.DataFrame, direction) -> bool:
        return self.predict_proba(window, direction) >= self.threshold


@lru_cache(maxsize=4)
def load_validator(path: Optional[str] = None) -> Optional[TradeValidator]:
    """Cached load. Returns None when no model has been trained yet."""
    from app.ml.mlp import load_model

    p = Path(path) if path else DEFAULT_MODEL_PATH
    if not p.exists():
        return None
    return TradeValidator(load_model(p))


def apply_nn_filter(
    signal: Direction,
    window: pd.DataFrame,
    params: Optional[dict] = None,
) -> Direction:
    """Veto a signal the learned model scores below its threshold.

    Only acts when `require_nn_confirmation` is set. Never flips or creates a
    direction — it can only turn a trade into HOLD, exactly like the
    candlestick gate.
    """
    p = params or {}
    if not p.get("require_nn_confirmation") or signal == Direction.HOLD:
        return signal

    validator = load_validator(p.get("nn_model_path"))
    if validator is None:  # no trained model → fail open, don't block everything
        return signal
    try:
        return signal if validator.should_take(window, signal) else Direction.HOLD
    except Exception:
        return signal  # a scoring error must not silently kill the strategy
