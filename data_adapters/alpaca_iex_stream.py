"""Alpaca IEX real-time websocket stream.

Subscribes to up to 30 symbols (all holdings + high-focus watchlist) on the
free IEX feed, writes trades/quotes/bars into SQLite, keeps an in-memory cache
of the latest price per symbol, and auto-reconnects on disconnect.

This is the *only* real-time source. The general 70-name watchlist is polled
separately (see market_monitor). LLMs never read raw ticks — the signal engine
compresses them into events first.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Optional

from config.settings import settings
from db import database as db

logger = logging.getLogger(__name__)

# Process-local cache of the most recent price per symbol.
_price_cache: dict[str, float] = {}
_cache_lock = threading.Lock()


def latest_cached_price(symbol: str) -> Optional[float]:
    with _cache_lock:
        return _price_cache.get(symbol)


def _set_cache(symbol: str, price: float) -> None:
    with _cache_lock:
        _price_cache[symbol] = price


class AlpacaIEXStream:
    """Wraps alpaca-py StockDataStream with reconnect + persistence.

    Dynamic subscriptions: call add_symbols(new_syms) at any time while running.
    The method is thread-safe; it deduplicates against the already-subscribed set.
    """

    def __init__(self, symbols: list[str]) -> None:
        self.symbols: list[str] = list(dict.fromkeys(symbols))[:30]  # deduped, cap 30
        self._stream = None
        self._subscribed: set[str] = set()
        self._lock = threading.Lock()

    # ---- handlers ---------------------------------------------------------
    async def _on_trade(self, trade) -> None:
        try:
            price = float(trade.price)
            _set_cache(trade.symbol, price)
            db.record_tick(trade.symbol, price=price,
                           volume=float(getattr(trade, "size", 0) or 0), source="alpaca")
        except Exception as exc:  # never let one bad message kill the stream
            logger.warning("trade handler error: %s", exc)

    async def _on_quote(self, q) -> None:
        try:
            bid = float(getattr(q, "bid_price", 0) or 0) or None
            ask = float(getattr(q, "ask_price", 0) or 0) or None
            mid = (bid + ask) / 2 if (bid and ask) else (bid or ask)
            if mid:
                _set_cache(q.symbol, mid)
            db.record_tick(q.symbol, price=mid, bid=bid, ask=ask, source="alpaca")
        except Exception as exc:
            logger.warning("quote handler error: %s", exc)

    async def _on_bar(self, bar) -> None:
        try:
            ts = bar.timestamp.strftime("%Y-%m-%dT%H:%M:%fZ") if hasattr(bar.timestamp, "strftime") else str(bar.timestamp)
            db.upsert_bar(bar.symbol, "1Min", open=float(bar.open), high=float(bar.high),
                          low=float(bar.low), close=float(bar.close),
                          volume=float(bar.volume), timestamp=ts, source="alpaca")
            _set_cache(bar.symbol, float(bar.close))
        except Exception as exc:
            logger.warning("bar handler error: %s", exc)

    # ---- dynamic subscription ------------------------------------------------
    def add_symbols(self, new_syms: list[str]) -> list[str]:
        """Subscribe to additional symbols on the already-running stream.

        Returns the list of symbols actually added (skips dupes / cap).
        Safe to call from any thread while the stream is running.
        """
        with self._lock:
            cap_room = 30 - len(self._subscribed)
            added = [s for s in new_syms if s not in self._subscribed][:cap_room]
            if not added:
                return []
            if self._stream is not None:
                try:
                    self._stream.subscribe_trades(self._on_trade, *added)
                    self._stream.subscribe_quotes(self._on_quote, *added)
                    self._stream.subscribe_bars(self._on_bar, *added)
                    self._subscribed.update(added)
                    self.symbols = list(self._subscribed)
                    logger.info("Dynamically subscribed to %d new symbols: %s",
                                len(added), ", ".join(added))
                except Exception as exc:
                    logger.error("Dynamic subscribe failed: %s", exc)
                    added = []
        return added

    # ---- run loop ---------------------------------------------------------
    def _build_stream(self):
        from alpaca.data.live import StockDataStream
        from alpaca.data.enums import DataFeed

        stream = StockDataStream(
            settings.alpaca_api_key,
            settings.alpaca_secret_key,
            feed=DataFeed.IEX,
        )
        if self.symbols:
            stream.subscribe_trades(self._on_trade, *self.symbols)
            stream.subscribe_quotes(self._on_quote, *self.symbols)
            stream.subscribe_bars(self._on_bar, *self.symbols)
        with self._lock:
            self._subscribed = set(self.symbols)
        return stream

    def run_forever(self) -> None:
        """Blocking entrypoint with reconnect/backoff. Call from a process."""
        if not settings.alpaca_enabled:
            logger.error("Alpaca keys not configured; stream cannot start.")
            return
        if not self.symbols:
            logger.warning("No symbols to subscribe; stream idle.")
            return

        backoff = 2
        while True:
            try:
                logger.info("Connecting Alpaca IEX stream for %d symbols: %s",
                            len(self.symbols), ", ".join(self.symbols))
                self._stream = self._build_stream()
                # StockDataStream.run() manages its own asyncio loop and blocks.
                self._stream.run()
                backoff = 2  # clean exit -> reset backoff
            except KeyboardInterrupt:
                logger.info("Stream interrupted by user; shutting down.")
                break
            except Exception as exc:
                logger.error("Stream error: %s — reconnecting in %ss", exc, backoff)
                try:
                    if self._stream is not None:
                        self._stream.stop()
                except Exception:
                    pass
                import time
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
