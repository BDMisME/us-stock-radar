"""Plotly chart builders for the dashboard (candlestick + indicators + treemap)."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from indicators import technical

_GREEN = "#4ADE80"
_RED = "#F87171"
_BLUE = "#60A5FA"
_AMBER = "#FBBF24"
_GRID = "#1F2937"
_BG = "#0B0F14"
_NEUTRAL = "#374151"

# rangeselector button style (shared)
_RS_BUTTONS = list([
    dict(count=3,  label="3天", step="day", stepmode="backward"),
    dict(count=7,  label="7天", step="day", stepmode="backward"),
    dict(count=1,  label="1月", step="month", stepmode="backward"),
    dict(count=3,  label="3月", step="month", stepmode="backward"),
    dict(count=6,  label="6月", step="month", stepmode="backward"),
    dict(count=1,  label="1年", step="year",  stepmode="backward"),
    dict(step="all", label="全部"),
])
_RS_STYLE = dict(
    bgcolor=_NEUTRAL, activecolor=_GREEN,
    bordercolor="#4B5563", borderwidth=1,
    font=dict(color="#E5E7EB", size=11),
)


def portfolio_treemap(df: pd.DataFrame) -> go.Figure:
    """Finviz-style market-cap treemap: size=市值, color=漲跌% (台股: 紅漲綠跌)."""
    if df.empty or "市值" not in df.columns:
        fig = go.Figure()
        fig.update_layout(template="plotly_dark", paper_bgcolor=_BG, height=200,
                          annotations=[dict(text="尚無持股資料", showarrow=False,
                                           font=dict(color="#6B7280"))])
        return fig

    pct = pd.to_numeric(df.get("漲跌%", pd.Series(dtype=float)), errors="coerce").fillna(0)
    mv  = pd.to_numeric(df.get("市值",  pd.Series(dtype=float)), errors="coerce").fillna(0)
    syms = df["代號"].tolist()
    types = df["類型"].tolist() if "類型" in df.columns else [""] * len(df)
    pnl_pct = pd.to_numeric(df.get("損益%", pd.Series(dtype=float)), errors="coerce").fillna(0)

    labels = [f"<b>{s}</b><br>{p:+.2f}%" for s, p in zip(syms, pct)]

    # Taiwan convention: positive pct → red, negative → green
    # colorscale maps [min→green, 0→neutral, max→red]; cmid=0 centres it at zero
    max_abs = max(abs(pct).max(), 0.5)

    fig = go.Figure(go.Treemap(
        labels=labels,
        parents=[""] * len(syms),
        values=mv.clip(lower=1),          # avoid zero-size tiles
        customdata=list(zip(syms, pct, pnl_pct, types, mv)),
        hovertemplate=(
            "<b>%{customdata[0]}</b> · %{customdata[3]}<br>"
            "今日: <b>%{customdata[1]:+.2f}%</b><br>"
            "損益: %{customdata[2]:+.2f}%<br>"
            "市值: $%{customdata[4]:,.0f}"
            "<extra></extra>"
        ),
        texttemplate="%{label}",
        textfont=dict(size=13, family="monospace"),
        marker=dict(
            colors=pct.tolist(),
            colorscale=[
                [0.0, _GREEN],    # most negative → green (跌)
                [0.5, _NEUTRAL],  # zero → neutral
                [1.0, _RED],      # most positive → red (漲)
            ],
            cmin=-max_abs, cmid=0, cmax=max_abs,
            showscale=True,
            colorbar=dict(
                title=dict(text="今日漲跌%", font=dict(size=11)),
                thickness=12, len=0.7,
                tickformat="+.1f",
            ),
            pad=dict(t=3, l=3, r=3, b=3),
        ),
        tiling=dict(packing="squarify"),
    ))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=_BG, plot_bgcolor=_BG,
        height=260, margin=dict(l=0, r=0, t=4, b=0),
    )
    return fig


def price_chart(df: pd.DataFrame, symbol: str, range_label: str = "") -> go.Figure:
    """Candlestick + MA overlays, RSI and volume subplots.

    UX notes:
    - dragmode="pan"  → drag to scroll left/right (like every trading platform)
    - scrollZoom is enabled via config={"scrollZoom": True} at render site
    - rangeselector buttons let users jump to 1M / 3M / 6M / 1Y / ALL
    """
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        row_heights=[0.60, 0.18, 0.22],
        subplot_titles=(f"{symbol} {range_label}".strip(), "RSI(14)", "成交量"),
    )

    if df.empty:
        fig.update_layout(
            template="plotly_dark", paper_bgcolor=_BG, plot_bgcolor=_BG,
            height=620,
            annotations=[dict(text="尚無 K 線資料", showarrow=False,
                              font=dict(color="#6B7280", size=14))],
        )
        return fig

    # Taiwan convention: 漲=紅 (increasing red), 跌=綠 (decreasing green)
    x = pd.to_datetime(df["timestamp"])
    fig.add_trace(go.Candlestick(
        x=x, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="Price",
        increasing_line_color=_RED, increasing_fillcolor=_RED,
        decreasing_line_color=_GREEN, decreasing_fillcolor=_GREEN,
        line=dict(width=1),
    ), row=1, col=1)

    close = df["close"].astype(float)
    for window, color in ((20, _BLUE), (60, _AMBER)):
        ma = technical.sma(close, window)
        fig.add_trace(
            go.Scatter(x=x, y=ma, name=f"MA{window}",
                       line=dict(color=color, width=1.2), opacity=0.85),
            row=1, col=1,
        )

    rsi = technical.rsi(close, 14)
    fig.add_trace(
        go.Scatter(x=x, y=rsi, name="RSI", line=dict(color=_BLUE, width=1.2)),
        row=2, col=1,
    )
    fig.add_hline(y=70, line=dict(color=_RED,   width=1, dash="dot"), row=2, col=1)
    fig.add_hline(y=30, line=dict(color=_GREEN, width=1, dash="dot"), row=2, col=1)
    fig.add_hrect(y0=30, y1=70, fillcolor="#374151", opacity=0.15, line_width=0, row=2, col=1)

    vol_colors = [_RED if c >= o else _GREEN for c, o in zip(df["close"], df["open"])]
    fig.add_trace(
        go.Bar(x=x, y=df["volume"], name="量", marker_color=vol_colors, opacity=0.75),
        row=3, col=1,
    )

    fig.update_layout(
        template="plotly_dark", paper_bgcolor=_BG, plot_bgcolor=_BG,
        height=660,
        margin=dict(l=10, r=10, t=36, b=10),
        showlegend=True,
        legend=dict(orientation="h", y=1.03, x=0, font=dict(size=11)),
        xaxis_rangeslider_visible=False,
        dragmode="pan",   # drag to pan — intuitive for chart navigation
    )
    fig.update_xaxes(gridcolor=_GRID, zeroline=False)
    fig.update_yaxes(gridcolor=_GRID, zeroline=False)

    # Plotly quick buttons are secondary. The Streamlit segmented control above
    # the chart is the source of truth because it can switch data sources too.
    fig.update_xaxes(
        rangeselector=dict(
            buttons=_RS_BUTTONS,
            **_RS_STYLE,
            x=0, xanchor="left",
            y=1.08, yanchor="bottom",
        ),
        row=1, col=1,
    )
    return fig
