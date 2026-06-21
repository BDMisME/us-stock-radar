"""Data-source adapter interfaces.

These abstract base classes define the contract every market-data provider must
satisfy. Today we ship Alpaca IEX (real-time), Finnhub, FMP and yfinance. To
upgrade to a paid SIP feed later (dxFeed Nasdaq Basic, Finazon SIP, Alpaca SIP),
implement a new ``QuoteAdapter`` / ``HistoryAdapter`` against these same methods
and swap it in via market_monitor — nothing downstream needs to change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class Quote:
    symbol: str
    price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[float] = None
    source: str = ""


@dataclass
class NewsArticle:
    title: str
    source: str
    url: str
    published_at: str
    summary: str = ""
    related_symbols: str = ""


class QuoteAdapter(ABC):
    """A source of point-in-time quotes."""

    name: str = "base"

    @abstractmethod
    def get_quote(self, symbol: str) -> Optional[Quote]:
        ...

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """Default fan-out; subclasses may override with a batch endpoint."""
        out: dict[str, Quote] = {}
        for s in symbols:
            q = self.get_quote(s)
            if q is not None:
                out[s] = q
        return out


class HistoryAdapter(ABC):
    """A source of historical OHLCV bars."""

    name: str = "base"

    @abstractmethod
    def get_bars(self, symbol: str, timeframe: str = "1Day", limit: int = 200) -> pd.DataFrame:
        """Return a DataFrame with columns: open, high, low, close, volume,
        indexed (or with a column) by timestamp, oldest -> newest."""
        ...


class NewsAdapter(ABC):
    """A source of news articles."""

    name: str = "base"

    @abstractmethod
    def get_news(self, symbol: Optional[str] = None, limit: int = 10) -> list[NewsArticle]:
        ...
