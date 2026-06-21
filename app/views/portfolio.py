"""Portfolio page — holdings with P&L, treemap, grouped table, and chart."""
from __future__ import annotations

import streamlit as st

from app.components import charts, data, style, ui
from db import database as db


def _render_table(df):
    if df.empty:
        st.caption("此分類尚無持股。")
        return
    st.dataframe(
        style.style_table(
            df,
            color_cols=["漲跌%", "未實現損益", "損益%"],
            pct_cols=["漲跌%", "損益%"],
            money_cols=["市值", "未實現損益"],
            price_cols=["均價", "現價", "MA20", "MA60"],
        ),
        use_container_width=True,
        hide_index=True,
    )


def _column_controls(df, key_prefix: str):
    default_cols = [c for c in ["代號", "群組", "類型", "現價", "漲跌%", "市值", "未實現損益", "損益%", "AI建議", "風險"] if c in df.columns]
    c1, c2 = st.columns([2.4, 1])
    cols = c1.multiselect("顯示欄位", df.columns.tolist(), default=default_cols, key=f"{key_prefix}_cols")
    sort_col = c2.selectbox("排序", [c for c in ["市值", "漲跌%", "損益%", "群組", "代號"] if c in df.columns],
                            key=f"{key_prefix}_sort")
    view = df[cols] if cols else df
    if sort_col in view.columns and sort_col != "代號":
        view = view.sort_values(sort_col, ascending=False, na_position="last")
    elif sort_col in view.columns:
        view = view.sort_values(sort_col)
    return view


def _category_change_panel(df):
    """Inline category change — lets user switch a holding between 長期 and 短線."""
    with st.expander("✏️ 修改持股類型（長期 / 短線）"):
        syms = df["代號"].tolist()
        c1, c2, c3 = st.columns([2, 2, 1])
        sym = c1.selectbox("選擇代號", syms, key="cat_change_sym")
        new_cat_label = c2.selectbox(
            "新類型", ["長期持股 (long_term)", "短線持股 (swing)"],
            key="cat_change_val",
        )
        new_cat = "swing" if "swing" in new_cat_label else "long_term"
        if c3.button("更新", key="cat_change_btn"):
            db.execute(
                "UPDATE holdings SET category=?, updated_at=? WHERE symbol=? AND active=1",
                (new_cat, db.utcnow_iso(), sym),
            )
            st.success(f"{sym} 已更新為「{'短線' if new_cat == 'swing' else '長期'}」")
            st.rerun()


def render() -> None:
    st.subheader("持股")
    df = data.portfolio_table()
    if df.empty:
        ui.empty_state("尚無持股", "請到「設定」頁面新增持股。")
        return

    groups = ["全部"] + sorted(df["群組"].fillna("未分組").unique().tolist())
    group_filter = st.segmented_control("群組", groups, default="全部", key="pf_group")
    if group_filter and group_filter != "全部":
        df = df[df["群組"] == group_filter]

    totals = data.portfolio_totals(df)

    # ── Metrics ──────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        ui.metric_card("總市值", f"${totals['market_value']:,.0f}", hint="目前持股總市值")
    with c2:
        ui.metric_card(
            "未實現損益",
            f"${totals['unrealized_pnl']:,.0f}",
            f"{totals['unrealized_pnl_pct']:+.2f}%",
            totals["unrealized_pnl"],
            hint="紅漲 / 綠跌",
        )
    n_swing  = int((df["類型"] == "短線").sum())
    n_long   = int((df["類型"] == "長期").sum())
    with c3:
        ui.metric_card("短線持股", f"{n_swing} 檔", hint="較高頻監控")
    with c4:
        ui.metric_card("長期持股", f"{n_long} 檔", hint="較低頻監控")

    # ── Treemap ───────────────────────────────────────────────────────────────
    st.plotly_chart(
        charts.portfolio_treemap(df),
        use_container_width=True,
        config={"displayModeBar": False},
    )
    st.caption("方塊大小＝市值　顏色🔴漲 🟢跌（台股慣例）")

    # ── Grouped table ─────────────────────────────────────────────────────────
    tab_all, tab_swing, tab_long = st.tabs(["全部", "短線持股", "長期持股"])
    with tab_all:
        _render_table(_column_controls(df, "pf_all"))
    with tab_swing:
        _render_table(_column_controls(df[df["類型"] == "短線"], "pf_swing"))
    with tab_long:
        _render_table(_column_controls(df[df["類型"] == "長期"], "pf_long"))

    st.caption("顏色：🔴 紅＝上漲　🟢 綠＝下跌（台股慣例）")

    _category_change_panel(df)

    # ── Chart ─────────────────────────────────────────────────────────────────
    with st.expander("個股 K 線", expanded=False):
        st.caption("提示：滑鼠滾輪縮放 · 拖曳平移 · 右上角快捷鈕切換時間區間")
        sym = st.selectbox("選擇標的", df["代號"].tolist(), key="pf_chart_sym")
        range_label = st.segmented_control(
            "時間範圍",
            data.RANGE_OPTIONS,
            default="3個月",
            key="pf_chart_range",
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
            ai = data.latest_ai_row(sym)
            if ai:
                with st.expander(f"{sym} 最新 AI 分析", expanded=False):
                    action = data.ACTION_LABELS.get(ai.get("action"), ai.get("action") or "—")
                    risk = data.RISK_LABELS.get(ai.get("risk_level"), ai.get("risk_level") or "—")
                    st.write(f"**建議**：{ai.get('recommendation') or '—'}　"
                             f"**動作**：{action}　**風險**：{risk}")
                    if ai.get("summary"):
                        st.write(ai["summary"])
                    if ai.get("invalidation_condition"):
                        st.caption(f"失效條件：{ai['invalidation_condition']}")
                    if ai.get("next_watch_price"):
                        st.caption(f"觀察價：${ai['next_watch_price']:,.2f}")
            timeline = data.symbol_timeline(sym)
            with st.expander(f"{sym} 個股時間線", expanded=False):
                if timeline.empty:
                    ui.empty_state("尚無時間線事件", "訊號、新聞與 AI 分析會在這裡彙整。")
                else:
                    st.dataframe(timeline, use_container_width=True, hide_index=True)
