"""A minimal multilayer perceptron in pure numpy.

Why not torch/sklearn: the problem is a few-hundred-row tabular binary
classification. A 2-layer MLP trained full-batch converges in milliseconds,
adds ZERO dependencies, and — seeded — produces byte-identical results every
run, which is what keeps the test suite offline and deterministic.

Everything is deliberately small. A large network on this little data would
memorise the training trades and predict noise out of sample; the whole point
of the accompanying walk-forward harness is to catch exactly that, so the
model it validates must be modest by construction.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np


# ── preprocessing ──

@dataclass
class StandardScaler:
    """Zero-mean/unit-variance per feature. Fitted on TRAIN only, then frozen."""
    mean: Optional[np.ndarray] = None
    std: Optional[np.ndarray] = None

    def fit(self, X: np.ndarray) -> "StandardScaler":
        self.mean = X.mean(axis=0)
        std = X.std(axis=0)
        std[std < 1e-9] = 1.0  # constant columns must not divide to inf
        self.std = std
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        return (X - self.mean) / self.std

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        return self.fit(X).transform(X)


# ── metrics ──

def roc_auc(y_true: np.ndarray, scores: np.ndarray) -> float:
    """AUC via the rank identity (Mann-Whitney U). No sklearn needed."""
    y_true = np.asarray(y_true).ravel()
    scores = np.asarray(scores).ravel()
    pos, neg = y_true == 1, y_true == 0
    n_pos, n_neg = int(pos.sum()), int(neg.sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order = scores.argsort()
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(scores) + 1)
    # Average ranks for ties so AUC is exact on tied scores.
    _, inv, counts = np.unique(scores, return_inverse=True, return_counts=True)
    cum = np.cumsum(counts)
    start = cum - counts
    avg = (start + cum + 1) / 2.0
    ranks = avg[inv]
    auc = (ranks[pos].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    return float(auc)


# ── model ──

@dataclass
class MLP:
    """Feed-forward net for binary probability output.

    layer_sizes = [n_in, h1, ..., 1]. A trailing 1 with no hidden layers is
    plain logistic regression — used as the honesty baseline in train.py.
    """
    layer_sizes: list[int]
    l2: float = 1e-3
    lr: float = 0.01
    seed: int = 7
    W: list[np.ndarray] = field(default_factory=list)
    b: list[np.ndarray] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.W:
            rng = np.random.default_rng(self.seed)
            self.W, self.b = [], []
            for n_in, n_out in zip(self.layer_sizes[:-1], self.layer_sizes[1:]):
                # He init for the ReLU layers; harmless for the final unit.
                self.W.append(rng.standard_normal((n_in, n_out)) * np.sqrt(2.0 / n_in))
                self.b.append(np.zeros(n_out))

    # -- forward --
    def _forward(self, X: np.ndarray) -> tuple[np.ndarray, list]:
        a = X
        cache = [X]
        last = len(self.W) - 1
        for i, (W, b) in enumerate(zip(self.W, self.b)):
            z = a @ W + b
            a = z if i == last else np.maximum(z, 0.0)  # ReLU hidden, linear pre-sigmoid
            cache.append(a)
        p = 1.0 / (1.0 + np.exp(-np.clip(cache[-1], -30, 30)))
        return p, cache

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self._forward(np.asarray(X, dtype=float))[0].ravel()

    # -- training (full-batch Adam) --
    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        epochs: int = 400,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        patience: int = 40,
    ) -> "MLP":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float).reshape(-1, 1)
        n = len(X)

        mW = [np.zeros_like(w) for w in self.W]
        vW = [np.zeros_like(w) for w in self.W]
        mb = [np.zeros_like(b) for b in self.b]
        vb = [np.zeros_like(b) for b in self.b]
        beta1, beta2, eps = 0.9, 0.999, 1e-8

        best_val, best_state, wait = np.inf, None, 0
        for t in range(1, epochs + 1):
            p, cache = self._forward(X)
            # dL/dz_out for BCE + sigmoid collapses to (p - y).
            delta = (p - y) / n
            gW, gb = [None] * len(self.W), [None] * len(self.b)
            for i in reversed(range(len(self.W))):
                a_prev = cache[i]
                gW[i] = a_prev.T @ delta + self.l2 * self.W[i]
                gb[i] = delta.sum(axis=0)
                if i > 0:
                    da = delta @ self.W[i].T
                    delta = da * (cache[i] > 0)  # ReLU derivative
            for i in range(len(self.W)):
                mW[i] = beta1 * mW[i] + (1 - beta1) * gW[i]
                vW[i] = beta2 * vW[i] + (1 - beta2) * gW[i] ** 2
                mb[i] = beta1 * mb[i] + (1 - beta1) * gb[i]
                vb[i] = beta2 * vb[i] + (1 - beta2) * gb[i] ** 2
                mWh, vWh = mW[i] / (1 - beta1 ** t), vW[i] / (1 - beta2 ** t)
                mbh, vbh = mb[i] / (1 - beta1 ** t), vb[i] / (1 - beta2 ** t)
                self.W[i] -= self.lr * mWh / (np.sqrt(vWh) + eps)
                self.b[i] -= self.lr * mbh / (np.sqrt(vbh) + eps)

            if X_val is not None and len(X_val):
                pv = np.clip(self.predict_proba(X_val), 1e-7, 1 - 1e-7)
                yv = np.asarray(y_val, dtype=float).ravel()
                val_loss = -np.mean(yv * np.log(pv) + (1 - yv) * np.log(1 - pv))
                if val_loss < best_val - 1e-5:
                    best_val, wait = val_loss, 0
                    best_state = ([w.copy() for w in self.W], [b.copy() for b in self.b])
                else:
                    wait += 1
                    if wait >= patience:
                        break
        if best_state is not None:
            self.W, self.b = best_state
        return self

    # -- persistence --
    def to_dict(self) -> dict:
        return {
            "layer_sizes": self.layer_sizes,
            "l2": self.l2, "lr": self.lr, "seed": self.seed,
            "W": [w.tolist() for w in self.W],
            "b": [b.tolist() for b in self.b],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MLP":
        m = cls(layer_sizes=d["layer_sizes"], l2=d["l2"], lr=d["lr"], seed=d["seed"],
                W=[np.array(w, dtype=float) for w in d["W"]],
                b=[np.array(b, dtype=float) for b in d["b"]])
        return m


def save_model(path: str | Path, mlp: MLP, scaler: StandardScaler,
               feature_names: list[str], threshold: float, meta: dict) -> None:
    """One self-describing JSON: weights, scaler, feature order, gate threshold.

    Feature order is stored so inference cannot silently feed columns in the
    wrong order — validator.py asserts the live extractor matches this list.
    """
    payload = {
        "mlp": mlp.to_dict(),
        "scaler": {"mean": scaler.mean.tolist(), "std": scaler.std.tolist()},
        "feature_names": feature_names,
        "threshold": threshold,
        "meta": meta,
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2))


def load_model(path: str | Path) -> dict:
    d = json.loads(Path(path).read_text())
    mlp = MLP.from_dict(d["mlp"])
    scaler = StandardScaler(mean=np.array(d["scaler"]["mean"]),
                            std=np.array(d["scaler"]["std"]))
    return {"mlp": mlp, "scaler": scaler, "feature_names": d["feature_names"],
            "threshold": d["threshold"], "meta": d.get("meta", {})}
