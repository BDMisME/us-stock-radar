"""設定頁 — 管理持股、觀察名單、API 設定、AI 頻率、資料匯出。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import streamlit as st

from config.settings import settings
from db import database as db

_UNIVERSE_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "stock_universe.json"

# Alpaca IEX websocket caps real-time subscriptions; holdings + high_focus share it.
REALTIME_CAP = 30
WATCHLIST_CAP = 50


def _realtime_usage() -> int:
    """How many names currently consume real-time slots (holdings + high_focus)."""
    return len(db.realtime_symbols(limit=REALTIME_CAP * 5))


@lru_cache(maxsize=1)
def _load_universe() -> list[dict]:
    try:
        with open(_UNIVERSE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _symbol_options() -> list[str]:
    """Return 'AAPL — Apple Inc.' style labels for the selectbox."""
    universe = _load_universe()
    if universe:
        return [f"{u['symbol']} — {u['name']}" for u in universe]
    return []


def _parse_symbol(option: str) -> str:
    """Extract plain ticker from 'AAPL — Apple Inc.'"""
    return option.split(" — ")[0].strip()


def _active_symbol_exists(table: str, symbol: str) -> bool:
    row = db.query_one(f"SELECT 1 FROM {table} WHERE symbol=? AND active=1 LIMIT 1", (symbol,))
    return bool(row)


def _bulk_update_group(table: str, symbols: list[str], group_name: str) -> None:
    if not symbols:
        return
    placeholders = ",".join("?" for _ in symbols)
    group_val = group_name.strip() or None
    db.execute(
        f"UPDATE {table} SET group_name=?, updated_at=? "
        f"WHERE active=1 AND symbol IN ({placeholders})",
        (group_val, db.utcnow_iso(), *symbols),
    )


def _bulk_remove(table: str, symbols: list[str]) -> None:
    if not symbols:
        return
    placeholders = ",".join("?" for _ in symbols)
    db.execute(
        f"UPDATE {table} SET active=0, updated_at=? WHERE active=1 AND symbol IN ({placeholders})",
        (db.utcnow_iso(), *symbols),
    )


def _symbol_selectbox(label: str, key: str) -> tuple[str, str]:
    """Searchable stock selectbox. Returns (symbol, name) or ('', '')."""
    opts = _symbol_options()
    if not opts:
        raw = st.text_input(label + "（手動輸入代號）", key=key).strip().upper()
        return raw, raw
    choice = st.selectbox(label, options=opts, index=None,
                          placeholder="輸入代號或公司名稱搜尋…", key=key)
    if not choice:
        return "", ""
    sym = _parse_symbol(choice)
    name = choice.split(" — ", 1)[1] if " — " in choice else sym
    return sym, name


def _realtime_quota_banner() -> None:
    used = _realtime_usage()
    remaining = REALTIME_CAP - used
    msg = (f"**即時行情額度（Alpaca IEX）：{used} / {REALTIME_CAP}**　"
           f"持股＋高關注共用此額度，剩餘 {max(remaining,0)} 檔。")
    if remaining <= 0:
        st.error(msg + "　已達上限，新增的即時標的將改用輪詢（更新較慢）。")
    elif remaining <= 5:
        st.warning(msg)
    else:
        st.info(msg)


def _add_holding_form() -> None:
    _realtime_quota_banner()
    with st.form("add_holding", clear_on_submit=True):
        st.markdown("**新增持股**")
        c1, c2 = st.columns([3, 1])
        with c1:
            sym, name = _symbol_selectbox("股票代號", "sel_hold")
        category = c2.selectbox("分類", ["長期持股 (long_term)", "短線持股 (swing)"])
        cat_val = "swing" if "swing" in category else "long_term"

        c3, c4, c5 = st.columns(3)
        shares   = c3.number_input("股數", min_value=0.0, step=1.0)
        avg_cost = c4.number_input("平均成本 ($)", min_value=0.0, step=0.01)
        target   = c5.number_input("目標價 ($)", min_value=0.0, step=0.01)
        c6, c7   = st.columns(2)
        stop     = c6.number_input("停損價 ($)", min_value=0.0, step=0.01)
        take     = c7.number_input("停利價 ($)", min_value=0.0, step=0.01)
        group    = st.text_input("群組（可自訂，例如 AI、金融、長期核心）", key="hold_group")
        theme    = st.text_input("主題標籤（逗號分隔）")

        submitted = st.form_submit_button("新增持股")
        if submitted and not sym:
            st.warning("請先選擇股票代號。")
        elif submitted and _active_symbol_exists("holdings", sym):
            st.warning(f"{sym} 已在持股中，請先移除舊資料或改用現有紀錄。")
        elif submitted and sym:
            db.insert("holdings", {
                "symbol": sym, "name": name or sym, "shares": shares,
                "avg_cost": avg_cost, "category": cat_val, "group_name": group.strip() or None,
                "theme_tags": theme,
                "stop_loss": stop or None, "take_profit": take or None,
                "target_price": target or None, "active": 1,
                "created_at": db.utcnow_iso(), "updated_at": db.utcnow_iso(),
            })
            st.success(f"已新增持股：{sym} — {name}")
            st.rerun()


def _add_watch_form() -> None:
    _realtime_quota_banner()
    active_watch_count = len(db.active_watchlist())
    st.caption(f"提示：分類選「高關注」會佔用即時額度（上限 {REALTIME_CAP}）；"
               f"觀察名單上限 {WATCHLIST_CAP} 檔；所有觀察標的會以約 "
               f"{settings.watchlist_poll_seconds}s 頻率更新。")
    if active_watch_count >= WATCHLIST_CAP:
        st.error(f"觀察名單已達 {WATCHLIST_CAP} 檔上限，請先移除不需要的標的。")
    with st.form("add_watch", clear_on_submit=True):
        st.markdown(f"**新增觀察名單**（{active_watch_count} / {WATCHLIST_CAP}）")
        c1, c2 = st.columns([3, 1])
        with c1:
            sym, name = _symbol_selectbox("股票代號 ", "sel_watch")
        category = c2.selectbox("分類 ", ["一般觀察 (general)", "高關注 (high_focus)"])
        cat_val = "high_focus" if "high_focus" in category else "general"

        c3, c4, c5 = st.columns(3)
        level    = c3.number_input("關注度 1-5", min_value=1, max_value=5, value=3)
        buy_low  = c4.number_input("目標買低 ($)", min_value=0.0, step=0.01)
        buy_high = c5.number_input("目標買高 ($)", min_value=0.0, step=0.01)
        group    = st.text_input("群組（可自訂，例如 AI、金融、能源）", key="watch_group")
        reason   = st.text_input("觀察原因")

        submitted = st.form_submit_button("新增觀察")
        if submitted and not sym:
            st.warning("請先選擇股票代號。")
        elif submitted and active_watch_count >= WATCHLIST_CAP:
            st.warning(f"觀察名單最多只能有 {WATCHLIST_CAP} 檔。")
        elif submitted and _active_symbol_exists("watchlist", sym):
            st.warning(f"{sym} 已在觀察名單中，請先移除舊資料或改用現有紀錄。")
        elif submitted and buy_low and buy_high and buy_low > buy_high:
            st.warning("目標買低不可高於目標買高。")
        elif submitted and sym:
            db.insert("watchlist", {
                "symbol": sym, "name": name or sym, "category": cat_val,
                "group_name": group.strip() or None,
                "watch_level": level, "target_buy_low": buy_low or None,
                "target_buy_high": buy_high or None, "reason": reason,
                "ai_enabled": 1, "alert_enabled": 1, "active": 1,
                "created_at": db.utcnow_iso(), "updated_at": db.utcnow_iso(),
            })
            st.success(f"已新增觀察：{sym} — {name}")
            st.rerun()


def _manage_holdings() -> None:
    rows = db.active_holdings()
    if not rows:
        st.caption("尚無持股。")
        return
    group_view = st.selectbox(
        "顯示群組",
        ["全部"] + sorted({h.get("group_name") or "未分組" for h in rows}),
        key="manage_hold_group_filter",
    )
    if group_view != "全部":
        rows = [h for h in rows if (h.get("group_name") or "未分組") == group_view]
    if not rows:
        st.caption("此群組尚無持股。")
        return
    symbols = [h["symbol"] for h in rows]
    with st.expander("批量操作", expanded=False):
        selected = st.multiselect("選擇持股", symbols, key="bulk_hold_symbols")
        c1, c2, c3 = st.columns([2, 1, 1])
        bulk_group = c1.text_input("批量設定群組", key="bulk_hold_group", placeholder="輸入新群組，留空代表未分組")
        if c2.button("套用群組", disabled=not selected, key="bulk_hold_group_btn"):
            _bulk_update_group("holdings", selected, bulk_group)
            st.success(f"已更新 {len(selected)} 檔持股群組。")
            st.rerun()
        if c3.button("批量移除", disabled=not selected, key="bulk_hold_remove_btn"):
            _bulk_remove("holdings", selected)
            st.success(f"已移除 {len(selected)} 檔持股。")
            st.rerun()

    for h in rows:
        c1, c2, c3, c4 = st.columns([2.4, 3.4, 2, 1])
        c1.write(f"**{h['symbol']}** · {h.get('name', '')}")
        _cat_h = {"long_term": "長期", "swing": "短線", "core": "長期", "high_focus": "長期"}
        cat_str = _cat_h.get(h.get("category", ""), h.get("category", "長期"))
        c2.caption(
            f"{h.get('shares')} 股 @ ${h.get('avg_cost')} "
            f"· 停損 {h.get('stop_loss') or '—'} / 停利 {h.get('take_profit') or '—'} "
            f"· [{cat_str}]"
        )
        group = c3.text_input("群組", value=h.get("group_name") or "", key=f"group_h_{h['id']}", label_visibility="collapsed")
        if c3.button("更新群組", key=f"upd_group_h_{h['id']}", use_container_width=True):
            _bulk_update_group("holdings", [h["symbol"]], group)
            st.rerun()
        if c4.button("移除", key=f"del_h_{h['id']}"):
            db.execute("UPDATE holdings SET active=0, updated_at=? WHERE id=?",
                       (db.utcnow_iso(), h["id"]))
            st.rerun()


def _manage_watch() -> None:
    rows = db.active_watchlist()
    if not rows:
        st.caption("尚無觀察名單。")
        return
    group_view = st.selectbox(
        "顯示群組",
        ["全部"] + sorted({w.get("group_name") or "未分組" for w in rows}),
        key="manage_watch_group_filter",
    )
    if group_view != "全部":
        rows = [w for w in rows if (w.get("group_name") or "未分組") == group_view]
    if not rows:
        st.caption("此群組尚無觀察標的。")
        return
    _label = {"high_focus": "高關注", "general": "一般觀察"}
    st.caption(f"共 {len(rows)} / {WATCHLIST_CAP} 檔")
    symbols = [w["symbol"] for w in rows]
    with st.expander("批量操作", expanded=False):
        selected = st.multiselect("選擇觀察標的", symbols, key="bulk_watch_symbols")
        c1, c2, c3 = st.columns([2, 1, 1])
        bulk_group = c1.text_input("批量設定群組", key="bulk_watch_group", placeholder="輸入新群組，留空代表未分組")
        if c2.button("套用群組", disabled=not selected, key="bulk_watch_group_btn"):
            _bulk_update_group("watchlist", selected, bulk_group)
            st.success(f"已更新 {len(selected)} 檔觀察標的群組。")
            st.rerun()
        if c3.button("批量移除", disabled=not selected, key="bulk_watch_remove_btn"):
            _bulk_remove("watchlist", selected)
            st.success(f"已移除 {len(selected)} 檔觀察標的。")
            st.rerun()

    for w in rows[:WATCHLIST_CAP]:
        c1, c2, c3, c4 = st.columns([2.4, 3.4, 2, 1])
        c1.write(f"**{w['symbol']}** · {w.get('name', '')}")
        c2.caption(
            f"{_label.get(w.get('category',''), w.get('category',''))} "
            f"· 關注度 {w.get('watch_level')} "
            f"· 買區 {w.get('target_buy_low') or '—'}~{w.get('target_buy_high') or '—'}"
        )
        group = c3.text_input("群組", value=w.get("group_name") or "", key=f"group_w_{w['id']}", label_visibility="collapsed")
        if c3.button("更新群組", key=f"upd_group_w_{w['id']}", use_container_width=True):
            _bulk_update_group("watchlist", [w["symbol"]], group)
            st.rerun()
        if c4.button("移除", key=f"del_w_{w['id']}"):
            db.execute("UPDATE watchlist SET active=0, updated_at=? WHERE id=?",
                       (db.utcnow_iso(), w["id"]))
            st.rerun()


def _config_status() -> None:
    st.markdown("**API / 通知設定狀態**（值請於 `.env` 設定，此頁不顯示明碼）")
    checks = {
        "Alpaca 即時行情": settings.alpaca_enabled,
        "Finnhub":         settings.finnhub_enabled,
        "FMP":             settings.fmp_enabled,
        "LLM AI 分析":     settings.llm_enabled,
        "Telegram 通知":   settings.telegram_enabled,
        "Email 通知":      settings.email_enabled,
    }
    cols = st.columns(3)
    for i, (label, ok) in enumerate(checks.items()):
        cols[i % 3].write(f"{'✅' if ok else '⛔'} {label}")

    st.divider()
    st.caption(
        f"資料庫路徑：`{settings.db_file}`  \n"
        f"行情輪詢間隔：{max(settings.watchlist_poll_seconds, 5)}s  \n"
        f"AI Worker 間隔：{settings.ai_worker_interval_seconds}s"
    )


def _ai_frequency() -> None:
    st.markdown("**AI 分析冷卻設定**")
    c1, c2 = st.columns(2)
    c1.metric("短線持股冷卻", f"{settings.ai_cooldown_core_hours} 小時",
              help="短線持股 (swing) CRITICAL 觸發後的 AI 分析冷卻時間（較短，積極更新）")
    c2.metric("長期持股／高關注冷卻", f"{settings.ai_cooldown_focus_hours} 小時",
              help="長期持股 (long_term) 及高關注觀察名單的冷卻時間（較長，減少雜訊）")
    st.caption("修改冷卻時間請在 `.env` 設定 AI_COOLDOWN_CORE_HOURS / AI_COOLDOWN_FOCUS_HOURS")

    st.divider()
    st.markdown("**排程分析頻率（美東時間）**")
    st.table([
        {"層級": "短線持股 (swing)",    "冷卻": f"{settings.ai_cooldown_core_hours}h",  "頻率": "開盤前 09:00 / 盤中每 30 分 / 收盤 16:05 / CRITICAL 即時"},
        {"層級": "長期持股 (long_term)","冷卻": f"{settings.ai_cooldown_focus_hours}h", "頻率": "開盤前 09:00 / 盤中每 60 分 / CRITICAL 即時"},
        {"層級": "高關注觀察",           "冷卻": f"{settings.ai_cooldown_focus_hours}h", "頻率": "開盤前 09:00 / 盤中每 60 分 / CRITICAL 即時"},
        {"層級": "一般觀察",             "冷卻": "盤後批次",                               "頻率": "收盤後批次（16:05）"},
        {"層級": "手動 AI 分析",          "冷卻": "每日 5 次",                              "頻率": "由 AI 分析師頁手動觸發，不影響排程/訊號觸發"},
        {"層級": "新聞",                 "冷卻": "立即搜尋每日 1 次",                       "頻率": "每日台灣時間 18:00 自動搜尋；新聞頁可手動立即搜尋"},
    ])


def _export() -> None:
    st.markdown("**匯出資料 (CSV)**")
    import pandas as pd
    tables = {
        "持股": "holdings",
        "觀察名單": "watchlist",
        "訊號": "signals",
        "AI 分析紀錄": "ai_analysis_logs",
        "新聞": "news_items",
    }
    cols = st.columns(len(tables))
    for i, (label, table) in enumerate(tables.items()):
        df = pd.DataFrame(db.to_dicts(db.query(f"SELECT * FROM {table}")))
        cols[i].download_button(
            label, df.to_csv(index=False).encode("utf-8"),
            file_name=f"{table}.csv", mime="text/csv",
            disabled=df.empty, key=f"dl_{table}")


def render() -> None:
    st.subheader("設定")
    tabs = st.tabs(["持股", "觀察名單", "API / 通知", "AI 頻率", "匯出"])
    with tabs[0]:
        _add_holding_form()
        st.divider()
        _manage_holdings()
    with tabs[1]:
        _add_watch_form()
        st.divider()
        _manage_watch()
    with tabs[2]:
        _config_status()
    with tabs[3]:
        _ai_frequency()
    with tabs[4]:
        _export()
