"""Alpaca historical + latest-quote adapter (REST).

This is the *primary* source for daily bars and last-close prices, because it
works reliably from cloud hosts (Zeabur) using the user's existing Alpaca keys —
unlike yfinance (often blocked from datacenter IPs) and Finnhub (free-tier candle
endpoint discontinued).

Real-time intraday ticks still come from the IEX websocket (alpaca_iex_stream);
this module covers everything else: backfilling history and the previous-close
price shown when the market is closed.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import pandas as pd

from config.settings import settings
from data_adapters.base import HistoryAdapter, Quote, QuoteAdapter

logger = logging.getLogger(__name__)

_TF = {"1Day": "Day", "1day": "Day", "1Hour": "Hour", "15Min": "15Min",
       "5Min": "5Min", "1Min": "Min"}

# Alpaca uses a dot for share classes (BRK.B, BF.B); our DB / yfinance use a
# dash (BRK-B). Convert at the Alpaca boundary and map results back.
def _to_alpaca(sym: str) -> str:
    return sym.replace("-", ".")


def _from_alpaca(sym: str) -> str:
    return sym.replace(".", "-")


class AlpacaHistoryAdapter(HistoryAdapter, QuoteAdapter):
    name = "alpaca"

    def __init__(self) -> None:
        self._client = None
        if settings.alpaca_enabled:
            try:
                from alpaca.data.historical import StockHistoricalDataClient
                self._client = StockHistoricalDataClient(
                    settings.alpaca_api_key, settings.alpaca_secret_key)
            except Exception as exc:  # pragma: no cover
                logger.warning("Alpaca historical client init failed: %s", exc)

    @property
    def enabled(self) -> bool:
        return self._client is not None

    # ---- bars -------------------------------------------------------------
    def _timeframe(self, timeframe: str):
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        unit = _TF.get(timeframe, "Day")
        if unit == "Day":
            return TimeFrame.Day
        if unit == "Hour":
            return TimeFrame.Hour
        if unit == "Min":
            return TimeFrame.Minute
        if unit == "15Min":
            return TimeFrame(15, TimeFrameUnit.Minute)
        if unit == "5Min":
            return TimeFrame(5, TimeFrameUnit.Minute)
        return TimeFrame.Day

    def get_bars(self, symbol: str, timeframe: str = "1Day", limit: int = 200) -> pd.DataFrame:
        out = self.get_bars_batch([symbol], timeframe=timeframe, limit=limit)
        return out.get(symbol, pd.DataFrame())

    def get_bars_batch(self, symbols: list[str], timeframe: str = "1Day",
                       limit: int = 200) -> dict[str, pd.DataFrame]:
        """Fetch bars for many symbols in one request (oldest -> newest each).

        Resilient to bad tickers: Alpaca rejects the WHOLE request if any symbol
        is invalid (naming the offender in the error), so we drop named bad
        symbols and retry rather than losing the entire batch.
        """
        if not self.enabled or not symbols:
            return {}
        from datetime import datetime, timedelta, timezone
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.enums import DataFeed

        tf = self._timeframe(timeframe)
        days = int(limit * 1.6) + 10
        start = datetime.now(timezone.utc) - timedelta(days=days)

        # Map alpaca-format -> original so we can return the caller's symbols.
        alias = {_to_alpaca(s): s for s in symbols}
        pending = set(alias.keys())

        resp = None
        for _ in range(5):  # at most a few retries to peel off bad tickers
            if not pending:
                return {}
            req = StockBarsRequest(symbol_or_symbols=list(pending), timeframe=tf,
                                   start=start, feed=DataFeed.IEX)
            try:
                resp = self._client.get_stock_bars(req)
                break
            except Exception as exc:
                bad = re.findall(r"invalid symbol:\s*([A-Za-z0-9.\-]+)", str(exc))
                if bad:
                    for b in bad:
                        pending.discard(b)
                    logger.info("Alpaca: dropping invalid symbol(s) %s and retrying.", bad)
                    continue
                logger.warning("Alpaca get_stock_bars failed (%d symbols): %s",
                               len(pending), exc)
                return {}

        if resp is None:
            return {}
        df = resp.df
        if df is None or df.empty:
            return {}

        out: dict[str, pd.DataFrame] = {}
        if isinstance(df.index, pd.MultiIndex):
            for sym in df.index.get_level_values(0).unique():
                key = alias.get(sym, _from_alpaca(sym))
                sub = df.xs(sym, level=0)
                out[key] = self._shape(sub).tail(limit).reset_index(drop=True)
        else:
            only = next(iter(pending))
            out[alias.get(only, _from_alpaca(only))] = \
                self._shape(df).tail(limit).reset_index(drop=True)
        return out

    @staticmethod
    def _shape(sub: pd.DataFrame) -> pd.DataFrame:
        d = sub.reset_index().rename(columns={"timestamp": "timestamp"})
        d = d[["timestamp", "open", "high", "low", "close", "volume"]].copy()
        d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%fZ")
        return d

    # ---- latest price -----------------------------------------------------
    def get_quote(self, symbol: str) -> Optional[Quote]:
        """Latest trade price. During market hours this is live-ish; after close
        it returns the last trade of the session."""
        quotes = self.get_quotes_batch([symbol])
        return quotes.get(symbol)

    def get_quotes_batch(self, symbols: list[str]) -> dict[str, Quote]:
        """Latest trade prices for many symbols in one Alpaca request."""
        if not self.enabled or not symbols:
            return {}
        from alpaca.data.requests import StockLatestTradeRequest
        from alpaca.data.enums import DataFeed
        alias = {_to_alpaca(s): s for s in dict.fromkeys(symbols)}
        try:
            req = StockLatestTradeRequest(symbol_or_symbols=list(alias.keys()), feed=DataFeed.IEX)
            resp = self._client.get_stock_latest_trade(req)
            out: dict[str, Quote] = {}
            for asym, trade in resp.items():
                sym = alias.get(asym, _from_alpaca(asym))
                if trade and trade.price:
                    out[sym] = Quote(symbol=sym, price=float(trade.price), source=self.name)
            return out
        except Exception as exc:
            logger.debug("Alpaca latest trade batch failed for %d symbols: %s", len(symbols), exc)
        return {}
