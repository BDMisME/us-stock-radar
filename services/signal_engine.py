"""Signal Engine — rules layer that compresses market data into discrete events.

Severity routing (revised):
  • INFO    → status='new'  (displayed only, never triggers AI)
  • WARNING → status='new'  (displayed in Signals page, no AI call)
  • CRITICAL + holding (core/high_focus) → status='pending_ai'
  • CRITICAL + general watchlist → status='new'  (batched by scheduler at close)

This keeps AI calls focused on truly material events and avoids burning tokens
on routine fluctuations.
"""
from __future__ import annotations

import time
from typing import Any, Optional

import pandas as pd

from config.settings import settings
from data_adapters.yfinance_history import YFinanceAdapter
from db import database as db
from indicators import technical
from services._logsetup import setup

logger = setup("signal_engine")

CRITICAL = "critical"
WARNING  = "warning"
INFO     = "info"


def _load_bars_df(symbol: str, limit: int = 160) -> pd.DataFrame:
    rows = db.query(
        "SELECT open, high, low, close, volume, timestamp FROM bars "
        "WHERE symbol=? AND timeframe='1Day' ORDER BY timestamp ASC LIMIT 5000",
        (symbol,),
    )
    if rows and len(rows) >= 30:
        return pd.DataFrame(db.to_dicts(rows)).tail(limit).reset_index(drop=True)
    df = YFinanceAdapter().get_bars(symbol, "1Day", limit=limit)
    if not df.empty:
        for _, r in df.iterrows():
            db.upsert_bar(symbol, "1Day", open=float(r["open"]), high=float(r["high"]),
                          low=float(r["low"]), close=float(r["close"]),
                          volume=float(r["volume"]), timestamp=str(r["timestamp"]),
                          source="yfinance")
    return df


def _persist_indicators(symbol: str, snap: dict[str, Any]) -> None:
    if not snap:
        return
    payload = {k: snap.get(k) for k in (
        "ma5", "ma10", "ma20", "ma60", "ma120", "rsi14", "macd", "macd_signal",
        "macd_hist", "bb_upper", "bb_middle", "bb_lower", "vwap", "volume_ratio",
        "distance_ma20_pct", "distance_ma60_pct")}
    payload.update({"symbol": symbol, "timeframe": "1Day", "timestamp": db.utcnow_iso()})
    db.insert("technical_indicators", payload)


def _should_queue_ai(severity: str, holding: Optional[dict], watch: Optional[dict]) -> bool:
    """Only CRITICAL signals for core holdings and high_focus watchlist go to AI."""
    if severity != CRITICAL:
        return False
    if holding:
        return True  # all holdings (core / other) get AI on CRITICAL
    if watch:
        return watch.get("category") == "high_focus"
    return False


def _emit(symbol: str, signal_type: str, severity: str, title: str,
          description: str, price: Optional[float], snap: dict,
          holding: Optional[dict], watch: Optional[dict]) -> None:
    pending = _should_queue_ai(severity, holding, watch)
    db.create_signal(symbol, signal_type, severity=severity, title=title,
                     description=description, price=price,
                     indicator_snapshot=snap, pending_ai=pending)
    logger.info("[%s] %s (%s) -> %s", symbol, signal_type, severity,
                "AI" if pending else "logged")


