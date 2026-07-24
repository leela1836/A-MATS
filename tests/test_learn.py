"""Learning-loop tests — offline. Seeds a journal with 'lived' trades and
retrains the validator on them without any bootstrap/network."""
import json

import numpy as np
import pytest

from app.journal.store import Journal
from app.ml.features import FEATURE_NAMES
from app.ml.learn import dataset_from_journal, learn


@pytest.fixture
def journal(tmp_path):
    return Journal(path=tmp_path / "j.db")


def _seed(journal, n=60, seed=0):
    """n closed directional trades whose outcome depends on feature 0, so a
    model has something real to learn."""
    rng = np.random.default_rng(seed)
    for i in range(n):
        vec = rng.standard_normal(len(FEATURE_NAMES))
        win = vec[0] > 0
        did = journal.record_decision("s", f"S{i}.NS", {
            "direction": "long", "entry_price": 100.0, "stop_loss": 95.0,
            "take_profit": 110.0, "features": json.dumps([float(v) for v in vec]),
        })
        journal.close_decision(did, 110.0 if win else 95.0,
                               "win" if win else "loss", 10.0 if win else -5.0)


def test_features_round_trip(journal):
    did = journal.record_decision("s", "X.NS", {
        "direction": "long", "entry_price": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
        "features": json.dumps([0.1] * len(FEATURE_NAMES)),
    })
    journal.close_decision(did, 110.0, "win", 10.0)
    rows = journal.training_rows()
    assert len(rows) == 1
    assert json.loads(rows[0]["features"]) == [0.1] * len(FEATURE_NAMES)
    assert rows[0]["outcome"] == "win"


def test_hold_and_open_are_not_learnable(journal):
    journal.record_decision("s", "H.NS", {"direction": "hold",
                            "features": json.dumps([0.0] * len(FEATURE_NAMES))})
    journal.record_decision("s", "O.NS", {"direction": "long", "entry_price": 100.0,
                            "stop_loss": 95.0, "take_profit": 110.0,
                            "features": json.dumps([0.0] * len(FEATURE_NAMES))})  # stays open
    assert journal.training_rows() == []  # neither is a closed directional trade


def test_dataset_from_journal_shape(journal):
    _seed(journal, n=30)
    ds = dataset_from_journal(journal)
    assert len(ds) == 30
    assert ds.X.shape == (30, len(FEATURE_NAMES))
    assert set(np.unique(ds.y)).issubset({0.0, 1.0})


def test_learn_from_experience_only(journal, tmp_path):
    _seed(journal, n=80)
    out = learn(bootstrap=False, save=True, model_path=tmp_path / "m.json", journal=journal)
    assert out["trained"] is True
    assert out["experience_samples"] == 80
    assert out["bootstrap_samples"] == 0
    assert 0.0 <= out["oos_auc"] <= 1.0
    assert (tmp_path / "m.json").exists()


def test_learn_refuses_when_too_little(journal, tmp_path):
    _seed(journal, n=5)
    out = learn(bootstrap=False, save=False, journal=journal)
    assert out["trained"] is False
