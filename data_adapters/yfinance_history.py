"""yfinance adapter — historical bars and a best-effort fallback quote.

yfinance is treated strictly as *history + fallback*, never as a primary
real-time feed (per project constraints). Quotes here are delayed and clearly
tagged with source="yfinance".
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from data_adapters.base import HistoryAdapter, Quote, QuoteAdapter

logger = logging.getLogger(__name__)

# Map our timeframe vocabulary to yfinance interval strings.
_INTERVAL = {
    "1Day": "1d", "1day": "1d", "1d": "1d",
    "1Hour": "1h", "1hour": "1h", "1h": "1h",
    "15Min": "15m", "5Min": "5m", "1Min": "1m",
}


def _period_for(limit: int, interval: str) -> str:
    if interval in ("1m", "5m", "15m"):
        return "5d" if limit <= 200 else "1mo"
    days = max(limit + 10, 30)
    if days <= 30:
        return "1mo"
    if days <= 90:
        return "3mo"
    if days <= 180:
        return "6mo"
    if days <= 365:
        return "1y"
    return "2y"


class YFinanceAdapter(HistoryAdapter, QuoteAdapter):
    name = "yfinance"

    def get_bars(self, symbol: str, timeframe: str = "1Day", limit: int = 200) -> pd.DataFrame:
        try:
            import yfinance as yf
        except Exception as exc:  # pragma: no cover
            logger.warning("yfinance not installed: %s", exc)
            return pd.DataFrame()

        interval = _INTERVAL.get(timeframe, "1d")
        period = _period_for(limit, interval)
        try:
            raw = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
        except Exception as exc:
            logger.warning("yfinance history failed for %s: %s", symbol, exc)
            return pd.DataFrame()

        if raw is None or raw.empty:
            return pd.DataFrame()

        df = raw.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })[["open", "high", "low", "close", "volume"]].copy()
        df.index.name = "timestamp"
        df = df.reset_index()
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%fZ")
        return df.tail(limit).reset_index(drop=True)

    def get_quote(self, symbol: str) -> Optional[Quote]:
        df = self.get_bars(symbol, "1Day", limit=2)
        if df.empty:
            return None
        last = df.iloc[-1]
        return Quote(
            symbol=symbol,
            price=float(last["close"]),
            volume=float(last["volume"]) if pd.notna(last["volume"]) else None,
            source=self.name,
        )
