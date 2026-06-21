"""Startup backfill — guarantees the dashboard has data from the first second.

For every tracked symbol it:
  1. fetches ~180 daily bars (Alpaca historical primary, yfinance fallback)
  2. writes them to `bars`
  3. computes indicators and writes a `technical_indicators` snapshot
  4. seeds `price_ticks` with the latest close so a price shows even when the
     market is closed (the live websocket overwrites this during market hours)

Run once at startup (see start.sh), then the resident workers keep it fresh.
Idempotent: re-running just refreshes the latest bars/indicators.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from data_adapters.alpaca_history import AlpacaHistoryAdapter  # noqa: E402
from data_adapters.yfinance_history import YFinanceAdapter  # noqa: E402
from db import database as db  # noqa: E402
from indicators import technical  # noqa: E402

BARS_LIMIT = 180


def _persist_bars(symbol: str, df: pd.DataFrame, source: str) -> None:
    for _, r in df.iterrows():
        db.upsert_bar(symbol, "1Day", open=float(r["open"]), high=float(r["high"]),
                      low=float(r["low"]), close=float(r["close"]),
                      volume=float(r["volume"]) if pd.notna(r["volume"]) else 0.0,
                      timestamp=str(r["timestamp"]), source=source)


def _persist_indicators(symbol: str, snap: dict) -> None:
    if not snap:
        return
    payload = {k: snap.get(k) for k in (
        "ma5", "ma10", "ma20", "ma60", "ma120", "rsi14", "macd", "macd_signal",
        "macd_hist", "bb_upper", "bb_middle", "bb_lower", "vwap", "volume_ratio",
        "distance_ma20_pct", "distance_ma60_pct")}
    payload.update({"symbol": symbol, "timeframe": "1Day", "timestamp": db.utcnow_iso()})
    db.insert("technical_indicators", payload)


def _seed_price(symbol: str, df: pd.DataFrame, source: str) -> None:
    if df.empty:
        return
    last_close = float(df["close"].iloc[-1])
    db.record_tick(symbol, price=last_close, source=f"{source}_close")


def run() -> None:
    db.init_db()
    symbols = db.all_tracked_symbols()
    if not symbols:
        print("[backfill] No tracked symbols; nothing to do.")
        return

    alpaca = AlpacaHistoryAdapter()
    yf = YFinanceAdapter()

    # 1) Try a single batched Alpaca request for everything (fast, cloud-safe).
    batched: dict[str, pd.DataFrame] = {}
    if alpaca.enabled:
        print(f"[backfill] Fetching {len(symbols)} symbols from Alpaca (batched)...")
        batched = alpaca.get_bars_batch(symbols, "1Day", limit=BARS_LIMIT)
        print(f"[backfill] Alpaca returned data for {len(batched)} symbols.")

    ok = 0
    missing: list[str] = []
    for sym in symbols:
        df = batched.get(sym)
        source = "alpaca"
        if df is None or df.empty:
            # 2) Per-symbol yfinance fallback.
            df = yf.get_bars(sym, "1Day", limit=BARS_LIMIT)
            source = "yfinance"
        if df is None or df.empty or len(df) < 20:
            missing.append(sym)
            continue
        try:
            _persist_bars(sym, df, source)
            snap = technical.compute_indicators(df)
            _persist_indicators(sym, snap)
            _seed_price(sym, df, source)
            ok += 1
        except Exception as exc:
            print(f"[backfill] {sym} failed: {exc}")
            missing.append(sym)

    print(f"[backfill] Done. populated={ok}, missing={len(missing)}")
    if missing:
        print(f"[backfill] No data for: {', '.join(missing[:30])}"
              + (" ..." if len(missing) > 30 else ""))


if __name__ == "__main__":
    run()
