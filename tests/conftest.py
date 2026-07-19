"""Shared test fixtures.

Isolates the paper-broker singleton to a per-test temp file, and injects a
deterministic market-data provider so the graph never hits the network.
"""
import pytest

from app.collectors import market_collector, news_collector
from app.execution import paper_broker
from app.models.state import Direction, MarketAnalysis


@pytest.fixture(autouse=True)
def isolated_broker(tmp_path, monkeypatch):
    broker = paper_broker.PaperBroker(path=tmp_path / "portfolio.json")
    monkeypatch.setattr(paper_broker, "_broker", broker)
    yield broker


class FakeMarketProvider:
    """Deterministic, offline market data for tests."""

    _LONG = {
        "RELIANCE.NS": (1400.0, 20.0),
        "TCS.NS": (3200.0, 40.0),
    }

    def get_analysis(self, symbol: str) -> MarketAnalysis:
        if symbol == "__BADFEED__":
            raise market_collector.MarketDataError("forced bad feed")
        if symbol == "SIDEWAYS.NS":
            return MarketAnalysis(
                symbol=symbol, last_price=500.0, trend="sideways",
                signal=Direction.HOLD, confidence=0.2,
                indicators={"rsi_14": 50.0, "atr_14": 5.0},
            )
        price, atr = self._LONG.get(symbol, (1000.0, 15.0))
        return MarketAnalysis(
            symbol=symbol, last_price=price, trend="up",
            signal=Direction.LONG, confidence=0.72,
            indicators={
                "ema_20": price * 0.98, "ema_50": price * 0.96,
                "rsi_14": 58.0, "atr_14": atr,
            },
        )


@pytest.fixture(autouse=True)
def fake_market(monkeypatch):
    monkeypatch.setattr(market_collector, "_provider", FakeMarketProvider())


class FakeNewsProvider:
    """Returns no articles, so graph tests never touch the network."""

    def get_news(self, symbol: str):
        return news_collector.NewsBundle(symbol=symbol, articles=[], sources_used=[])


@pytest.fixture(autouse=True)
def fake_news(monkeypatch):
    from app.agents import news as news_agent

    news_agent.clear_cache()  # sentiment cache must not leak between tests
    monkeypatch.setattr(news_collector, "_provider", FakeNewsProvider())


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    """Force the deterministic fallback so tests never spend tokens.

    Must clear EVERY provider key — the active provider comes from config,
    so leaving any one set would let the suite make real API calls.
    """
    for env in ("OPENAI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY",
                "AZURE_OPENAI_API_KEY"):
        monkeypatch.delenv(env, raising=False)
