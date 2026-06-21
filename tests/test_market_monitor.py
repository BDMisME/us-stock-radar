"""Market monitor behavior tests."""
from __future__ import annotations


def test_poll_interval_has_five_second_floor(monkeypatch):
    from config.settings import settings
    from services import market_monitor

    monkeypatch.setattr(settings, "watchlist_poll_seconds", 1, raising=False)
    assert market_monitor.poll_interval_seconds() == 5

    monkeypatch.setattr(settings, "watchlist_poll_seconds", 8, raising=False)
    assert market_monitor.poll_interval_seconds() == 8
