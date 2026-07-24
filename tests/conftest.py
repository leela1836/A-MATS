"""Shared test fixtures.

Isolates the paper-broker singleton to a per-test temp file, and injects a
deterministic market-data provider so the graph never hits the network.
"""
import pytest

from app import market_calendar
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


@pytest.fixture(autouse=True)
def fake_history(monkeypatch):
    """Stub raw OHLCV so anything calling fetch_history directly (the feature
    capture in scans, dataset builders) stays offline and deterministic."""
    import numpy as np
    import pandas as pd

    def _hist(symbol, period="2y", interval="1d", **_kw):
        n = 260
        idx = pd.date_range("2024-01-01", periods=n, freq="D")
        rng = np.random.default_rng(abs(hash(symbol)) % (2 ** 32))
        close = 1000.0 + np.cumsum(rng.standard_normal(n))
        return pd.DataFrame(
            {"Open": close, "High": close + 2, "Low": close - 2,
             "Close": close, "Volume": 1_000_000.0}, index=idx,
        )

    monkeypatch.setattr(market_collector, "fetch_history", _hist)


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
def no_nse_network(request, monkeypatch):
    """Stub every official-NSE fetch so the suite never hits nseindia.com."""
    from app.collectors import nse_official

    # test_nse_official exercises these functions directly (stubbing the
    # transport instead), so blanket-replacing them there would test nothing.
    if request.module.__name__.endswith("test_nse_official"):
        return

    monkeypatch.setattr(nse_official, "fetch_asm_symbols", lambda refresh=False: set())
    monkeypatch.setattr(nse_official, "fetch_announcements", lambda refresh=False: [])
    monkeypatch.setattr(
        nse_official, "fetch_trading_holidays",
        lambda segment="CM", refresh=False: {__import__("datetime").date(2026, 1, 26)},
    )


@pytest.fixture(autouse=True)
def market_open(monkeypatch):
    """Pin the session to OPEN so pipeline tests don't depend on the clock.

    Without this the suite passes on a Tuesday afternoon and fails on a
    Sunday. Tests that exercise the closed-market path override this.
    """
    monkeypatch.setattr(
        market_calendar, "trading_allowed", lambda now=None: (True, "test: forced open")
    )


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    """Force the deterministic fallback so tests never spend tokens.

    Must clear EVERY provider key — the active provider comes from config,
    so leaving any one set would let the suite make real API calls.
    """
    for env in ("OPENAI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY",
                "AZURE_OPENAI_API_KEY"):
        monkeypatch.delenv(env, raising=False)
