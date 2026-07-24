"""Offline tests for the learned trade validator.

No network, no tokens: the MLP trains on synthetic arrays, the feature
extractor runs on hand-built OHLCV, and the gate is checked with no model on
disk. Fast and deterministic — the whole point of the pure-numpy choice.
"""
import numpy as np
import pandas as pd
import pytest

from app.ml.mlp import MLP, StandardScaler, roc_auc, save_model, load_model
from app.ml.features import FEATURE_NAMES, extract
from app.ml.dataset import Dataset, temporal_split
from app.ml.validator import TradeValidator, apply_nn_filter
from app.models.state import Direction


# ── the network actually learns ──

def test_mlp_learns_xor():
    """XOR is not linearly separable — solving it proves the hidden layer and
    backprop work, not just memorisation of a trivial mapping."""
    X = np.array([[0, 0], [0, 1], [1, 0], [1, 1]], dtype=float)
    y = np.array([0, 1, 1, 0], dtype=float)
    net = MLP([2, 8, 1], l2=0.0, lr=0.05, seed=1).fit(X, y, epochs=3000)
    preds = (net.predict_proba(X) > 0.5).astype(int)
    assert (preds == y).all()


def test_mlp_is_deterministic():
    X = np.random.default_rng(0).standard_normal((40, 3))
    y = (X[:, 0] > 0).astype(float)
    a = MLP([3, 4, 1], seed=42).fit(X, y, epochs=200).predict_proba(X)
    b = MLP([3, 4, 1], seed=42).fit(X, y, epochs=200).predict_proba(X)
    assert np.allclose(a, b)


def test_logistic_baseline_separates_linearly():
    rng = np.random.default_rng(3)
    X = rng.standard_normal((200, 2))
    y = (X[:, 0] + X[:, 1] > 0).astype(float)
    net = MLP([2, 1], lr=0.1, seed=0).fit(X, y, epochs=500)  # no hidden = logistic
    assert roc_auc(y, net.predict_proba(X)) > 0.95


# ── metrics ──

def test_roc_auc_edges():
    y = np.array([0, 0, 1, 1])
    assert roc_auc(y, np.array([0.1, 0.2, 0.8, 0.9])) == pytest.approx(1.0)
    assert roc_auc(y, np.array([0.9, 0.8, 0.2, 0.1])) == pytest.approx(0.0)
    assert roc_auc(y, np.array([0.5, 0.5, 0.5, 0.5])) == pytest.approx(0.5)


def test_scaler_roundtrip():
    X = np.array([[1.0, 100.0], [3.0, 300.0], [5.0, 500.0]])
    s = StandardScaler().fit(X)
    Z = s.transform(X)
    assert np.allclose(Z.mean(axis=0), 0.0, atol=1e-9)
    assert np.allclose(Z.std(axis=0), 1.0, atol=1e-6)


def test_scaler_handles_constant_column():
    X = np.array([[1.0, 5.0], [2.0, 5.0], [3.0, 5.0]])  # col 1 constant
    Z = StandardScaler().fit(X).transform(X)
    assert np.isfinite(Z).all()  # must not divide by zero


# ── feature extraction ──

def _ohlcv(n: int, base: float = 100.0, vol: float = 1e6) -> pd.DataFrame:
    rng = np.random.default_rng(5)
    close = base + np.cumsum(rng.standard_normal(n))
    high = close + np.abs(rng.standard_normal(n))
    low = close - np.abs(rng.standard_normal(n))
    open_ = close + rng.standard_normal(n) * 0.5
    volume = np.abs(rng.standard_normal(n)) * vol + vol
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": volume})


def test_extract_shape_and_finiteness():
    v = extract(_ohlcv(120), Direction.LONG)
    assert v.shape == (len(FEATURE_NAMES),)
    assert np.isfinite(v).all()


def test_extract_is_deterministic():
    df = _ohlcv(120)
    assert np.array_equal(extract(df, Direction.LONG), extract(df, Direction.LONG))


