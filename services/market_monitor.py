"""Market Monitor — orchestrates all market-data ingestion.

Two concurrent jobs:
  1. Real-time: the Alpaca IEX websocket for the 30 holdings + high-focus names
     (runs in a background thread).
  2. Fast polling: every tracked symbol (holdings + watchlist) is polled every
     WATCHLIST_POLL_SECONDS, with a hard floor of 5 seconds, through the provider
     chain Alpaca -> Finnhub -> FMP -> yfinance.

All quotes land in price_ticks with an explicit source tag.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from config.settings import settings
from data_adapters.alpaca_history import AlpacaHistoryAdapter
from data_adapters.alpaca_iex_stream import AlpacaIEXStream
from data_adapters.finnhub_client import FinnhubAdapter
from data_adapters.fmp_client import FMPAdapter
from data_adapters.yfinance_history import YFinanceAdapter
from db import database as db
from services._logsetup import setup

logger = setup("market_monitor")


class QuoteRouter:
    """Tries quote providers in order until one returns a price.

    Alpaca is primary (the user's real-time source; its latest-trade endpoint
    returns the last session price even after close). Finnhub/FMP/yfinance are
    fallbacks for names without Alpaca coverage or when Alpaca is unconfigured.
    """

    def __init__(self) -> None:
        self.alpaca = AlpacaHistoryAdapter()
        self.finnhub = FinnhubAdapter()
        self.fmp = FMPAdapter()
        self.yf = YFinanceAdapter()

    def quote(self, symbol: str):
        for adapter in (self.alpaca, self.finnhub, self.fmp, self.yf):
            try:
                if isinstance(adapter, (AlpacaHistoryAdapter, FinnhubAdapter, FMPAdapter)) \
                        and not adapter.enabled:
                    continue
                q = adapter.get_quote(symbol)
                if q and q.price:
                    return q
            except Exception as exc:
                logger.debug("quote provider %s failed for %s: %s", adapter.name, symbol, exc)
        return None

    def quotes(self, symbols: list[str]) -> dict[str, object]:
        """Fetch quotes for many symbols while minimizing API requests."""
        symbols = list(dict.fromkeys(symbols))
        out: dict[str, object] = {}
        if not symbols:
            return out

        if self.alpaca.enabled:
            out.update(self.alpaca.get_quotes_batch(symbols))

        # Fall back per missing symbol only. These providers are rate-limited
        # more tightly, so they should not be the primary path for 5-second
        # polling across a full watchlist.
        for sym in [s for s in symbols if s not in out]:
            q = None
            for adapter in (self.finnhub, self.fmp, self.yf):
                try:
                    if isinstance(adapter, (FinnhubAdapter, FMPAdapter)) and not adapter.enabled:
                        continue
                    q = adapter.get_quote(sym)
                    if q and q.price:
                        break
                except Exception as exc:
                    logger.debug("quote provider %s failed for %s: %s", adapter.name, sym, exc)
            if q and q.price:
                out[sym] = q
        return out



def poll_symbols(router: QuoteRouter, symbols: list[str]) -> int:
    written = 0
    for sym, q in router.quotes(symbols).items():
        if q and q.price:
            db.record_tick(sym, price=q.price, bid=q.bid, ask=q.ask,
                           volume=q.volume, source=q.source)
            written += 1
    return written


def poll_interval_seconds() -> int:
    """Fast quote polling floor for holdings + watchlist."""
    return max(settings.watchlist_poll_seconds, 5)


def run_forever() -> None:
    """Source-of-truth strategy (Alpaca-first):

      • realtime names (holdings + high_focus, ≤30): Alpaca IEX websocket for
        live ticks during market hours.
      • all tracked names: also polled every 5 seconds by default so holdings
        and the whole watchlist keep moving even outside websocket coverage.
      • EVERY tracked symbol additionally gets a periodic last-close refresh via
        Alpaca historical, so prices stay correct even when the market is closed
        (previous session close) — no mixing of "realtime" and "poll" sets.
    """
    db.init_db()
    realtime = db.realtime_symbols(limit=30)

    stream: Optional[AlpacaIEXStream] = None
    if settings.alpaca_enabled and realtime:
        stream = AlpacaIEXStream(realtime)
        t = threading.Thread(target=stream.run_forever, name="alpaca-iex", daemon=True)
        t.start()
        logger.info("Alpaca IEX stream thread started for %d symbols.", len(realtime))

    router = QuoteRouter()
    hist = AlpacaHistoryAdapter()
    known_realtime: set[str] = set(realtime)

    interval = poll_interval_seconds()
    last_prune = 0.0
    logger.info("Market monitor running. realtime=%d (alpaca_ws=%s) interval=%ss",
                len(realtime), bool(stream), interval)

    while True:
        try:
            # Keep the websocket subscription in sync with the DB.
            current_realtime = set(db.realtime_symbols(limit=30))
            if stream is not None:
                new_syms = list(current_realtime - known_realtime)
                if new_syms:
                    added = stream.add_symbols(new_syms)
                    known_realtime.update(added)

            # Poll every tracked symbol at the fast interval. The websocket is
            # still faster for subscribed names, but this gives all holdings and
            # watchlist names a 5-second fallback/update path.
            tracked = db.all_tracked_symbols()
            n = poll_symbols(router, tracked)

            # Periodically refresh daily bars for every tracked symbol. We update
            # BARS (not ticks): latest_price() uses live ticks when present and
            # falls back to the latest bar close otherwise — so this keeps prices
            # correct after hours without ever clobbering live websocket ticks.
            if hist.enabled:
                _refresh_bars(hist, db.all_tracked_symbols())

            now = time.time()
            if now - last_prune >= 300:
                pruned = db.prune_price_ticks(older_than_hours=72)
                last_prune = now
                if pruned:
                    logger.info("Pruned %d stale price ticks.", pruned)

            logger.info("Polled tracked=%d/%d, realtime_ws=%d.",
                        n, len(tracked), len(current_realtime))
        except Exception as exc:
            logger.exception("Polling error: %s", exc)
        time.sleep(interval)


def _refresh_bars(hist: AlpacaHistoryAdapter, symbols: list[str]) -> None:
    """Upsert the most recent daily bars for all tracked symbols (batched)."""
    if not symbols:
        return
    try:
        batched = hist.get_bars_batch(symbols, "1Day", limit=3)
    except Exception as exc:
        logger.debug("bar refresh failed: %s", exc)
        return
    for sym, df in batched.items():
        if df is None or df.empty:
            continue
        for _, r in df.iterrows():
            try:
                db.upsert_bar(sym, "1Day", open=float(r["open"]), high=float(r["high"]),
                              low=float(r["low"]), close=float(r["close"]),
                              volume=float(r["volume"]) if r["volume"] == r["volume"] else 0.0,
                              timestamp=str(r["timestamp"]), source="alpaca")
            except Exception:
                pass


if __name__ == "__main__":
    run_forever()
