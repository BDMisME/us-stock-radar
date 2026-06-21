"""Financial Modeling Prep (FMP) adapter — quotes, daily history, news.

Plain REST via requests. Rate-limited for the free tier. Used as a secondary
backup to Finnhub for watchlist polling and news.
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
import requests

from config.settings import settings
from data_adapters._ratelimit import RateLimiter
from data_adapters.base import HistoryAdapter, NewsAdapter, NewsArticle, Quote, QuoteAdapter

logger = logging.getLogger(__name__)
_limiter = RateLimiter(min_interval_seconds=1.0)
_BASE = "https://financialmodelingprep.com/api/v3"
_TIMEOUT = 12


class FMPAdapter(QuoteAdapter, HistoryAdapter, NewsAdapter):
    name = "fmp"

    @property
    def enabled(self) -> bool:
        return settings.fmp_enabled

    def _get(self, path: str, params: Optional[dict] = None):
        params = dict(params or {})
        params["apikey"] = settings.fmp_api_key
        _limiter.wait()
        try:
            resp = requests.get(f"{_BASE}/{path}", params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("FMP GET %s failed: %s", path, exc)
            return None

    def get_quote(self, symbol: str) -> Optional[Quote]:
        if not self.enabled:
            return None
        data = self._get(f"quote/{symbol}")
        if not data:
            return None
        row = data[0] if isinstance(data, list) else data
        price = row.get("price")
        if price is None:
            return None
        return Quote(
            symbol=symbol, price=float(price),
            volume=float(row["volume"]) if row.get("volume") is not None else None,
            source=self.name,
        )

    def get_bars(self, symbol: str, timeframe: str = "1Day", limit: int = 200) -> pd.DataFrame:
        if not self.enabled:
            return pd.DataFrame()
        # v1: daily only; intraday endpoints differ by plan.
        data = self._get(f"historical-price-full/{symbol}", {"timeseries": limit})
        if not data or "historical" not in data:
            return pd.DataFrame()
        hist = list(reversed(data["historical"]))  # API returns newest-first
        df = pd.DataFrame(hist)
        if df.empty:
            return df
        df = df.rename(columns={"date": "timestamp"})
        cols = ["open", "high", "low", "close", "volume", "timestamp"]
        df = df[[c for c in cols if c in df.columns]]
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%fZ")
        return df.tail(limit).reset_index(drop=True)

    def get_news(self, symbol: Optional[str] = None, limit: int = 10) -> list[NewsArticle]:
        if not self.enabled:
            return []
        params = {"limit": limit}
        if symbol:
            params["tickers"] = symbol
        data = self._get("stock_news", params)
        if not data:
            return []
        out: list[NewsArticle] = []
        for item in data[:limit]:
            out.append(NewsArticle(
                title=item.get("title", ""),
                source=item.get("site", "fmp"),
                url=item.get("url", ""),
                published_at=item.get("publishedDate", ""),
                summary=item.get("text", "")[:500],
                related_symbols=item.get("symbol", symbol or ""),
            ))
        return out
