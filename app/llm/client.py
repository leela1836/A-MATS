"""Thin OpenAI wrapper returning parsed JSON plus token/cost accounting.

Deliberately minimal: the agents own their prompts and schemas, this layer
only handles transport, JSON parsing, retries, and usage metering.

If no API key is configured, `LLMUnavailable` is raised so callers can fall
back to deterministic logic instead of failing the trading cycle.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

from app.config import get_config

# USD per 1M tokens. Update when pricing changes.
_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
}
_DEFAULT_PRICING = (2.50, 10.00)


class LLMUnavailable(RuntimeError):
    """No API key configured, or the provider could not be reached."""


@dataclass
class LLMResult:
    data: dict[str, Any]
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


def _cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    inp, out = _PRICING.get(model, _DEFAULT_PRICING)
    return (prompt_tokens / 1_000_000) * inp + (completion_tokens / 1_000_000) * out


def api_key() -> Optional[str]:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    return key or None


def is_available() -> bool:
    return api_key() is not None


def complete_json(
    system_prompt: str,
    user_payload: dict[str, Any],
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_retries: int = 2,
) -> LLMResult:
    """Call the model and parse a JSON object response."""
    key = api_key()
    if key is None:
        raise LLMUnavailable("OPENAI_API_KEY is not set")

    llm_cfg = get_config("agent").get("llm", {})
    model = model or llm_cfg.get("model", "gpt-4o")
    temperature = llm_cfg.get("temperature", 0.2) if temperature is None else temperature
    timeout = float(llm_cfg.get("timeout_seconds", 60))

    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise LLMUnavailable("openai package not installed") from exc

    client = OpenAI(api_key=key, timeout=timeout)

    last_err: Optional[Exception] = None
    for _ in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload)},
                ],
            )
            content = resp.choices[0].message.content or "{}"
            data = json.loads(content)
            usage = resp.usage
            pt = getattr(usage, "prompt_tokens", 0) or 0
            ct = getattr(usage, "completion_tokens", 0) or 0
            return LLMResult(
                data=data,
                model=model,
                prompt_tokens=pt,
                completion_tokens=ct,
                cost_usd=_cost(model, pt, ct),
            )
        except json.JSONDecodeError as exc:
            last_err = exc  # malformed JSON: retry
        except Exception as exc:
            raise LLMUnavailable(f"LLM call failed: {exc}") from exc

    raise LLMUnavailable(f"LLM returned unparseable JSON: {last_err}")
