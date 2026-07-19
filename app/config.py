"""Loads and caches the YAML config files under configs/."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"

_CONFIG_FILES = {
    "agent": "agent.yaml",
    "risk": "risk.yaml",
    "market": "market.yaml",
    "trading": "trading.yaml",
}


def _load(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / _CONFIG_FILES[name]
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache(maxsize=None)
def get_config(name: str) -> dict[str, Any]:
    """Return a parsed config section by short name (agent/risk/market/trading)."""
    if name not in _CONFIG_FILES:
        raise KeyError(f"Unknown config '{name}'. Known: {sorted(_CONFIG_FILES)}")
    return _load(name)


def all_configs() -> dict[str, dict[str, Any]]:
    return {name: get_config(name) for name in _CONFIG_FILES}
