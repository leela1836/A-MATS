"""Dump the journal + trained model to docs/*.json for the GitHub Pages site.

Run after each scan (the workflow does this). The static pages in docs/ fetch
these and re-render, so the dashboard updates itself as new scans land.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.journal.store import get_journal
from app.ml.validator import DEFAULT_MODEL_PATH

DOCS = Path(__file__).resolve().parent.parent.parent / "docs"


def _track_record() -> dict:
    j = get_journal()
    decisions = j.recent_decisions(60)
    for d in decisions:
        # trim thesis for payload weight; keep enough to read on a phone
        if d.get("thesis"):
            d["thesis"] = d["thesis"][:240]
    from app.status.summary import agent_summary
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stats": j.stats(),
        "equity": j.equity_curve(500),
        "decisions": decisions,
        "summary": agent_summary(j),
    }


def _nn_model() -> dict:
    try:
        from app.ml.mlp import load_model
        b = load_model(DEFAULT_MODEL_PATH)
    except Exception:
        return {"available": False}
    return {
        "available": True,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "feature_names": b["feature_names"],
        "layer_sizes": b["mlp"].layer_sizes,
        "threshold": b["threshold"],
        "meta": b.get("meta", {}),
        "W": [w.tolist() for w in b["mlp"].W],
        "bias": [bb.tolist() for bb in b["mlp"].b],
        "scaler_mean": b["scaler"].mean.tolist(),
        "scaler_std": b["scaler"].std.tolist(),
    }


def build() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "data.json").write_text(json.dumps(_track_record()), encoding="utf-8")
    (DOCS / "nn.json").write_text(json.dumps(_nn_model()), encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    print(f"wrote {DOCS/'data.json'} and {DOCS/'nn.json'}")


if __name__ == "__main__":
    build()
