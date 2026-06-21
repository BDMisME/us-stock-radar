"""Finnhub adapter — quotes, daily candles, and company news.

Used to poll the 70-name general watchlist (alongside FMP/yfinance) and to
fetch news. Rate-limited to respect the free tier (~60 calls/min → we space
calls ~1.2s apart by default).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from config.settings import settings
from data_adapters._ratelimit import RateLimiter
from data_adapters.base import HistoryAdapter, NewsAdapter, NewsArticle, Quote, QuoteAdapter

logger = logging.getLogger(__name__)
_limiter = RateLimiter(min_interval_seconds=1.2)

_RESOLUTION = {"1Day": "D", "1day": "D", "1Hour": "60", "15Min": "15", "5Min": "5", "1Min": "1"}


class FinnhubAdapter(QuoteAdapter, HistoryAdapter, NewsAdapter):
    name = "finnhub"

    def __init__(self) -> None:
        self._client = None
        if settings.finnhub_enabled:
            try:
                import finnhub
                self._client = finnhub.Client(api_key=settings.finnhub_api_key)
            except Exception as exc:  # pragma: no cover
                logger.warning("finnhub client init failed: %s", exc)

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def get_quote(self, symbol: str) -> Optional[Quote]:
        if not self.enabled:
            return None
        _limiter.wait()
        try:
            q = self._client.quote(symbol)
        except Exception as exc:
            logger.warning("finnhub quote failed for %s: %s", symbol, exc)
            return None
        price = q.get("c")  # current price
        if not price:
            return None
        return Quote(symbol=symbol, price=float(price), source=self.name)

    def get_bars(self, symbol: str, timeframe: str = "1Day", limit: int = 200) -> pd.DataFrame:
        if not self.enabled:
            return pd.DataFrame()
        _limiter.wait()
        resolution = _RESOLUTION.get(timeframe, "D")
        now = int(time.time())
        # crude lookback window; daily bars need ~limit*1.5 calendar days
        lookback = now - int(limit * 1.7 * 86400)
        try:
            data = self._client.stock_candles(symbol, resolution, lookback, now)
        except Exception as exc:
            logger.warning("finnhub candles failed for %s: %s", symbol, exc)
            return pd.DataFrame()
        if not data or data.get("s") != "ok":
            return pd.DataFrame()
        df = pd.DataFrame({
            "open": data["o"], "high": data["h"], "low": data["l"],
            "close": data["c"], "volume": data["v"],
            "timestamp": [datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
                          for t in data["t"]],
        })
        return df.tail(limit).reset_index(drop=True)

    def get_news(self, symbol: Optional[str] = None, limit: int = 10) -> list[NewsArticle]:
        if not self.enabled:
            return []
        _limiter.wait()
        try:
            if symbol:
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                week_ago = (datetime.now(timezone.utc).timestamp() - 7 * 86400)
                from_str = datetime.fromtimestamp(week_ago, tz=timezone.utc).strftime("%Y-%m-%d")
                raw = self._client.company_news(symbol, _from=from_str, to=today)
            else:
                raw = self._client.general_news("general")
        except Exception as exc:
            logger.warning("finnhub news failed for %s: %s", symbol, exc)
            return []

        out: list[NewsArticle] = []
        for item in (raw or [])[:limit]:
            ts = item.get("datetime", 0)
            published = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ") if ts else ""
            out.append(NewsArticle(
                title=item.get("headline", ""),
                source=item.get("source", "finnhub"),
                url=item.get("url", ""),
                published_at=published,
                summary=item.get("summary", ""),
                related_symbols=symbol or "",
            ))
        return out