def evaluate_symbol(symbol: str, holding: Optional[dict], watch: Optional[dict]) -> int:
    df = _load_bars_df(symbol)
    if df is None or df.empty or len(df) < 20:
        return 0

    snap = technical.compute_indicators(df)
    if not snap:
        return 0
    _persist_indicators(symbol, snap)

    closes = df["close"].astype(float).reset_index(drop=True)
    last = float(closes.iloc[-1])
    prev = float(closes.iloc[-2]) if len(closes) >= 2 else last
    count = 0

    def emit(stype, sev, title, desc):
        nonlocal count
        _emit(symbol, stype, sev, title, desc, last, snap, holding, watch)
        count += 1

    # ---- MA break / reclaim ----
    for ma_key, ma_label in (("ma20", "MA20"), ("ma60", "MA60")):
        ma = snap.get(ma_key)
        if ma:
            if prev >= ma > last:
                emit(f"break_below_{ma_key}", WARNING, f"跌破 {ma_label}",
                     f"{symbol} 收盤 {last:.2f} 跌破 {ma_label} {ma:.2f}")
            elif prev <= ma < last:
                emit(f"reclaim_{ma_key}", WARNING, f"站上 {ma_label}",
                     f"{symbol} 收盤 {last:.2f} 站上 {ma_label} {ma:.2f}")

    # ---- RSI extremes ----
    rsi = snap.get("rsi14")
    if rsi is not None:
        if rsi > 70:
            emit("rsi_overbought", WARNING, "RSI 超買", f"{symbol} RSI14={rsi:.1f} > 70")
        elif rsi < 30:
            emit("rsi_oversold", WARNING, "RSI 超賣", f"{symbol} RSI14={rsi:.1f} < 30")

    # ---- MACD cross ----
    cross = technical.macd_cross(df)
    if cross == "golden":
        emit("macd_golden_cross", WARNING, "MACD 黃金交叉", f"{symbol} MACD 由下而上穿越訊號線")
    elif cross == "death":
        emit("macd_death_cross", WARNING, "MACD 死亡交叉", f"{symbol} MACD 由上而下跌破訊號線")

    # ---- Volume surge ----
    vr = snap.get("volume_ratio")
    if vr is not None and vr >= 2.0:
        emit("volume_surge", WARNING, "放量", f"{symbol} 成交量為 20 日均量 {vr:.1f} 倍")

    # ---- Day change ----
    day_chg = (last - prev) / prev * 100 if prev else 0.0
    if day_chg > 5:
        emit("day_gain_gt5", WARNING, "單日大漲", f"{symbol} 今日 +{day_chg:.1f}%")
    elif day_chg < -5:
        emit("day_loss_gt5", CRITICAL, "單日大跌", f"{symbol} 今日 {day_chg:.1f}%")

    # ---- Holding-specific rules ----
    if holding:
        avg_cost = holding.get("avg_cost") or 0
        stop = holding.get("stop_loss")
        take = holding.get("take_profit")
        if stop and stop > 0 and last <= stop * 1.02:
            emit("near_stop_loss", CRITICAL, "接近停損",
                 f"{symbol} 現價 {last:.2f} 接近停損 {stop:.2f} (2% 內)")
        if take and take > 0 and last >= take * 0.98:
            emit("near_take_profit", WARNING, "接近停利",
                 f"{symbol} 現價 {last:.2f} 接近停利 {take:.2f} (2% 內)")
        if avg_cost > 0:
            pnl_pct = (last - avg_cost) / avg_cost * 100
            if pnl_pct <= -5:
                emit("below_cost_5pct", CRITICAL, "跌破成本 5%",
                     f"{symbol} 較成本 {avg_cost:.2f} 下跌 {pnl_pct:.1f}%")
            elif pnl_pct >= 10:
                emit("above_cost_10pct", INFO, "高於成本 10%",
                     f"{symbol} 較成本 {avg_cost:.2f} 上漲 {pnl_pct:.1f}%")

    # ---- High-focus watchlist entering target buy band ----
    if watch and watch.get("category") == "high_focus":
        low = watch.get("target_buy_low")
        high = watch.get("target_buy_high")
        if low and high and low <= last <= high:
            emit("entered_buy_zone", CRITICAL, "進入目標買區",
                 f"{symbol} 現價 {last:.2f} 進入目標買區 {low:.2f}~{high:.2f}")

    return count


def run_once() -> int:
    holdings = {h["symbol"]: h for h in db.active_holdings()}
    watch    = {w["symbol"]: w for w in db.active_watchlist()}
    symbols  = db.all_tracked_symbols()
    total = 0
    for sym in symbols:
        try:
            total += evaluate_symbol(sym, holdings.get(sym), watch.get(sym))
        except Exception as exc:
            logger.exception("evaluate_symbol failed for %s: %s", sym, exc)
    logger.info("Scan complete: %d symbols, %d signals emitted.", len(symbols), total)
    return total


def run_forever(interval_seconds: int = 300) -> None:
    logger.info("Signal engine starting (interval=%ss).", interval_seconds)
    while True:
        try:
            run_once()
        except Exception as exc:
            logger.exception("Scan failed: %s", exc)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    db.init_db()
    run_forever(interval_seconds=settings.watchlist_poll_seconds * 2 or 300)
