"""Shared UI helpers for the Streamlit dashboard."""
from __future__ import annotations

import html
from typing import Literal

import streamlit as st

TW_UP = "#F87171"
TW_DOWN = "#4ADE80"
NEUTRAL = "#9CA3AF"


def inject_css() -> None:
    """Apply app-wide styling."""
    st.markdown(
        """
<style>
  :root {
    --radar-bg: #0B0F14;
    --radar-panel: #111827;
    --radar-panel-soft: #151B24;
    --radar-border: #263241;
    --radar-text: #D7E0EA;
    --radar-muted: #8B98A8;
    --radar-up: #F87171;
    --radar-down: #4ADE80;
    --radar-blue: #60A5FA;
    --radar-amber: #FBBF24;
  }
  .block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1380px; }
  h1, h2, h3 { letter-spacing: 0; }
  [data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; }
  [data-testid="stSidebar"] {
    border-right: 1px solid var(--radar-border);
    background: linear-gradient(180deg, #0D131B 0%, #0B0F14 100%);
  }
  [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] .stRadio label { font-size: 1.02rem !important; }
  div[data-testid="stVerticalBlockBorderWrapper"],
  div[data-testid="stExpander"] {
    border-color: var(--radar-border) !important;
    border-radius: 8px !important;
    background: var(--radar-panel);
  }
  div[data-testid="stDataFrame"] {
    border: 1px solid var(--radar-border);
    border-radius: 8px;
    overflow: hidden;
  }
  .radar-title {
    font-size: 1.35rem;
    font-weight: 760;
    color: #EAF2FF;
    letter-spacing: 0;
    line-height: 1.2;
  }
  .radar-title span { color: var(--radar-blue); }
  .radar-sub { color: var(--radar-muted); font-size: 0.82rem; margin-top: 0.15rem; }
  .radar-credit {
    color: var(--radar-muted);
    font-size: 0.72rem;
    line-height: 1.45;
    margin-top: 0.55rem;
  }
  .radar-credit strong { color: #EAF2FF; font-weight: 650; }
  .radar-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    border: 1px solid var(--radar-border);
    border-radius: 999px;
    padding: 0.2rem 0.55rem;
    color: var(--radar-muted);
    background: #0F1621;
    font-size: 0.78rem;
    white-space: nowrap;
  }
  .radar-card {
    border: 1px solid var(--radar-border);
    border-radius: 8px;
    padding: 0.9rem 1rem;
    background: linear-gradient(180deg, #121A24 0%, #0F151E 100%);
    min-height: 105px;
  }
  .radar-card .label { color: var(--radar-muted); font-size: 0.84rem; }
  .radar-card .value {
    color: var(--radar-text);
    font-size: clamp(1.35rem, 2.1vw, 1.95rem);
    line-height: 1.15;
    font-weight: 760;
    margin-top: 0.35rem;
    font-variant-numeric: tabular-nums;
    overflow-wrap: anywhere;
  }
  .radar-card .delta {
    margin-top: 0.35rem;
    font-size: 0.92rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }
  .radar-card .hint { color: var(--radar-muted); font-size: 0.78rem; margin-top: 0.2rem; }
  .radar-empty {
    border: 1px dashed var(--radar-border);
    border-radius: 8px;
    padding: 1rem;
    background: #0E141C;
    color: var(--radar-muted);
  }
  .radar-section-title {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    margin: 0.6rem 0 0.35rem;
  }
  .radar-section-title strong { color: #EAF2FF; }
</style>
""",
        unsafe_allow_html=True,
    )


def _sign_color(value: float | int | None) -> str:
    if value is None:
        return NEUTRAL
    if value > 0:
        return TW_UP
    if value < 0:
        return TW_DOWN
    return NEUTRAL


def metric_card(
    label: str,
    value: str,
    delta: str | None = None,
    delta_value: float | int | None = None,
    hint: str | None = None,
) -> None:
    """Render a metric using Taiwan market colors: red up, green down."""
    delta_html = ""
    if delta is not None:
        delta_html = (
            f'<div class="delta" style="color:{_sign_color(delta_value)}">'
            f"{html.escape(delta)}</div>"
        )
    hint_html = f'<div class="hint">{html.escape(hint)}</div>' if hint else ""
    st.markdown(
        f"""
<div class="radar-card">
  <div class="label">{html.escape(label)}</div>
  <div class="value">{html.escape(value)}</div>
  {delta_html}
  {hint_html}
</div>
""",
        unsafe_allow_html=True,
    )


def empty_state(title: str, body: str, tone: Literal["info", "warning"] = "info") -> None:
    border = "#35506B" if tone == "info" else "#7C5B1B"
    st.markdown(
        f"""
<div class="radar-empty" style="border-color:{border}">
  <strong>{html.escape(title)}</strong><br>
  {html.escape(body)}
</div>
""",
        unsafe_allow_html=True,
    )


def section_header(title: str, meta: str | None = None) -> None:
    meta_html = f'<span class="radar-pill">{html.escape(meta)}</span>' if meta else ""
    st.markdown(
        f'<div class="radar-section-title"><strong>{html.escape(title)}</strong>{meta_html}</div>',
        unsafe_allow_html=True,
    )
