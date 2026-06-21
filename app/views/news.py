"""News page — daily headlines with AI summary, sentiment and impact."""
from __future__ import annotations

import streamlit as st

from app.components import data, ui
from db import database as db
from news.news_analyzer import analyze_pending_news
from news.news_fetcher import fetch_and_store


_SENT_COLOR = {"bullish": "🔴", "bearish": "🟢", "neutral": "⚪", "uncertain": "🟡"}
_SENT_LABEL = {"bullish": "偏多", "bearish": "偏空", "neutral": "中性", "uncertain": "不確定"}


def render() -> None:
    st.subheader("新聞")
    used = db.usage_count_today("manual", "news_search")
    remaining = max(0, 1 - used)
    c0, c1 = st.columns([2, 1])
    c0.caption("自動新聞搜尋：每日台灣時間 18:00 觸發；立即搜尋每日限 1 次。")
    if c1.button("立即搜尋新聞", disabled=remaining <= 0, use_container_width=True):
        db.log_api_usage("manual", "news_search")
        with st.spinner("搜尋並分析新聞中…"):
            stored = fetch_and_store(limit=15)
            analyzed = analyze_pending_news(limit=15)
        st.success(f"已新增 {stored} 則新聞，AI 分析 {analyzed} 則。")
        st.rerun()
    if remaining <= 0:
        st.caption("今日立即搜尋額度已用完，下一個台灣日曆日重置。")
    else:
        st.caption(f"今日立即搜尋剩餘 {remaining} 次。")

    df = data.news_table(limit=50)
    if df.empty:
        ui.empty_state("尚無新聞", "新聞於開盤前後自動抓取並由 AI 摘要、標註情緒與影響標的。")
        return

    c1, c2 = st.columns([1, 1.6])
    sentiment = c1.multiselect(
        "情緒",
        sorted([s for s in df["sentiment"].dropna().unique().tolist()]),
        format_func=lambda s: _SENT_LABEL.get(s, s),
    )
    q = c2.text_input("搜尋標題 / 摘要 / 標的", placeholder="例如 NVDA、Fed、earnings").strip().upper()
    view = df
    if sentiment:
        view = view[view["sentiment"].isin(sentiment)]
    if q:
        haystack = (
            view["title"].fillna("").astype(str).str.upper()
            + " "
            + view["summary"].fillna("").astype(str).str.upper()
            + " "
            + view["related_symbols"].fillna("").astype(str).str.upper()
        )
        view = view[haystack.str.contains(q, regex=False)]

    st.caption("情緒顏色：🔴 偏多 / 🟢 偏空（台股慣例）")
    if view.empty:
        ui.empty_state("沒有符合條件的新聞", "請放寬情緒篩選或搜尋關鍵字。")
        return

    for _, n in view.iterrows():
        dot = _SENT_COLOR.get(n.get("sentiment"), "⚪")
        sent = _SENT_LABEL.get(n.get("sentiment"), n.get("sentiment") or "—")
        impact = n.get("impact_level") or "—"
        with st.container(border=True):
            st.markdown(f"{dot} **{n['title']}**")
            meta = f"{n.get('source','')} · {n.get('published_at','')} · 情緒: {sent} · 影響: {impact}"
            if n.get("related_symbols"):
                meta += f" · 連動: {n['related_symbols']}"
            st.caption(meta)
            if n.get("summary"):
                st.write(n["summary"])
            if n.get("url"):
                st.markdown(f"[原文連結]({n['url']})")
