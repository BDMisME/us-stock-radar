"""us-stock-radar — Streamlit dashboard entrypoint.

Run from the project root:  streamlit run app/main.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the project root importable when launched via `streamlit run app/main.py`.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from db import database as db  # noqa: E402
from app.components import ui  # noqa: E402
from app.views import (ai_analyst, news, overview, portfolio,  # noqa: E402
                       settings as settings_view, signals, watchlist)

st.set_page_config(page_title="US Stock Radar", page_icon="📡", layout="wide")

# Ensure tables exist so a fresh clone renders without a manual init step.
db.init_db()

ui.inject_css()

PAGES = {
    "總覽": overview.render,
    "持股": portfolio.render,
    "觀察名單": watchlist.render,
    "訊號": signals.render,
    "AI 分析師": ai_analyst.render,
    "新聞": news.render,
    "設定": settings_view.render,
}

with st.sidebar:
    st.markdown('<div class="radar-title"><span>📡</span> US STOCK RADAR</div>', unsafe_allow_html=True)
    st.markdown('<div class="radar-sub">個人美股 AI 看盤雷達</div>', unsafe_allow_html=True)
    from config.settings import settings as _settings
    if _settings.app_credit_name:
        _credit = f'Powered by <strong>{_settings.app_credit_name}</strong>'
    else:
        _credit = ('Open-source · MIT<br>'
                   '<a href="https://github.com/BDMisME/us-stock-radar" '
                   'target="_blank">GitHub ↗</a>')
    st.markdown(f'<div class="radar-credit">{_credit}</div>', unsafe_allow_html=True)
    st.divider()
    choice = st.radio("頁面", list(PAGES.keys()), label_visibility="collapsed")
    st.divider()
    n_hold = db.query_one("SELECT COUNT(*) c FROM holdings WHERE active=1")["c"]
    n_watch = db.query_one("SELECT COUNT(*) c FROM watchlist WHERE active=1")["c"]
    st.caption(f"持股 {n_hold} · 觀察 {n_watch}/50")
    st.caption("僅供研究監控 · 不下單 · 不保證獲利")

try:
    PAGES[choice]()
except Exception as exc:  # surface errors in-page rather than a blank screen
    st.error(f"頁面載入發生錯誤：{exc}")
    st.exception(exc)