def test_dir_long_flag_tracks_direction():
    df = _ohlcv(120)
    i = FEATURE_NAMES.index("dir_long")
    assert extract(df, Direction.LONG)[i] == 1.0
    assert extract(df, Direction.SHORT)[i] == 0.0


def test_features_are_scale_invariant():
    """A Rs 100 stock and a Rs 24,000 index with the same shape (prices and
    volume scaled together) must produce near-identical unit-free features."""
    small = _ohlcv(120, base=100.0, vol=1e6)
    big = small.copy()
    big[["Open", "High", "Low", "Close"]] *= 240.0  # ratios must be unchanged
    a = extract(small, Direction.LONG)
    b = extract(big, Direction.LONG)
    # Price-relative and candlestick features are unit-free; volume is untouched.
    assert np.allclose(a, b, atol=1e-6)


def test_missing_volume_degrades_to_zero():
    df = _ohlcv(120).drop(columns=["Volume"])
    v = extract(df, Direction.LONG)
    for name in ("vol_surge", "turnover_spike", "vol_trend_ratio", "up_down_vol_pressure"):
        assert v[FEATURE_NAMES.index(name)] == 0.0


# ── save / load ──

def test_model_roundtrip(tmp_path):
    X = np.random.default_rng(2).standard_normal((50, len(FEATURE_NAMES)))
    y = (X[:, 1] > 0).astype(float)
    scaler = StandardScaler().fit(X)
    mlp = MLP([len(FEATURE_NAMES), 4, 1], seed=9).fit(scaler.transform(X), y, epochs=100)
    path = tmp_path / "m.json"
    save_model(path, mlp, scaler, list(FEATURE_NAMES), 0.5, {"note": "test"})

    bundle = load_model(path)
    reloaded = bundle["mlp"].predict_proba(bundle["scaler"].transform(X))
    original = mlp.predict_proba(scaler.transform(X))
    assert np.allclose(reloaded, original)
    assert bundle["feature_names"] == list(FEATURE_NAMES)


def test_validator_predicts_probability(tmp_path):
    X = np.random.default_rng(4).standard_normal((60, len(FEATURE_NAMES)))
    y = (X[:, 0] > 0).astype(float)
    scaler = StandardScaler().fit(X)
    mlp = MLP([len(FEATURE_NAMES), 4, 1], seed=1).fit(scaler.transform(X), y, epochs=100)
    path = tmp_path / "v.json"
    save_model(path, mlp, scaler, list(FEATURE_NAMES), 0.5, {})
    v = TradeValidator(load_model(path))
    p = v.predict_proba(_ohlcv(120), Direction.LONG)
    assert 0.0 <= p <= 1.0


# ── gate behaviour ──

def test_gate_off_is_a_passthrough():
    sig = apply_nn_filter(Direction.LONG, _ohlcv(120), {"require_nn_confirmation": False})
    assert sig == Direction.LONG


def test_gate_fails_open_without_a_model():
    """Flag on but no model trained → must NOT block every trade."""
    sig = apply_nn_filter(Direction.LONG, _ohlcv(120),
                          {"require_nn_confirmation": True,
                           "nn_model_path": "does/not/exist.json"})
    assert sig == Direction.LONG


def test_gate_never_touches_hold():
    sig = apply_nn_filter(Direction.HOLD, _ohlcv(120), {"require_nn_confirmation": True})
    assert sig == Direction.HOLD


# ── dataset ──

def test_temporal_split_is_strictly_ordered():
    n = 20
    ds = Dataset(
        X=np.zeros((n, len(FEATURE_NAMES))),
        y=np.zeros(n),
        dates=[f"2020-{m:02d}-01" for m in range(1, n + 1)] if n <= 12
               else [f"20{20 + i // 12:02d}-{i % 12 + 1:02d}-01" for i in range(n)],
        symbols=["X"] * n,
        returns=np.zeros(n),
        feature_names=list(FEATURE_NAMES),
    )
    train, test = temporal_split(ds, train_frac=0.7)
    assert len(train) + len(test) == n
    assert max(train.dates) <= min(test.dates)  # no future leaks into training
