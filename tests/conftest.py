"""Shared test fixtures.

Isolates the paper-broker singleton to a per-test temp file so tests never
touch the real data/portfolio.json.
"""
import pytest

from app.execution import paper_broker


@pytest.fixture(autouse=True)
def isolated_broker(tmp_path, monkeypatch):
    broker = paper_broker.PaperBroker(path=tmp_path / "portfolio.json")
    monkeypatch.setattr(paper_broker, "_broker", broker)
    yield broker
