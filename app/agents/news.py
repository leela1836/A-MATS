"""News Agent: turns curated Indian financial headlines into a sentiment read.

Sources are restricted by the collector's domain allowlist — this agent only
ever sees content from publications listed in configs/news.yaml.

Like the Reasoning Engine, the LLM is the primary path and a deterministic
neutral read is the fallback. Crucially the fallback is *neutral*, never a
guess: with no model available we must not fabricate a sentiment signal that
would nudge a trade.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from app.collectors.news_collector import NewsBundle, get_news_provider
from app.config import get_config
from app.llm.client import LLMUnavailable, complete_json
from app.models.state import NewsArticleRef, NewsSignals
from app.prompts import load_prompt

# Sentiment is cached per symbol: headlines refresh on a ~15-minute cadence,
# so re-running the same symbol inside that window must not spend a request.
# This matters because free-tier Gemini keys allow only ~20 requests/day.
_SENTIMENT_CACHE: dict[str, tuple[float, NewsSignals]] = {}


def _cache_ttl() -> float:
    return float(get_config("news").get("fetch", {}).get("cache_ttl_seconds", 900))


def clear_cache() -> None:
    _SENTIMENT_CACHE.clear()


def _label(score: float) -> str:
    if score >= 0.15:
        return "bullish"
    if score <= -0.15:
        return "bearish"
    return "neutral"


def analyse(symbol: str) -> tuple[NewsSignals, dict[str, Any]]:
    """Return (signals, usage). Never raises — news is advisory, not critical."""
    cached = _SENTIMENT_CACHE.get(symbol)
    if cached and time.time() - cached[0] < _cache_ttl():
        age = round(time.time() - cached[0])
        return cached[1], {"source": "cache", "reason": f"cached {age}s ago"}

    try:
        bundle = get_news_provider().get_news(symbol)
    except Exception as exc:
        return _neutral(symbol, NewsBundle(symbol=symbol)), {
            "source": "fallback", "reason": f"news fetch failed: {type(exc).__name__}",
        }

    refs = [
        NewsArticleRef(
            title=a.title, source=a.source, url=a.url,
            relevance=a.relevance, age_hours=a.age_hours,
        )
        for a in bundle.articles
    ]

    # No coverage: a genuine neutral, no need to spend a token on it.
    if not bundle.articles:
        signals = _neutral(symbol, bundle)
        return signals, {"source": "skipped", "reason": "no relevant articles"}

    cfg = get_config("agent").get("news_agent", {})
    version = str(cfg.get("prompt_version", "v1"))

    try:
        result = complete_json(
            system_prompt=load_prompt("news", version),
            user_payload={
                "symbol": symbol,
                "articles": [
                    {
                        "title": a.title,
                        "source": a.source,
                        "age_hours": a.age_hours,
                        "relevance": a.relevance,
                    }
                    for a in bundle.articles
                ],
            },
            model=cfg.get("model"),
            temperature=cfg.get("temperature"),
        )
    except LLMUnavailable as exc:
        signals = _neutral(symbol, bundle, articles=refs)
        return signals, {"source": "fallback", "reason": str(exc)[:120]}

    try:
        score = min(max(float(result.data.get("sentiment_score", 0.0)), -1.0), 1.0)
        confidence = min(max(float(result.data.get("confidence", 0.0)), 0.0), 1.0)
        events = [str(e)[:160] for e in (result.data.get("key_events") or [])][:5]
        signals = NewsSignals(
            symbol=symbol,
            sentiment_score=round(score, 3),
            sentiment_label=str(result.data.get("sentiment_label") or _label(score)),
            confidence=round(confidence, 3),
            key_events=events,
            summary=str(result.data.get("summary", ""))[:500],
            article_count=len(bundle.articles),
            sources_used=bundle.sources_used,
            articles=refs,
        )
    except (TypeError, ValueError) as exc:
        signals = _neutral(symbol, bundle, articles=refs)
        return signals, {
            "source": "fallback",
            "reason": f"unusable LLM output: {type(exc).__name__}",
            "model": result.model,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "cost_usd": result.cost_usd,
        }

    _SENTIMENT_CACHE[symbol] = (time.time(), signals)
    return signals, {
        "source": "llm",
        "model": result.model,
        "prompt_version": version,
        "articles": len(bundle.articles),
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "cost_usd": result.cost_usd,
    }


def _neutral(symbol: str, bundle: NewsBundle, articles: list[NewsArticleRef] | None = None) -> NewsSignals:
    """A deliberately signal-free read — never guess sentiment without a model."""
    return NewsSignals(
        symbol=symbol,
        sentiment_score=0.0,
        sentiment_label="neutral",
        confidence=0.0,
        key_events=[],
        summary="No sentiment computed (news agent unavailable or no coverage).",
        article_count=len(bundle.articles),
        sources_used=bundle.sources_used,
        articles=articles or [],
    )
