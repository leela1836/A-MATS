"""Train and HONESTLY evaluate the trade validator.

The evaluation is the point, not the training. Any model can fit a few hundred
trades; the question is whether it generalises to trades it has never seen,
placed later in time. So:

  • the split is TEMPORAL (train on the older trades, test on the newer ones);
  • the threshold is chosen on TRAIN only, never peeked from the test set;
  • the MLP is reported next to a logistic-regression baseline AND the majority-
    class win rate, so we can see whether the network earns its complexity or
    just launders the base rate.

Run:  ./.venv/Scripts/python.exe -m app.ml.train
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.ml.dataset import Dataset, build_dataset, temporal_split
from app.ml.mlp import MLP, StandardScaler, roc_auc, save_model

SYMBOLS = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", "SBIN.NS"]
PERIOD = "5y"
MODEL_PATH = Path(__file__).parent / "models" / "trade_validator.json"

COVERAGE_FLOOR = 0.30  # a gate that takes <30% of trades is too sparse to trust


@dataclass
class Eval:
    auc: float
    base_win_rate: float
    threshold: float
    coverage: float          # fraction of test trades the gate lets through
    taken_win_rate: float
    mean_ret_all: float      # mean return_pct over ALL test trades
    mean_ret_taken: float    # mean return_pct over trades the gate keeps


def _pick_threshold(scores: np.ndarray, rets: np.ndarray) -> float:
    """Threshold that maximises mean realised return on TRAIN, keeping enough
    coverage. Fit on train only — the test set never informs it."""
    best_thr, best_obj = 0.5, -np.inf
    for thr in np.quantile(scores, np.linspace(0.0, 0.9, 19)):
        keep = scores >= thr
        if keep.mean() < COVERAGE_FLOOR:
            continue
        obj = rets[keep].mean()
        if obj > best_obj:
            best_obj, best_thr = obj, float(thr)
    return best_thr


def _evaluate(scores: np.ndarray, ds: Dataset, thr: float) -> Eval:
    keep = scores >= thr
    taken = ds.y[keep]
    return Eval(
        auc=roc_auc(ds.y, scores),
        base_win_rate=float(ds.y.mean()),
        threshold=thr,
        coverage=float(keep.mean()),
        taken_win_rate=float(taken.mean()) if len(taken) else float("nan"),
        mean_ret_all=float(ds.returns.mean()),
        mean_ret_taken=float(ds.returns[keep].mean()) if keep.any() else float("nan"),
    )


def train() -> dict:
    print(f"Building dataset from {SYMBOLS} over {PERIOD} ...")
    ds = build_dataset(SYMBOLS, period=PERIOD)
    print(f"  {len(ds)} trades, base win rate {ds.y.mean():.1%}")
    if len(ds) < 60:
        raise SystemExit("too few trades to train a validator honestly")

    train_ds, test_ds = temporal_split(ds, train_frac=0.7)
    # Inner temporal split of TRAIN for early stopping.
    fit_ds, val_ds = temporal_split(train_ds, train_frac=0.8)
    print(f"  fit={len(fit_ds)}  val={len(val_ds)}  test={len(test_ds)} (temporal)")

    scaler = StandardScaler().fit(fit_ds.X)
    Xf, Xv, Xt = (scaler.transform(d.X) for d in (fit_ds, val_ds, test_ds))
    Xtrain = scaler.transform(train_ds.X)
    n_feat = ds.X.shape[1]

    mlp = MLP([n_feat, 16, 1], l2=3e-3, lr=0.01, seed=7)
    mlp.fit(Xf, fit_ds.y, epochs=800, X_val=Xv, y_val=val_ds.y, patience=60)

    logistic = MLP([n_feat, 1], l2=3e-3, lr=0.05, seed=7)
    logistic.fit(Xf, fit_ds.y, epochs=800, X_val=Xv, y_val=val_ds.y, patience=60)

    thr = _pick_threshold(mlp.predict_proba(Xtrain), train_ds.returns)

    mlp_eval = _evaluate(mlp.predict_proba(Xt), test_ds, thr)
    log_eval = _evaluate(logistic.predict_proba(Xt), test_ds, thr)

    print("\n=== OUT-OF-SAMPLE (test = newest 30% of trades) ===")
    print(f"  base win rate (take everything) : {mlp_eval.base_win_rate:.1%}")
    print(f"  logistic baseline AUC           : {log_eval.auc:.3f}")
    print(f"  MLP AUC                         : {mlp_eval.auc:.3f}")
    print(f"  threshold (chosen on train)     : {thr:.3f}")
    print(f"  MLP gate coverage               : {mlp_eval.coverage:.1%} of test trades")
    print(f"  win rate  — all vs gated        : {mlp_eval.base_win_rate:.1%}"
          f" -> {mlp_eval.taken_win_rate:.1%}")
    print(f"  mean ret% — all vs gated        : {mlp_eval.mean_ret_all:+.3f}"
          f" -> {mlp_eval.mean_ret_taken:+.3f}")

    verdict = (
        "MLP beats coin-flip and the logistic baseline out of sample"
        if mlp_eval.auc > 0.55 and mlp_eval.auc >= log_eval.auc
        else "NO out-of-sample edge — the gate is not trustworthy yet"
    )
    print(f"\n  VERDICT: {verdict}")

    save_model(
        MODEL_PATH, mlp, scaler, ds.feature_names, thr,
        meta={
            "symbols": SYMBOLS, "period": PERIOD, "trades": len(ds),
            "oos_auc": round(mlp_eval.auc, 4),
            "oos_base_win_rate": round(mlp_eval.base_win_rate, 4),
            "oos_gated_win_rate": round(mlp_eval.taken_win_rate, 4),
            "oos_coverage": round(mlp_eval.coverage, 4),
            "logistic_auc": round(log_eval.auc, 4),
        },
    )
    print(f"\n  saved -> {MODEL_PATH}")
    return {"mlp": mlp_eval, "logistic": log_eval}


if __name__ == "__main__":
    train()
