"""The mass-generation bootstrap cache: save/load roundtrip + graceful absence."""
import numpy as np

from app.ml import generate
from app.ml.dataset import Dataset
from app.ml.features import FEATURE_NAMES


def test_load_cached_is_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(generate, "CACHE", tmp_path / "missing.npz")
    assert generate.load_cached() is None


def test_bootstrap_cache_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setattr(generate, "CACHE", tmp_path / "boot.npz")
    ds = Dataset(
        X=np.zeros((3, len(FEATURE_NAMES))), y=np.array([1.0, 0.0, 1.0]),
        dates=["2024-01-01", "2024-01-02", "2024-01-03"],
        symbols=["A.NS", "B.NS", "A.NS"], returns=np.array([1.0, -1.0, 2.0]),
        feature_names=list(FEATURE_NAMES),
    )
    np.savez(
        generate.CACHE, X=ds.X, y=ds.y, returns=ds.returns,
        dates=np.array(ds.dates, dtype=object), symbols=np.array(ds.symbols, dtype=object),
    )
    got = generate.load_cached()
    assert got is not None
    assert len(got) == 3
    assert got.X.shape[1] == len(FEATURE_NAMES)
    assert list(got.symbols) == ["A.NS", "B.NS", "A.NS"]
    assert got.feature_names == list(FEATURE_NAMES)
