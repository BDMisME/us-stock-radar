"""Watchlist page — high-focus and general watch names with buy-zone highlights."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components import charts, data, style, ui


def _buy_zone_color(val: str) -> str:
    """Style rule for the 買區狀態 column."""
    s = str(val)
    if "✓" in s:
        return "color: #4ADE80; font-weight: 600"   # green — price is in zone
    if "↓" in s:
        return "color: #60A5FA"                      # blue — below zone (even cheaper)
    if "↑" in s:
        return "color: #9CA3AF"                      # gray — above zone (missed entry)
    return ""


def _render_watchlist_table(df: pd.DataFrame) -> None:
    if df.empty:
        st.caption("此分類尚無觀察名單。")
        return

    # Build styler for color columns + buy zone
    color_cols = [c for c in ["漲跌%", "距MA20%", "距MA60%"] if c in df.columns]
    sty = style.style_table(
        df,
        color_cols=color_cols,
        pct_cols=["漲跌%", "距MA20%", "距MA60%"],
        price_cols=["現價"],
    )
    if "買區狀態" in df.columns:
        sty = sty.map(_buy_zone_color, subset=["買區狀態"])

    st.dataframe(sty, use_container_width=True, hide_index=True)


def _column_controls(df: pd.DataFrame) -> pd.DataFrame:
    default_cols = [c for c in ["代號", "群組", "分類", "主題", "關注度", "現價", "漲跌%", "買區狀態", "最新訊號", "AI建議"] if c in df.columns]
    c1, c2 = st.columns([2.4, 1])
    cols = c1.multiselect("顯示欄位", df.columns.tolist(), default=default_cols, key="wl_cols")
    sort_options = [c for c in ["關注度", "漲跌%", "距MA20%", "群組", "代號"] if c in df.columns]
    sort_col = c2.selectbox("排序", sort_options, key="wl_sort") if sort_options else None
    view = df[cols] if cols else df
    if sort_col in view.columns and sort_col != "代號":
        view = view.sort_values(sort_col, ascending=False, na_position="last")
    elif sort_col in view.columns:
        view = view.sort_values(sort_col)
    return view


def render() -> None:
    st.subheader("觀察名單")
    cat = st.radio("分類", ["全部", "高關注", "一般觀察"], horizontal=True)
    _cat_map = {"全部": None, "高關注": "high_focus", "一般觀察": "general"}
    category = _cat_map[cat]

    df = data.watchlist_table(category)
    if df.empty:
        ui.empty_state("觀察名單為空", "請到「設定」頁面新增。")
        return

    groups = ["全部"] + sorted(df["群組"].fillna("未分組").unique().tolist())
    group_filter = st.segmented_control("群組", groups, default="全部", key="wl_group")
    if group_filter and group_filter != "全部":
        df = df[df["群組"] == group_filter]
    if df.empty:
        ui.empty_state("此群組沒有觀察標的", "請切換群組或到設定頁調整群組。")
        return

    # Summary metrics row
    n_in_zone = int(df["買區狀態"].str.startswith("✓").sum()) if "買區狀態" in df.columns else 0
    c1, c2, c3 = st.columns(3)
    with c1:
        ui.metric_card("觀察檔數", f"{len(df)} 檔", hint="目前篩選結果")
    with c2:
        ui.metric_card("在買區", f"{n_in_zone} 檔", hint="價格落在目標買區")
    with c3:
        ui.metric_card("高關注", f"{int((df['分類'] == '高關注').sum())} 檔", hint="佔用即時額度")

    q = st.text_input("搜尋代號或主題", placeholder="例如 NVDA、AI、半導體").strip().upper()
    if q:
        haystack = (
            df["代號"].astype(str).str.upper()
            + " "
            + df["主題"].fillna("").astype(str).str.upper()
        )
        df = df[haystack.str.contains(q, regex=False)]
        st.caption(f"搜尋結果：{len(df)} 筆")
    if df.empty:
        ui.empty_state("沒有符合條件的標的", "請放寬分類或搜尋關鍵字。")
        return

    _render_watchlist_table(_column_controls(df))
    st.caption("顏色：🔴 紅＝上漲　🟢 綠＝下跌（台股慣例）　買區狀態：🟢在區 · 🔵低於區 · ⬜高於區")

    # ── Chart ──────────────────────────────────────────────────────────────
    with st.expander("個股 K 線", expanded=False):
        st.caption("提示：滑鼠滾輪縮放 · 拖曳平移 · 右上角快捷鈕切換時間區間")
        sym = st.selectbox("選擇標的", df["代號"].tolist(), key="wl_chart_sym")
        range_label = st.segmented_control(
            "時間範圍",
            data.RANGE_OPTIONS,
            default="3個月",
            key="wl_chart_range",
        )
        if sym:
            bars, source_note = data.chart_bars(sym, range_label or "3個月")
            st.caption(source_note)
            st.plotly_chart(
                charts.price_chart(bars, sym, range_label or ""),
                use_container_width=True,
                config={"scrollZoom": True, "displaylogo": False,
                        "modeBarButtonsToRemove": ["select2d", "lasso2d"]},
            )
            timeline = data.symbol_timeline(sym)
            with st.expander(f"{sym} 個股時間線", expanded=False):
                if timeline.empty:
                    ui.empty_state("尚無時間線事件", "訊號、新聞與 AI 分析會在這裡彙整。")
                else:
                    st.dataframe(timeline, use_container_width=True, hide_index=True)
