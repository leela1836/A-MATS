"""Curated news ingestion for Indian markets.

TRUST MODEL — the point of this module:

The agent must never read arbitrary internet content. Every request passes
through `assert_allowed()`, which refuses any URL whose host is not in the
`sources` registry of `configs/news.yaml`. The allowlist is derived from
config at call time, so curating sources is a config change, not a code
change. Redirects are disabled, because a 302 to an unapproved domain would
otherwise silently defeat the allowlist.

We read RSS feeds rather than scraping HTML: feeds are published for
syndication, are stable to parse, and keep our footprint light.
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Any, Optional
from urllib.parse import urlparse

from app.config import get_config


class NewsSourceError(RuntimeError):
    """A URL was refused (not on the allowlist) or a feed could not be read."""


@dataclass
class Article:
    title: str
    url: str
    source: str
    domain: str
    trust: float
    published: Optional[str] = None
    summary: str = ""
    age_hours: Optional[float] = None
    relevance: str = "market"  # "direct" (names the company) | "market" (context)


@dataclass
class NewsBundle:
    symbol: str
    articles: list[Article] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ── allowlist ──

def allowed_domains() -> set[str]:
    """Domains the agent is permitted to fetch, from configs/news.yaml."""
    return {
        s["domain"].lower()
        for s in get_config("news").get("sources", [])
        if s.get("enabled", False)
    }


def assert_allowed(url: str) -> None:
    """Raise unless `url` points at an enabled, allowlisted domain."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise NewsSourceError(f"refused non-http(s) URL: {url[:80]}")
    host = (parsed.hostname or "").lower()
    permitted = allowed_domains()
    if host not in permitted:
        raise NewsSourceError(
            f"refused off-allowlist domain '{host}' "
            f"(permitted: {sorted(permitted) or 'none'})"
        )


# ── fetching ──

def _fetch_feed(source: dict[str, Any], cfg: dict[str, Any]) -> list[Article]:
    import httpx

    url = source["url"]
    assert_allowed(url)  # hard gate — before any network call

    fetch_cfg = cfg.get("fetch", {})
    resp = httpx.get(
        url,
        headers={"User-Agent": fetch_cfg.get("user_agent", "AMATS/0.1")},
        timeout=float(fetch_cfg.get("timeout_seconds", 20)),
        follow_redirects=bool(fetch_cfg.get("follow_redirects", False)),
    )
    if resp.status_code != 200:
        raise NewsSourceError(f"{source['name']}: HTTP {resp.status_code}")

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as exc:
        raise NewsSourceError(f"{source['name']}: malformed feed ({exc})") from exc

    limit = int(fetch_cfg.get("max_articles_per_source", 25))
    now = time.time()
    articles: list[Article] = []

    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        link = (item.findtext("link") or "").strip()
        # An article link off the allowlist is dropped, not followed.
        if link:
            try:
                assert_allowed(link)
            except NewsSourceError:
                link = ""

        published = (item.findtext("pubDate") or "").strip() or None
        age_hours = None
        if published:
            try:
                age_hours = round((now - parsedate_to_datetime(published).timestamp()) / 3600, 1)
            except (TypeError, ValueError):
                age_hours = None

        articles.append(Article(
            title=_clean(title),
            url=link,
            source=source["name"],
            domain=source["domain"],
            trust=float(source.get("trust", 0.5)),
            published=published,
            summary=_clean((item.findtext("description") or "")[:400]),
            age_hours=age_hours,
        ))
    return articles


def _age_hours(published: str) -> Optional[float]:
    """Parse NSE's '19-Jul-2026 21:54:15' stamp into an age in hours."""
    from datetime import datetime

    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y"):
        try:
            return round((datetime.now() - datetime.strptime(published.strip(), fmt)).total_seconds() / 3600, 1)
        except ValueError:
            continue
    return None


def _clean(text: str) -> str:
    """Strip tags and decode the entities RSS descriptions are riddled with."""
    import html
    import re

    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


# ── relevance ──

