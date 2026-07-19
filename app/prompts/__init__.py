"""Versioned prompt loading.

Prompts live as individual markdown files named `<name>_<version>.md` so each
revision is a separate, diffable artifact under version control.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def load_prompt(name: str, version: str = "v1") -> str:
    path = PROMPT_DIR / f"{name}_{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"No prompt '{name}' version '{version}' at {path}")
    return path.read_text(encoding="utf-8")
