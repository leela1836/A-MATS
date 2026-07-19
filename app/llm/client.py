"""Multi-provider LLM wrapper returning parsed JSON plus token/cost accounting.

Provider is chosen by `configs/agent.yaml -> llm.provider` ("google" or
"openai"). Both paths return the same LLMResult so agents stay
provider-agnostic.

Deliberately minimal: agents own their prompts and schemas; this layer only
handles transport, JSON parsing, retries, and usage metering.

If no API key is configured, `LLMUnavailable` is raised so callers can fall
back to deterministic logic instead of failing the trading cycle.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

from app.config import get_config

# USD per 1M tokens, (input, output). Approximate — update when pricing moves.
_PRICING: dict[str, tuple[float, float]] = {
    # Google
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.0-flash": (0.10, 0.40),
    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
}
_DEFAULT_PRICING = (0.30, 2.50)

_GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


class LLMUnavailable(RuntimeError):
    """No API key configured, or the provider could not be reached."""


class ModelUnavailable(LLMUnavailable):
    """This specific model is rate-limited (429) or retired (404).

    Distinct from LLMUnavailable because each Gemini model carries its OWN
    daily quota — exhausting one says nothing about the next, so the caller
    should try the next model in the chain rather than give up.
    """

    def __init__(self, model: str, status: int, detail: str = ""):
        self.model, self.status = model, status
        super().__init__(f"{model}: HTTP {status} {detail[:120]}")


@dataclass
class LLMResult:
    data: dict[str, Any]
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    provider: str = ""


def _cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    inp, out = _PRICING.get(model, _DEFAULT_PRICING)
    return (prompt_tokens / 1_000_000) * inp + (completion_tokens / 1_000_000) * out


def provider_name() -> str:
    return str(get_config("agent").get("llm", {}).get("provider", "google")).lower()


# Providers that speak the OpenAI wire format. NVIDIA NIM and other hosted
# gateways only differ by base_url + key env, so they reuse the OpenAI path.
_OPENAI_COMPATIBLE: dict[str, tuple[str, Optional[str]]] = {
    # provider: (key env var, base_url or None for OpenAI's own default)
    "openai": ("OPENAI_API_KEY", None),
    "nvidia": ("NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1"),
}


def api_key(provider: Optional[str] = None) -> Optional[str]:
    provider = provider or provider_name()
    if provider == "google":
        env = "GOOGLE_API_KEY"
    else:
        env = _OPENAI_COMPATIBLE.get(provider, ("OPENAI_API_KEY", None))[0]
    return os.getenv(env, "").strip() or None


def _base_url(provider: str) -> Optional[str]:
    """Explicit config wins, else the provider's known gateway."""
    configured = get_config("agent").get("llm", {}).get("base_url")
    if configured:
        return str(configured)
    return _OPENAI_COMPATIBLE.get(provider, (None, None))[1]


def is_available(provider: Optional[str] = None) -> bool:
    return api_key(provider) is not None


def complete_json(
    system_prompt: str,
    user_payload: dict[str, Any],
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_retries: int = 2,
) -> LLMResult:
    """Call the configured provider and parse a JSON object response."""
    provider = provider_name()
    key = api_key(provider)
    if key is None:
        env = "GOOGLE_API_KEY" if provider == "google" else "OPENAI_API_KEY"
        raise LLMUnavailable(f"{env} is not set")

    llm_cfg = get_config("agent").get("llm", {})
    temperature = llm_cfg.get("temperature", 0.2) if temperature is None else temperature
    timeout = float(llm_cfg.get("timeout_seconds", 60))
    max_tokens = int(llm_cfg.get("max_tokens", 4096))

    payload_text = json.dumps(user_payload)
    chain = model_chain(model)
    exhausted: list[str] = []

    for candidate in chain:
        last_err: Optional[Exception] = None
        for _ in range(max_retries):
            try:
                if provider == "google":
                    raw, pt, ct = _gemini_call(
                        key, candidate, system_prompt, payload_text,
                        temperature, max_tokens, timeout,
                    )
                else:
                    raw, pt, ct = _openai_call(
                        key, candidate, system_prompt, payload_text, temperature,
                        timeout, base_url=_base_url(provider),
                    )
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise json.JSONDecodeError("expected a JSON object", raw, 0)
                return LLMResult(
                    data=data, model=candidate, prompt_tokens=pt, completion_tokens=ct,
                    cost_usd=_cost(candidate, pt, ct), provider=provider,
                )
            except json.JSONDecodeError as exc:
                last_err = exc  # malformed JSON: retry the same model
            except ModelUnavailable as exc:
                # This model's quota is spent (or it's retired) — the next
                # model has an independent quota, so move on immediately.
                exhausted.append(f"{candidate}({exc.status})")
                last_err = exc
                break
            except LLMUnavailable:
                raise
            except Exception as exc:
                raise LLMUnavailable(f"LLM call failed: {exc}") from exc

        if isinstance(last_err, json.JSONDecodeError):
            raise LLMUnavailable(f"LLM returned unparseable JSON: {last_err}")

    raise LLMUnavailable(
        f"all models exhausted: {', '.join(exhausted) or 'none tried'}"
    )


def model_chain(preferred: Optional[str] = None) -> list[str]:
    """Ordered models to try. Each Gemini model has its own daily quota, so
    chaining multiplies the effective free-tier budget."""
    llm_cfg = get_config("agent").get("llm", {})
    primary = preferred or llm_cfg.get("model", "gemini-2.5-flash")
    chain = [primary]
    for m in llm_cfg.get("fallback_models", []) or []:
        if m and m not in chain:
            chain.append(str(m))
    return chain


def _gemini_call(
    key: str, model: str, system_prompt: str, user_text: str,
    temperature: float, max_tokens: int, timeout: float,
) -> tuple[str, int, int]:
    import httpx

    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
            "maxOutputTokens": max_tokens,
            # Structured extraction needs no deliberation; keeps latency and
            # token spend down. Raise if a task genuinely needs reasoning time.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    resp = httpx.post(
        _GEMINI_ENDPOINT.format(model=model),
        params={"key": key}, json=body, timeout=timeout,
    )
    if resp.status_code in (429, 404):
        # 429 = daily/rate quota spent, 404 = model retired for this account.
        # Both mean "try a different model", not "give up".
        raise ModelUnavailable(model, resp.status_code, resp.text)
    if resp.status_code != 200:
        raise LLMUnavailable(f"Gemini HTTP {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise LLMUnavailable(f"Gemini returned no candidates: {str(data)[:160]}")

    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts)
    if not text.strip():
        reason = candidates[0].get("finishReason", "?")
        raise LLMUnavailable(f"Gemini returned empty text (finishReason={reason})")

    usage = data.get("usageMetadata", {})
    return (
        text,
        int(usage.get("promptTokenCount", 0)),
        int(usage.get("candidatesTokenCount", 0)),
    )


def _openai_call(
    key: str, model: str, system_prompt: str, user_text: str,
    temperature: float, timeout: float, base_url: Optional[str] = None,
) -> tuple[str, int, int]:
    """OpenAI-compatible chat completion (OpenAI, NVIDIA NIM, ...)."""
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise LLMUnavailable("openai package not installed") from exc

    client = OpenAI(api_key=key, timeout=timeout, base_url=base_url)
    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
    )
    usage = resp.usage
    return (
        resp.choices[0].message.content or "{}",
        getattr(usage, "prompt_tokens", 0) or 0,
        getattr(usage, "completion_tokens", 0) or 0,
    )
