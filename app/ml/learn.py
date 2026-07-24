"""The learning loop: retrain the validator on the agent's OWN closed trades.

The NN first learns from backtest trades (a bootstrap). As the paper book
accumulates closed trades, this folds that lived EXPERIENCE into the training
set and retrains — so the gate that vetoes weak setups keeps sharpening on the
trades the agent actually meets. Early on it is mostly bootstrap; as experience
grows it takes over.

Honest scope: learning improves selectivity and survival. It does not conjure
an edge an efficient market won't give — see docs/HANDOFF.md.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from app.journal.store import Journal, get_journal
from app.ml.dataset import Dataset, build_dataset
from app.ml.features import FEATURE_NAMES
from app.ml.mlp import save_model
from app.ml.train import HIDDEN_LAYERS, PERIOD, SYMBOLS, _fit_and_eval
from app.ml.validator import DEFAULT_MODEL_PATH, load_validator

# Below this many lived trades, blend in the backtest bootstrap for a stable fit.
BLEND_UNTIL = 150
MIN_TO_TRAIN = 40


def dataset_from_journal(journal: Journal) -> Dataset:
    rows = journal.training_rows()
    X, y, dates, rets = [], [], [], []
    for r in rows:
        try:
            vec = json.loads(r["features"])
        except Exception:
            continue
        if len(vec) != len(FEATURE_NAMES):
            continue
        X.append([float(v) for v in vec])
        y.append(1.0 if r["outcome"] == "win" else 0.0)
        dates.append(r["ts"])
        rets.append(float(r.get("pnl_pct") or 0.0))
    if not X:
        return Dataset(np.empty((0, len(FEATURE_NAMES))), np.empty(0), [], [],
                       np.empty(0), list(FEATURE_NAMES))
    return Dataset(np.array(X, float), np.array(y, float), dates,
                   ["paper"] * len(X), np.array(rets, float), list(FEATURE_NAMES))


def _concat(a: Dataset, b: Dataset) -> Dataset:
    if len(a) == 0:
        return b
    if len(b) == 0:
        return a
    return Dataset(
        np.vstack([a.X, b.X]), np.concatenate([a.y, b.y]),
        list(a.dates) + list(b.dates), list(a.symbols) + list(b.symbols),
        np.concatenate([a.returns, b.returns]), a.feature_names,
    )


def learn(bootstrap: bool = True, save: bool = True,
          model_path: Path = DEFAULT_MODEL_PATH,
          journal: Journal | None = None) -> dict[str, Any]:
    """Retrain the validator on journal experience (+ bootstrap). Returns a
    summary; saves over the live model so the next scan uses the sharper gate."""
    journal = journal or get_journal()
    exp = dataset_from_journal(journal)

    parts, boot_n = exp, 0
    if bootstrap and len(exp) < BLEND_UNTIL:
        boot = build_dataset(SYMBOLS, period=PERIOD)  # cached fetches -> fast
        boot_n = len(boot)
        parts = _concat(exp, boot)

    if len(parts) < MIN_TO_TRAIN:
        return {"trained": False, "reason": "not enough data yet",
                "experience_samples": len(exp), "total": len(parts)}

    res = _fit_and_eval(parts, HIDDEN_LAYERS)
    ev = res["mlp_eval"]
    summary = {
        "trained": True, "saved": save,
        "experience_samples": len(exp), "bootstrap_samples": boot_n,
        "total": len(parts), "oos_auc": round(ev.auc, 4),
        "experience_win_rate": round(float(exp.y.mean()), 3) if len(exp) else None,
    }
    if save:
        save_model(model_path, res["mlp"], res["scaler"], parts.feature_names, res["thr"],
                   meta={"trained_on": "journal+bootstrap" if boot_n else "journal",
                         **{k: summary[k] for k in ("experience_samples", "bootstrap_samples",
                                                    "total", "oos_auc")}})
        load_validator.cache_clear()  # next scan reloads the sharper model
    return summary


if __name__ == "__main__":
    print(json.dumps(learn(), indent=2))