def _matches(text: str, terms: list[str]) -> bool:
    import re

    low = text.lower()
    for t in terms:
        t = str(t).lower().strip()
        if not t:
            continue
        # Word-boundary match so "itc" doesn't hit "switch".
        if re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", low):
            return True
    return False


def filter_for_symbol(articles: list[Article], symbol: str, cfg: dict[str, Any]) -> list[Article]:
    aliases = cfg.get("symbol_aliases", {}).get(symbol, [])
    if not aliases:
        # Fall back to the bare ticker, e.g. RELIANCE.NS -> "reliance".
        aliases = [symbol.split(".")[0].lower()]
    market_terms = cfg.get("market_wide_terms", [])
    max_age = float(cfg.get("fetch", {}).get("lookback_hours", 48))

    picked: list[Article] = []
    for a in articles:
        if a.age_hours is not None and a.age_hours > max_age:
            continue
        blob = f"{a.title} {a.summary}"
        if _matches(blob, aliases):
            a.relevance = "direct"
            picked.append(a)
        elif _matches(blob, market_terms):
            a.relevance = "market"
            picked.append(a)

    # Company-specific news first, then most recent, then most trusted.
    picked.sort(key=lambda a: (
        0 if a.relevance == "direct" else 1,
        a.age_hours if a.age_hours is not None else 9e9,
        -a.trust,
    ))
    return picked[: int(cfg.get("fetch", {}).get("max_articles_per_symbol", 12))]


# ── provider ──

class NewsProvider:
    """Fetches allowlisted feeds with a TTL cache shared across symbols."""

    def __init__(self):
        self._cache: dict[str, tuple[float, list[Article]]] = {}

    def _ttl(self, cfg: dict[str, Any]) -> float:
        return float(cfg.get("fetch", {}).get("cache_ttl_seconds", 900))

    def _official(self, symbol: str, bundle: NewsBundle) -> list[Article]:
        """Exchange-filed disclosures for this symbol.

        These outrank media entirely: they are the company's own filings,
        tagged with an exact NSE symbol, so relevance needs no keyword
        guessing and there is nothing speculative about them.
        """
        from app.collectors.nse_official import (
            fetch_announcements,
            to_nse_symbol,
        )

        plain = to_nse_symbol(symbol)
        out: list[Article] = []
        try:
            for a in fetch_announcements():
                if a.symbol != plain:
                    continue
                out.append(Article(
                    title=a.title, url=a.url, source="nse_official",
                    domain="www.nseindia.com", trust=1.0,
                    published=a.published, summary=a.detail,
                    age_hours=_age_hours(a.published), relevance="direct",
                ))
            bundle.sources_used.append("nse_official")
        except Exception as exc:
            bundle.errors.append(f"nse_official: {type(exc).__name__}: {str(exc)[:80]}")
        return out

    def get_news(self, symbol: str) -> NewsBundle:
        cfg = get_config("news")
        bundle = NewsBundle(symbol=symbol)
        pool: list[Article] = []
        now = time.time()

        for source in cfg.get("sources", []):
            if not source.get("enabled", False):
                continue
            name = source["name"]
            cached = self._cache.get(name)
            if cached and now - cached[0] < self._ttl(cfg):
                pool.extend(cached[1])
                bundle.sources_used.append(name)
                continue
            try:
                articles = _fetch_feed(source, cfg)
            except Exception as exc:
                bundle.errors.append(f"{name}: {type(exc).__name__}: {str(exc)[:100]}")
                continue
            self._cache[name] = (now, articles)
            pool.extend(articles)
            bundle.sources_used.append(name)

        # Media articles get keyword-filtered; official filings are already
        # symbol-exact, so they bypass the relevance guesswork and lead.
        official = self._official(symbol, bundle)
        bundle.articles = official + filter_for_symbol(pool, symbol, cfg)
        return bundle


_provider: Optional[NewsProvider] = None


def get_news_provider() -> NewsProvider:
    global _provider
    if _provider is None:
        _provider = NewsProvider()
    return _provider
