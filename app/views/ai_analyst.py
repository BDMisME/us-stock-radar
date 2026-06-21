"""AI Analyst page — structured AI analysis history with filters."""
from __future__ import annotations

import streamlit as st

from agents.stock_analyst_agent import StockAnalystAgent
from app.components import data, ui
from db import database as db


def render() -> None:
    st.subheader("AI 分析師")

    agent = StockAnalystAgent()
    if not agent.enabled:
        st.warning("AI 分析師尚未設定（需在 .env 填入 LLM_API_KEY / LLM_MODEL）。")

    # On-demand analysis
    with st.expander("立即分析個股", expanded=False):
        manual_used = db.usage_count_today("manual", "stock_analysis")
        manual_remaining = max(0, 5 - manual_used)
        st.caption(f"立即分析每日限 5 次（台灣日曆日），今日剩餘 {manual_remaining} 次。")
        symbols = db.all_tracked_symbols()
        col1, col2 = st.columns([3, 1])
        sym = col1.selectbox("標的", symbols) if symbols else None
        if col2.button("分析", disabled=not (agent.enabled and sym and manual_remaining > 0)):
            db.log_api_usage("manual", "stock_analysis")
            with st.spinner(f"分析 {sym} 中…"):
                result = agent.analyze(sym, trigger_description="手動觸發 (Dashboard)")
            if result:
                meta = result.pop("_meta", {})
                db.log_ai_analysis({
                    "symbol": sym, "analysis_type": "manual", "trigger_type": "manual",
                    "recommendation": result.get("recommendation"),
                    "risk_level": result.get("risk_level"), "action": result.get("action"),
                    "summary": result.get("summary"), "reasoning": result.get("reasoning"),
                    "invalidation_condition": result.get("invalidation_condition"),
                    "next_watch_price": result.get("next_watch_price"),
                    "model": meta.get("model"), "input_tokens": meta.get("input_tokens"),
                    "output_tokens": meta.get("output_tokens"),
                })
                st.success("分析完成，已寫入紀錄。")
                st.json(result)
            else:
                st.error("分析失敗或 ARK 未回應。")

    df = data.ai_table(limit=300)
    if df.empty:
        ui.empty_state(
            "尚無 AI 分析紀錄",
            "可在上方「立即分析個股」手動觸發，或等待事件/排程自動產生。",
        )
        return

    c1, c2, c3 = st.columns(3)
    sym_f = c1.text_input("依代號搜尋").strip().upper()
    action_f = c2.multiselect("動作", sorted(df["動作"].dropna().unique().tolist()))
    risk_f = c3.multiselect("風險", sorted(df["風險"].dropna().unique().tolist()))

    view = df
    if sym_f:
        view = view[view["代號"].str.upper().str.contains(sym_f)]
    if action_f:
        view = view[view["動作"].isin(action_f)]
    if risk_f:
        view = view[view["風險"].isin(risk_f)]

    st.caption(f"{len(view)} / {len(df)} 筆")
    st.dataframe(view, use_container_width=True, hide_index=True)
    st.caption("⚠️ AI 內容僅供研究與風險提醒，非投資建議，不保證獲利。")
