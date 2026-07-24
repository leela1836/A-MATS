"""FastAPI service for the Neural-Network Health Dashboard (port 8100).

Read-only window onto the trained trade-validator MLP (`app/ml/mlp.py`,
`app/ml/features.py`, `app/ml/validator.py`). Deliberately its own process on
its own port: it must never touch `app/main.py`, the LangGraph workflows, or
the Next.js frontend, and it makes zero LLM calls — the only network call it
can ever make is `yfinance` history for symbol-mode predictions, and even that
is optional (manual/slider mode runs fully offline on the loaded model).

Same origin serves both the JSON API and the HTML page, so no CORS needed.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.ml.mlp import MLP, load_model

MODEL_PATH = Path(__file__).resolve().parents[1] / "ml" / "models" / "trade_validator.json"
DASHBOARD_HTML_PATH = Path(__file__).parent / "dashboard.html"

app = FastAPI(title="NN Health Dashboard", version="0.1.0")


# ── model loading ──

@lru_cache(maxsize=1)
def get_bundle() -> Optional[dict]:
    """Cached load of the trained model bundle. None if not yet trained."""
    if not MODEL_PATH.exists():
        return None
    return load_model(MODEL_PATH)


def forward_with_hidden(mlp: MLP, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Replicate MLP._forward but also hand back the hidden (ReLU) layer.

    Mirrors mlp.py exactly: ReLU on every layer but the last, sigmoid on the
    final linear output. Kept separate from MLP._forward (which only returns
    the full cache) so the dashboard doesn't reach into a private method.
    """
    a = np.asarray(X, dtype=float)
    hidden = a
    last = len(mlp.W) - 1
    for i, (W, b) in enumerate(zip(mlp.W, mlp.b)):
        z = a @ W + b
        a = z if i == last else np.maximum(z, 0.0)
        if i == last - 1:
            hidden = a  # activations of the last hidden layer, post-ReLU
    p = 1.0 / (1.0 + np.exp(-np.clip(a, -30, 30)))
    return p, hidden


# ── API models ──

class PredictRequest(BaseModel):
    mode: str  # "symbol" | "manual"
    direction: str = "long"
    symbol: Optional[str] = None
    period: str = "1y"
    features: Optional[dict[str, float]] = None


# ── endpoints ──

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "nn-dashboard", "model_loaded": get_bundle() is not None}


@app.get("/api/model")
def api_model() -> dict:
    """Model metadata: feature contract, architecture, gate threshold, OOS stats."""
    bundle = get_bundle()
    if bundle is None:
        return {"available": False}
    return {
        "available": True,
        "feature_names": bundle["feature_names"],
        "layer_sizes": bundle["mlp"].layer_sizes,
        "threshold": bundle["threshold"],
        **bundle["meta"],
    }


@app.get("/api/weights")
def api_weights() -> dict:
    """Raw weight matrices and biases so the frontend can draw the network graph."""
    bundle = get_bundle()
    if bundle is None:
        return {"available": False}
    mlp = bundle["mlp"]
    return {
        "available": True,
        "layer_sizes": mlp.layer_sizes,
        "feature_names": bundle["feature_names"],
        "W": [w.tolist() for w in mlp.W],
        "b": [b.tolist() for b in mlp.b],
    }


@app.post("/api/predict")
def api_predict(req: PredictRequest) -> dict:
    """Score one candidate entry, in either 'symbol' (live) or 'manual' (offline) mode."""
    bundle = get_bundle()
    if bundle is None:
        raise HTTPException(status_code=503, detail="no trained model at app/ml/models/trade_validator.json")

    mlp, scaler = bundle["mlp"], bundle["scaler"]
    feature_names, threshold = bundle["feature_names"], float(bundle["threshold"])

    direction = (req.direction or "long").strip().lower()
    if direction not in ("long", "short"):
        raise HTTPException(status_code=400, detail="direction must be 'long' or 'short'")

    if req.mode == "symbol":
        if not req.symbol:
            raise HTTPException(status_code=400, detail="symbol required for mode='symbol'")
        from app.collectors.market_collector import MarketDataError, fetch_history
        from app.ml.features import extract

        try:
            df = fetch_history(req.symbol.strip().upper(), period=req.period)
        except MarketDataError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        try:
            x = extract(df, direction)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"feature extraction failed: {exc}") from exc

    elif req.mode == "manual":
        if not req.features:
            raise HTTPException(status_code=400, detail="features required for mode='manual'")
        x = np.array([float(req.features.get(name, 0.0)) for name in feature_names], dtype=float)

    else:
        raise HTTPException(status_code=400, detail="mode must be 'symbol' or 'manual'")

    x_scaled = scaler.transform(x.reshape(1, -1))
    p, hidden = forward_with_hidden(mlp, x_scaled)
    p_win = float(p.ravel()[0])

    return {
        "p_win": p_win,
        "threshold": threshold,
        "verdict": "take" if p_win >= threshold else "skip",
        "direction": direction,
        "feature_values": {name: float(v) for name, v in zip(feature_names, x)},
        "scaled_inputs": {name: float(v) for name, v in zip(feature_names, x_scaled.ravel())},
        "hidden_activations": hidden.ravel().tolist(),
    }


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return DASHBOARD_HTML_PATH.read_text(encoding="utf-8")
