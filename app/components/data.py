"""Read-side helpers for the Streamlit dashboard.

These wrap the database into pandas DataFrames shaped for display. They are
deliberately read-only (the Settings page handles writes) and tolerate empty
tables so the UI renders cleanly on a fresh install.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import streamlit as st

from db import database as db


def _df(rows) -> pd.DataFrame:
    return pd.DataFrame(db.to_dicts(rows))


@st.cache_data(ttl=5, show_spinner=False)
def _cached_rows(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return db.to_dicts(db.query(sql, params))


CATEGORY_LABELS = {
    # Current values
    "long_term": "長期",
    "swing":     "短線",
    # Watchlist
    "high_focus": "高關注",
    "general":    "一般觀察",
    # Legacy holding values (backward compat)
    "core": "長期",
}
SEVERITY_LABELS = {"info": "一般", "warning": "注意", "critical": "重要"}
STATUS_LABELS = {"new": "已記錄", "pending_ai": "待 AI 分析",
                 "analyzed": "已分析", "ignored": "冷卻略過"}
RISK_LABELS = {"low": "低", "medium": "中", "high": "高"}
ACTION_LABELS = {"hold": "續抱", "buy_watch": "觀察買點", "add": "加碼",
                 "trim": "減碼", "sell": "賣出", "wait": "等待"}


def category_label(cat: Optional[str]) -> str:
    return CATEGORY_LABELS.get(cat or "", cat or "—")


def _map_col(df: pd.DataFrame, col: str, mapping: dict) -> None:
    if col in df.columns:
        df[col] = df[col].map(lambda v: mapping.get(v, v))


def day_change_pct(symbol: str) -> Optional[float]:
    """Latest daily close vs the prior close, in percent. None if <2 bars."""
    rows = db.query(
        "SELECT close FROM bars WHERE symbol=? AND timeframe='1Day' AND close IS NOT NULL "
        "ORDER BY timestamp DESC LIMIT 2", (symbol,))
    if len(rows) < 2:
        return None
    last, prev = rows[0]["close"], rows[1]["close"]
    if not prev:
        return None
    return round((last - prev) / prev * 100, 2)


def latest_indicator_row(symbol: str) -> dict[str, Any]:
    row = db.query_one(
        "SELECT * FROM technical_indicators WHERE symbol=? ORDER BY timestamp DESC LIMIT 1",
        (symbol,),
    )
    return dict(row) if row else {}


def latest_ai_row(symbol: str) -> dict[str, Any]:
    row = db.query_one(
        "SELECT * FROM ai_analysis_logs WHERE symbol=? ORDER BY created_at DESC LIMIT 1",
        (symbol,),
    )
    return dict(row) if row else {}


def latest_signal_row(symbol: str) -> dict[str, Any]:
    row = db.query_one(
        "SELECT * FROM signals WHERE symbol=? ORDER BY created_at DESC LIMIT 1", (symbol,),
    )
    return dict(row) if row else {}


def _placeholders(values: list[str]) -> str:
    return ",".join("?" for _ in values)


def _latest_prices(symbols: list[str]) -> dict[str, Optional[float]]:
    if not symbols:
        return {}
    ph = _placeholders(symbols)
    tick_rows = _cached_rows(
        f"""
        SELECT pt.symbol, pt.price
        FROM price_ticks pt
        JOIN (
          SELECT symbol, MAX(timestamp) ts
          FROM price_ticks
          WHERE price IS NOT NULL AND symbol IN ({ph})
          GROUP BY symbol
        ) latest ON latest.symbol=pt.symbol AND latest.ts=pt.timestamp
        """,
        tuple(symbols),
    )
    out = {r["symbol"]: r["price"] for r in tick_rows if r.get("price") is not None}
    missing = [s for s in symbols if s not in out]
    if missing:
        ph2 = _placeholders(missing)
        bar_rows = _cached_rows(
            f"""
            SELECT b.symbol, b.close
            FROM bars b
            JOIN (
              SELECT symbol, MAX(timestamp) ts
              FROM bars
              WHERE timeframe='1Day' AND close IS NOT NULL AND symbol IN ({ph2})
              GROUP BY symbol
            ) latest ON latest.symbol=b.symbol AND latest.ts=b.timestamp
            WHERE b.timeframe='1Day'
            """,
            tuple(missing),
        )
        out.update({r["symbol"]: r["close"] for r in bar_rows if r.get("close") is not None})
    return out


def _day_changes(symbols: list[str]) -> dict[str, Optional[float]]:
    out: dict[str, Optional[float]] = {}
    if not symbols:
        return out
    ph = _placeholders(symbols)
    rows = _cached_rows(
        f"""
        SELECT symbol, close
        FROM (
          SELECT symbol, close,
                 ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY timestamp DESC) rn
          FROM bars
          WHERE timeframe='1Day' AND close IS NOT NULL AND symbol IN ({ph})
        )
        WHERE rn <= 2
        ORDER BY symbol, rn
        """,
        tuple(symbols),
    )
    by_symbol: dict[str, list[float]] = {}
    for r in rows:
        vals = by_symbol.setdefault(r["symbol"], [])
        if len(vals) < 2:
            vals.append(r["close"])
    for sym, closes in by_symbol.items():
        if len(closes) >= 2 and closes[1]:
            out[sym] = round((closes[0] - closes[1]) / closes[1] * 100, 2)
        else:
            out[sym] = None
    return out


def _latest_by_symbol(table: str, symbols: list[str], ts_col: str) -> dict[str, dict[str, Any]]:
    if not symbols:
        return {}
    ph = _placeholders(symbols)
    rows = _cached_rows(
        f"""
        SELECT t.*
        FROM {table} t
        JOIN (
          SELECT symbol, MAX({ts_col}) ts
          FROM {table}
          WHERE symbol IN ({ph})
          GROUP BY symbol
        ) latest ON latest.symbol=t.symbol AND latest.ts=t.{ts_col}
        """,
        tuple(symbols),
    )
    return {r["symbol"]: r for r in rows}


# Column orderings (Chinese headers) used by the views.
PORTFOLIO_COLS = ["代號", "群組", "類型", "股數", "均價", "現價", "漲跌%", "市值",
                  "未實現損益", "損益%", "MA20", "MA60", "RSI", "AI建議", "風險"]
WATCHLIST_COLS = ["代號", "群組", "分類", "主題", "關注度", "現價", "漲跌%",
                  "量比", "距MA20%", "距MA60%", "買區狀態", "最新訊號", "AI建議"]


def _holding_type_label(category: Optional[str]) -> str:
    """Map holding category to short Chinese label."""
    if category == "swing":
        return "短線"
    return "長期"  # long_term + legacy core/high_focus + None


def portfolio_table() -> pd.DataFrame:
    holdings = db.active_holdings()
    symbols = [h["symbol"] for h in holdings]
    prices = _latest_prices(symbols)
    changes = _day_changes(symbols)
    indicators = _latest_by_symbol("technical_indicators", symbols, "timestamp")
    ai_rows = _latest_by_symbol("ai_analysis_logs", symbols, "created_at")
    rows: list[dict[str, Any]] = []
    for h in holdings:
        sym = h["symbol"]
        price = prices.get(sym)
        ind = indicators.get(sym, {})
        ai = ai_rows.get(sym, {})
        shares = h.get("shares") or 0
        avg_cost = h.get("avg_cost") or 0
        mkt_val = (price or 0) * shares
        pnl = (price - avg_cost) * shares if price else None
        pnl_pct = ((price - avg_cost) / avg_cost * 100) if (price and avg_cost) else None
        rsi_raw = ind.get("rsi14")
        rows.append({
            "代號": sym,
            "群組": h.get("group_name") or "未分組",
            "類型": _holding_type_label(h.get("category")),
            "股數": shares, "均價": avg_cost,
            "現價": price, "漲跌%": changes.get(sym),
            "市值": round(mkt_val, 2) if mkt_val else None,
            "未實現損益": round(pnl, 2) if pnl is not None else None,
            "損益%": round(pnl_pct, 2) if pnl_pct is not None else None,
            "MA20": ind.get("ma20"), "MA60": ind.get("ma60"),
            "RSI": round(rsi_raw, 1) if rsi_raw is not None else None,
            "AI建議": ai.get("recommendation") or "—",
            "風險": RISK_LABELS.get(ai.get("risk_level"), ai.get("risk_level")) or "—",
        })
    df = pd.DataFrame(rows)
    return df[PORTFOLIO_COLS] if not df.empty else df


def portfolio_totals(df: pd.DataFrame) -> dict[str, float]:
    if df.empty:
        return {"market_value": 0.0, "unrealized_pnl": 0.0, "unrealized_pnl_pct": 0.0}
    mv = float(df["市值"].fillna(0).sum())
    pnl = float(df["未實現損益"].fillna(0).sum())
    cost = mv - pnl
    return {
        "market_value": round(mv, 2),
        "unrealized_pnl": round(pnl, 2),
        "unrealized_pnl_pct": round(pnl / cost * 100, 2) if cost else 0.0,
    }


def _buy_zone_status(price: Optional[float], low: Optional[float], high: Optional[float]) -> str:
    """Describe where current price sits relative to the target buy zone."""
    if not low and not high:
        return "—"
    if price is None:
        return "—"
    if low and high:
        if low <= price <= high:
            return "✓ 在買區"
        if price < low:
            pct = (low - price) / price * 100
            return f"↓ 低 {pct:.1f}%"
        pct = (price - high) / high * 100
        return f"↑ 高 {pct:.1f}%"
    if low and price < low:
        return f"↓ 低 {(low - price) / price * 100:.1f}%"
    if high and price > high:
        return f"↑ 高 {(price - high) / high * 100:.1f}%"
    return "✓ 在買區"


def watchlist_table(category: Optional[str] = None) -> pd.DataFrame:
    watch = db.active_watchlist(category)
    symbols = [w["symbol"] for w in watch]
    prices = _latest_prices(symbols)
    changes = _day_changes(symbols)
    indicators = _latest_by_symbol("technical_indicators", symbols, "timestamp")
    ai_rows = _latest_by_symbol("ai_analysis_logs", symbols, "created_at")
    signal_rows = _latest_by_symbol("signals", symbols, "created_at")
    rows: list[dict[str, Any]] = []
    for w in watch:
        sym = w["symbol"]
        ind = indicators.get(sym, {})
        ai = ai_rows.get(sym, {})
        sig = signal_rows.get(sym, {})
        price = prices.get(sym)
        rows.append({
            "代號": sym, "分類": category_label(w.get("category")),
            "群組": w.get("group_name") or "未分組",
            "主題": w.get("theme_tags"), "關注度": w.get("watch_level"),
            "現價": price, "漲跌%": changes.get(sym),
            "量比": ind.get("volume_ratio"),
            "距MA20%": ind.get("distance_ma20_pct"),
            "距MA60%": ind.get("distance_ma60_pct"),
            "買區狀態": _buy_zone_status(price, w.get("target_buy_low"), w.get("target_buy_high")),
            "最新訊號": sig.get("signal_type") or "—",
            "AI建議": ai.get("recommendation") or "—",
        })
    df = pd.DataFrame(rows)
    return df[WATCHLIST_COLS] if not df.empty else df


def signals_table(limit: int = 200, localize: bool = True) -> pd.DataFrame:
    df = _df(db.query(
        "SELECT symbol, signal_type, severity, title, description, price, status, created_at "
        "FROM signals ORDER BY created_at DESC LIMIT ?", (limit,)))
    if df.empty or not localize:
        return df
    _map_col(df, "severity", SEVERITY_LABELS)
    _map_col(df, "status", STATUS_LABELS)
    return df.rename(columns={
        "symbol": "代號", "signal_type": "類型", "severity": "嚴重度",
        "title": "事件", "description": "說明", "price": "價格",
        "status": "AI狀態", "created_at": "時間",
    })


def ai_table(limit: int = 200, localize: bool = True) -> pd.DataFrame:
    df = _df(db.query(
        "SELECT symbol, recommendation, action, risk_level, analysis_type, summary, "
        "invalidation_condition, next_watch_price, model, created_at "
        "FROM ai_analysis_logs ORDER BY created_at DESC LIMIT ?", (limit,)))
    if df.empty or not localize:
        return df
    _map_col(df, "action", ACTION_LABELS)
    _map_col(df, "risk_level", RISK_LABELS)
    return df.rename(columns={
        "symbol": "代號", "recommendation": "建議", "action": "動作",
        "risk_level": "風險", "analysis_type": "類型", "summary": "摘要",
        "invalidation_condition": "失效條件", "next_watch_price": "觀察價",
        "model": "模型", "created_at": "時間",
    })


def news_table(limit: int = 50) -> pd.DataFrame:
    return _df(db.query(
        "SELECT title, source, url, published_at, summary, related_symbols, "
        "sentiment, impact_level FROM news_items ORDER BY published_at DESC, created_at DESC LIMIT ?",
        (limit,)))


def bars_df(symbol: str, timeframe: str = "1Day", limit: int = 180) -> pd.DataFrame:
    rows = db.query(
        "SELECT open, high, low, close, volume, timestamp FROM bars "
        "WHERE symbol=? AND timeframe=? ORDER BY timestamp ASC LIMIT 5000",
        (symbol, timeframe))
    df = _df(rows)
    return df.tail(limit).reset_index(drop=True) if not df.empty else df


def _tick_candles(symbol: str, limit: int = 390) -> pd.DataFrame:
    """Compress raw realtime ticks into 1-minute candles as a fallback."""
    rows = db.query(
        "SELECT price, volume, timestamp FROM price_ticks "
        "WHERE symbol=? AND price IS NOT NULL ORDER BY timestamp ASC LIMIT 5000",
        (symbol,),
    )
    ticks = _df(rows)
    if ticks.empty:
        return ticks
    ticks["timestamp"] = pd.to_datetime(ticks["timestamp"], errors="coerce", utc=True)
    ticks["price"] = pd.to_numeric(ticks["price"], errors="coerce")
    ticks["volume"] = pd.to_numeric(ticks.get("volume", 0), errors="coerce").fillna(0)
    ticks = ticks.dropna(subset=["timestamp", "price"])
    if ticks.empty:
        return pd.DataFrame()
    grouped = ticks.set_index("timestamp").resample("1min")
    out = grouped["price"].ohlc()
    out["volume"] = grouped["volume"].sum()
    out = out.dropna(subset=["open", "high", "low", "close"]).reset_index()
    out["timestamp"] = out["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%fZ")
    return out.tail(limit).reset_index(drop=True)


RANGE_OPTIONS = ["即時", "3天", "7天", "1個月", "3個月", "6個月", "1年"]


def chart_bars(symbol: str, range_label: str) -> tuple[pd.DataFrame, str]:
    """Return the best available bars for a UI range and a short source note."""
    range_label = range_label if range_label in RANGE_OPTIONS else "3個月"
    if range_label == "即時":
        df = bars_df(symbol, "1Min", 390)
        if not df.empty:
            return df, "即時 1 分 K（Alpaca IEX）"
        df = _tick_candles(symbol, 390)
        if not df.empty:
            return df, "即時 tick 合成 1 分 K"
        return bars_df(symbol, "1Day", 2), "尚無即時 K，暫以最近日 K 顯示"

    if range_label == "3天":
        df = bars_df(symbol, "1Min", 3 * 390)
        if not df.empty:
            return df, "近 3 天 1 分 K"
        return bars_df(symbol, "1Day", 5), "尚無分鐘 K，暫以日 K 顯示"

    if range_label == "7天":
        df = bars_df(symbol, "1Hour", 7 * 8)
        if not df.empty:
            return df, "近 7 天 1 小時 K"
        df = bars_df(symbol, "1Min", 7 * 390)
        if not df.empty:
            return df, "近 7 天 1 分 K"
        return bars_df(symbol, "1Day", 10), "尚無小時/分鐘 K，暫以日 K 顯示"

    day_limits = {"1個月": 23, "3個月": 66, "6個月": 132, "1年": 252}
    return bars_df(symbol, "1Day", day_limits[range_label]), f"{range_label}日 K"


def risk_tasks(limit: int = 8) -> pd.DataFrame:
    """Action-oriented risk queue for the overview page."""
    rows = db.query(
        "SELECT symbol, severity, title, status, created_at FROM signals "
        "WHERE severity IN ('critical','warning') "
        "ORDER BY CASE severity WHEN 'critical' THEN 0 ELSE 1 END, created_at DESC "
        "LIMIT ?",
        (limit,),
    )
    df = _df(rows)
    if df.empty:
        return df
    _map_col(df, "severity", SEVERITY_LABELS)
    _map_col(df, "status", STATUS_LABELS)
    return df.rename(columns={
        "symbol": "代號", "severity": "嚴重度", "title": "待辦",
        "status": "狀態", "created_at": "時間",
    })


def symbol_timeline(symbol: str, limit: int = 20) -> pd.DataFrame:
    """Merge signals, news, and AI records into one symbol timeline."""
    rows: list[dict[str, Any]] = []
    for r in db.query(
        "SELECT created_at ts, '訊號' kind, title main, description detail "
        "FROM signals WHERE symbol=? ORDER BY created_at DESC LIMIT ?",
        (symbol, limit),
    ):
        rows.append(dict(r))
    for r in db.query(
        "SELECT created_at ts, 'AI' kind, recommendation main, summary detail "
        "FROM ai_analysis_logs WHERE symbol=? ORDER BY created_at DESC LIMIT ?",
        (symbol, limit),
    ):
        rows.append(dict(r))
    for r in db.query(
        "SELECT published_at ts, '新聞' kind, title main, summary detail "
        "FROM news_items WHERE related_symbols LIKE ? ORDER BY published_at DESC LIMIT ?",
        (f"%{symbol}%", limit),
    ):
        rows.append(dict(r))
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["ts_sort"] = pd.to_datetime(out["ts"], errors="coerce", utc=True)
    out = out.sort_values("ts_sort", ascending=False).drop(columns=["ts_sort"]).head(limit)
    return out.rename(columns={"ts": "時間", "kind": "類型", "main": "標題", "detail": "內容"})
