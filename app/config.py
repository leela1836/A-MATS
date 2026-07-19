"""Loads and caches the YAML config files under configs/.

Also loads secrets from the gitignored .env at import time so every module
sees API keys via os.getenv without needing to know where they came from.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "configs"

try:  # optional dependency; absence just means no .env loading
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:  # pragma: no cover
    pass

_CONFIG_FILES = {
    "agent": "agent.yaml",
    "risk": "risk.yaml",
    "market": "market.yaml",
    "trading": "trading.yaml",
    "news": "news.yaml",
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
