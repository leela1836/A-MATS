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

from app.journal.store import Journal, get_journal, ROUND_TRIP_COST_PCT
from app.ml.dataset import Dataset, build_dataset
from app.ml.features import FEATURE_NAMES
from app.ml.mlp import save_model
from app.ml.train import HIDDEN_LAYERS, PERIOD, SYMBOLS, _fit_and_eval
from app.ml.validator import DEFAULT_MODEL_PATH, load_validator

# Below this many lived trades, blend in the backtest bootstrap for a stable fit.
BLEND_UNTIL = 150
# Minimum samples (lived + bootstrap) to attempt a fit. Kept low so the loop
# actually retrains early — the bootstrap blend keeps an early fit stable while
# the agent's own closed trades are still few.
MIN_TO_TRAIN = 20


def dataset_from_journal(journal: Journal) -> Dataset:
    rows = journal.training_rows()
    X, y, dates, rets, ends = [], [], [], [], []
    for r in rows:
        try:
            vec = json.loads(r["features"])
        except Exception:
            continue
        if len(vec) != len(FEATURE_NAMES):
            continue
        try:
            if not r.get("exit_ts") or not np.isfinite(np.asarray(vec, dtype=float)).all():
                continue
        except (TypeError, ValueError):
            continue
        X.append([float(v) for v in vec])
        net = float(r.get("pnl_pct") or 0.0) - ROUND_TRIP_COST_PCT
        y.append(float(net > 0))
        dates.append(r["ts"])
        ends.append(r["exit_ts"])
        rets.append(net)
    if not X:
        return Dataset(np.empty((0, len(FEATURE_NAMES))), np.empty(0), [], [],
                       np.empty(0), list(FEATURE_NAMES))
    return Dataset(np.array(X, float), np.array(y, float), dates,
                   ["research_idea"] * len(X), np.array(rets, float), list(FEATURE_NAMES), ends)


def _concat(a: Dataset, b: Dataset) -> Dataset:
    if len(a) == 0:
        return b
    if len(b) == 0:
        return a
    return Dataset(
        np.vstack([a.X, b.X]), np.concatenate([a.y, b.y]),
        list(a.dates) + list(b.dates), list(a.symbols) + list(b.symbols),
        np.concatenate([a.returns, b.returns]), a.feature_names,
        (a.end_dates + b.end_dates) if a.end_dates is not None and b.end_dates is not None else None,
    )


def learn(bootstrap: bool = True, save: bool = True,
          model_path: Path = DEFAULT_MODEL_PATH,
          journal: Journal | None = None) -> dict[str, Any]:
    """Retrain the validator on journal experience (+ bootstrap). Returns a
    summary; saves a candidate, leaving the active model unchanged."""
    journal = journal or get_journal()
    exp = dataset_from_journal(journal)

    parts, boot_n = exp, 0
    if bootstrap and len(exp) < BLEND_UNTIL:
        # Prefer the mass-generated universe-wide cache (thousands of trades);
        # fall back to backtesting a few symbols live if it hasn't been built yet.
        from app.ml.generate import load_cached
        boot = load_cached()
        # Legacy bootstrap labels used biased fills and lack label end dates.
        # Regenerate explicitly; never blend them or trigger paid/network work.
        if boot is not None and boot.end_dates is not None:
            boot_n = len(boot)
            parts = _concat(exp, boot)

    if len(parts) < MIN_TO_TRAIN:
        skipped = {"trained": False, "reason": "not enough data yet",
                   "experience_samples": len(exp), "total": len(parts)}
        journal.record_learning(skipped)  # remember that it tried and why it held off
        return skipped

    try:
        res = _fit_and_eval(parts, HIDDEN_LAYERS)
    except ValueError as exc:
        skipped = {"trained": False, "saved": False, "reason": str(exc),
                   "experience_samples": len(exp), "total": len(parts)}
        journal.record_learning(skipped)
        return skipped
    ev = res["mlp_eval"]
    summary = {
        "trained": True, "saved": False, "candidate_saved": save,
        "experience_samples": len(exp), "bootstrap_samples": boot_n,
        "total": len(parts), "oos_auc": round(ev.auc, 4),
        "experience_win_rate": round(float(exp.y.mean()), 3) if len(exp) else None,
        "promotion_eligible": False,
        "statistical_screen_passed": bool(res["splits"][2] >= 50 and ev.auc >= 0.55
                                   and ev.coverage >= 0.30 and ev.mean_ret_taken > 0
                                   and ev.mean_ret_taken > ev.mean_ret_all
                                   and ev.auc >= res["log_eval"].auc),
        "promotion_reason": "research labels; prospective fill-based validation required",
        "reason": "candidate retrained; active model unchanged; prospective validation required",
    }
    if save:
        candidate_path = model_path.with_name(model_path.stem + ".candidate.json")
        save_model(candidate_path, res["mlp"], res["scaler"], parts.feature_names, res["thr"],
                   meta={"trained_on": "research_ideas", "active": False,
                         "promotion_eligible": summary["promotion_eligible"],
                         **{k: summary[k] for k in ("experience_samples", "bootstrap_samples",
                                                    "total", "oos_auc")}})
        summary["candidate_path"] = str(candidate_path)
    journal.record_learning(summary)  # log the retrain into the agent's memory
    return summary


if __name__ == "__main__":
    print(json.dumps(learn(), indent=2))
