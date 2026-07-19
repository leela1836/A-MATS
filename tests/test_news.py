"""News agent tests — trust boundary, relevance filtering, and sentiment.

The allowlist tests are the important ones: they assert the agent cannot
fetch content from a domain that isn't explicitly curated.
"""
import pytest

from app.agents import news as news_agent
from app.collectors import news_collector as nc
from app.collectors.news_collector import Article, NewsSourceError
from app.llm.client import LLMResult, LLMUnavailable


# ── trust boundary ──

def test_allowlist_permits_curated_domains():
    permitted = nc.allowed_domains()
    assert "www.moneycontrol.com" in permitted
    assert "economictimes.indiatimes.com" in permitted
    nc.assert_allowed("https://www.moneycontrol.com/rss/business.xml")


@pytest.mark.parametrize("url", [
    "https://evil.example.com/feed.xml",
    "https://blogspot.com/hot-stock-tips",
    "https://moneycontrol.com.attacker.net/rss",   # lookalike host
    "https://x.com/some_finfluencer",
])
def test_allowlist_refuses_everything_else(url):
    with pytest.raises(NewsSourceError, match="off-allowlist"):
        nc.assert_allowed(url)


def test_non_http_schemes_refused():
    for url in ("file:///etc/passwd", "ftp://host/f", "javascript:alert(1)"):
        with pytest.raises(NewsSourceError):
            nc.assert_allowed(url)


def test_disabled_source_is_not_allowlisted(monkeypatch):
    """Disabling a source in config must revoke fetch permission."""
    cfg = {
        "sources": [
            {"name": "a", "domain": "allowed.example", "url": "https://allowed.example/f", "enabled": True},
            {"name": "b", "domain": "disabled.example", "url": "https://disabled.example/f", "enabled": False},
        ]
    }
    monkeypatch.setattr(nc, "get_config", lambda name: cfg)
    nc.assert_allowed("https://allowed.example/f")
    with pytest.raises(NewsSourceError):
        nc.assert_allowed("https://disabled.example/f")


# ── relevance filtering ──

def _article(title, source="moneycontrol_markets", age=1.0, trust=0.9):
    return Article(title=title, url="", source=source, domain="www.moneycontrol.com",
                   trust=trust, age_hours=age, summary="")


def _cfg():
    return {
        "fetch": {"lookback_hours": 48, "max_articles_per_symbol": 12},
        "symbol_aliases": {"RELIANCE.NS": ["reliance", "ril", "jio"]},
        "market_wide_terms": ["nifty", "sensex"],
    }


def test_direct_mentions_rank_above_market_context():
    arts = [
        _article("Nifty ends flat amid global cues", age=1.0),
        _article("Reliance Industries wins new order", age=5.0),
    ]
    out = nc.filter_for_symbol(arts, "RELIANCE.NS", _cfg())
    assert out[0].relevance == "direct"
    assert "Reliance" in out[0].title


def test_irrelevant_articles_dropped():
    arts = [_article("Monsoon update for Kerala farmers")]
    assert nc.filter_for_symbol(arts, "RELIANCE.NS", _cfg()) == []


def test_stale_articles_dropped():
    arts = [_article("Reliance announces buyback", age=200.0)]
    assert nc.filter_for_symbol(arts, "RELIANCE.NS", _cfg()) == []


def test_word_boundary_prevents_false_match():
    """'ITC' must not match inside 'switch'."""
    cfg = {**_cfg(), "symbol_aliases": {"ITC.NS": ["itc"]}, "market_wide_terms": []}
    arts = [_article("Companies switch to renewable power")]
    assert nc.filter_for_symbol(arts, "ITC.NS", cfg) == []


# ── agent behaviour ──

def test_no_articles_skips_llm_and_returns_neutral(monkeypatch):
    monkeypatch.setattr(news_agent, "get_news_provider",
                        lambda: _FakeProvider([]))
    signals, usage = news_agent.analyse("RELIANCE.NS")
    assert usage["source"] == "skipped"
    assert signals.sentiment_score == 0.0
    assert signals.confidence == 0.0


def test_fallback_is_neutral_not_a_guess(monkeypatch):
    """Without an LLM we must emit no signal, rather than invent one."""
    monkeypatch.setattr(news_agent, "get_news_provider",
                        lambda: _FakeProvider([_article("Reliance wins order")]))
    monkeypatch.setattr(news_agent, "complete_json",
                        lambda *a, **k: (_ for _ in ()).throw(LLMUnavailable("no key")))
    signals, usage = news_agent.analyse("RELIANCE.NS")
    assert usage["source"] == "fallback"
    assert signals.sentiment_score == 0.0
    assert signals.article_count == 1  # articles were found, just not scored


def test_llm_sentiment_is_parsed_and_clamped(monkeypatch):
    monkeypatch.setattr(news_agent, "get_news_provider",
                        lambda: _FakeProvider([_article("Reliance profit jumps 25%")]))

    def fake(*a, **k):
        return LLMResult(
            data={
                "sentiment_score": 2.5,  # out of range on purpose
                "sentiment_label": "bullish", "confidence": 0.7,
                "key_events": ["Q1 profit up 25%"], "summary": "Strong earnings.",
            },
            model="gemini-2.5-flash-lite", prompt_tokens=400,
            completion_tokens=60, cost_usd=0.000064,
        )
    monkeypatch.setattr(news_agent, "complete_json", fake)
    signals, usage = news_agent.analyse("RELIANCE.NS")
    assert usage["source"] == "llm"
    assert signals.sentiment_score == 1.0  # clamped
    assert signals.key_events == ["Q1 profit up 25%"]


def test_sentiment_is_cached_to_conserve_daily_quota(monkeypatch):
    """Repeat runs inside the TTL must not spend another LLM request."""
    monkeypatch.setattr(news_agent, "get_news_provider",
                        lambda: _FakeProvider([_article("Reliance profit jumps")]))
    calls = {"n": 0}

    def fake(*a, **k):
        calls["n"] += 1
        return LLMResult(
            data={"sentiment_score": 0.5, "sentiment_label": "bullish",
                  "confidence": 0.6, "key_events": [], "summary": "ok"},
            model="gemini-2.5-flash", prompt_tokens=100, completion_tokens=20,
            cost_usd=0.0001,
        )

    monkeypatch.setattr(news_agent, "complete_json", fake)

    first, u1 = news_agent.analyse("RELIANCE.NS")
    second, u2 = news_agent.analyse("RELIANCE.NS")
    assert calls["n"] == 1, "second call must be served from cache"
    assert u1["source"] == "llm"
    assert u2["source"] == "cache"
    assert second.sentiment_score == first.sentiment_score


def test_fetch_failure_is_non_fatal(monkeypatch):
    class Boom:
        def get_news(self, symbol):
            raise ConnectionError("network down")
    monkeypatch.setattr(news_agent, "get_news_provider", lambda: Boom())
    signals, usage = news_agent.analyse("RELIANCE.NS")
    assert usage["source"] == "fallback"
    assert signals.sentiment_score == 0.0


class _FakeProvider:
    def __init__(self, articles):
        self._articles = articles

    def get_news(self, symbol):
        from app.collectors.news_collector import NewsBundle
        return NewsBundle(symbol=symbol, articles=self._articles,
                          sources_used=["moneycontrol_markets"])
