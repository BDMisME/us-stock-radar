"""Signals page — the rules-engine event feed."""
from __future__ import annotations

import streamlit as st

from app.components import data, ui


def render() -> None:
    st.subheader("訊號")
    df = data.signals_table(limit=300)
    if df.empty:
        ui.empty_state(
            "目前沒有觸發任何訊號",
            "系統會在價格或技術指標達到設定條件時自動產生，例如跌破均線、放量、進入買區。",
        )
        return

    c1, c2, c3 = st.columns([1, 1, 1.4])
    sev = c1.multiselect("嚴重度", sorted(df["嚴重度"].dropna().unique().tolist()))
    status = c2.multiselect("AI 狀態", sorted(df["AI狀態"].dropna().unique().tolist()))
    sym_f = c3.text_input("搜尋代號 / 事件", placeholder="例如 AAPL、跌破、放量").strip().upper()
    view = df
    if sev:
        view = view[view["嚴重度"].isin(sev)]
    if status:
        view = view[view["AI狀態"].isin(status)]
    if sym_f:
        haystack = (
            view["代號"].astype(str).str.upper()
            + " "
            + view["事件"].fillna("").astype(str).str.upper()
            + " "
            + view["說明"].fillna("").astype(str).str.upper()
        )
        view = view[haystack.str.contains(sym_f, regex=False)]

    st.caption(f"{len(view)} / {len(df)} 筆")
    st.dataframe(
        view, use_container_width=True, hide_index=True,
        column_config={"價格": st.column_config.NumberColumn("價格", format="$%.2f")},
    )
