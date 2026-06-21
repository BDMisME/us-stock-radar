"""Overview page — the at-a-glance daily snapshot."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components import data, ui
from db import database as db


def render() -> None:
    st.subheader("總覽")

    pf = data.portfolio_table()
    totals = data.portfolio_totals(pf)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        ui.metric_card("持股市值", f"${totals['market_value']:,.0f}", hint="目前持股總市值")
    with c2:
        ui.metric_card(
            "未實現損益",
            f"${totals['unrealized_pnl']:,.0f}",
            f"{totals['unrealized_pnl_pct']:+.2f}%",
            totals["unrealized_pnl"],
            hint="紅漲 / 綠跌",
        )
    high_risk = db.query_one(
        "SELECT COUNT(*) c FROM ai_analysis_logs WHERE risk_level='high' "
        "AND datetime(created_at) >= datetime('now','-1 day')")["c"]
    with c3:
        ui.metric_card("今日高風險提醒", f"{high_risk}", hint="近 24 小時 high")
    pending = db.query_one("SELECT COUNT(*) c FROM signals WHERE status='pending_ai'")["c"]
    with c4:
        ui.metric_card("待 AI 分析事件", f"{pending}", hint="等待 AI worker")

    st.divider()
    left, right = st.columns([3, 2])

    with left:
        tasks = data.risk_tasks(limit=8)
        ui.section_header("風險待辦", f"{len(tasks)} 項")
        if tasks.empty:
            ui.empty_state("目前沒有高優先待辦", "重大訊號與風險事件會集中在這裡。")
        else:
            st.dataframe(tasks, use_container_width=True, hide_index=True)

        ai = data.ai_table(limit=8)
        ui.section_header("最新 AI 建議", f"{len(ai)} 筆")
        if ai.empty:
            ui.empty_state(
                "尚無最新建議",
                "AI 分析將於重大事件觸發或排程時間自動產生。",
            )
        else:
            st.dataframe(
                ai[["代號", "建議", "動作", "風險", "摘要", "時間"]],
                use_container_width=True, hide_index=True)

        # Rank by event count; top_sev uses an explicit ordinal so 'critical'
        # outranks 'warning'/'info' (a plain MAX() would sort lexically and pick
        # 'warning' over 'critical').
        rank = db.query(
            "SELECT symbol, COUNT(*) events, "
            "CASE MAX(CASE severity WHEN 'critical' THEN 3 WHEN 'warning' THEN 2 "
            "WHEN 'info' THEN 1 ELSE 0 END) WHEN 3 THEN 'critical' WHEN 2 THEN 'warning' "
            "WHEN 1 THEN 'info' ELSE '—' END top_sev "
            "FROM signals WHERE datetime(created_at) >= datetime('now','-1 day') "
            "GROUP BY symbol ORDER BY events DESC LIMIT 10")
        rank_df = pd.DataFrame(db.to_dicts(rank))
        ui.section_header("異常股票排行", "近 24h")
        if rank_df.empty:
            ui.empty_state("目前平靜", "近 24 小時無異常事件。")
        else:
            rank_df["top_sev"] = rank_df["top_sev"].map(
                lambda v: data.SEVERITY_LABELS.get(v, v))
            rank_df = rank_df.rename(columns={
                "symbol": "代號", "events": "事件數", "top_sev": "最高嚴重度"})
            st.dataframe(rank_df, use_container_width=True, hide_index=True)

    with right:
        news = data.news_table(limit=6)
        ui.section_header("今日新聞摘要", f"{len(news)} 則")
        if news.empty:
            ui.empty_state("尚無新聞摘要", "新聞於開盤前後自動抓取並摘要。")
        else:
            for _, n in news.iterrows():
                tag = n.get("sentiment") or "—"
                st.markdown(f"- **[{tag}]** {n['title']}  \n  <small>{n.get('source','')}</small>",
                            unsafe_allow_html=True)

    st.caption("⚠️ 本工具僅供個人監控與研究，不提供投資建議、不保證獲利、不執行任何下單。")
