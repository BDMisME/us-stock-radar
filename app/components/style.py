"""Shared table styling — Taiwan market color convention (紅漲 / 綠跌).

Per the user's preference: positive numbers (漲) are RED, negative (跌) are
GREEN — the opposite of the US convention. Applied to gain/loss and day-change
columns via a pandas Styler that st.dataframe renders.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

TW_UP = "#F87171"     # red  → 漲 / 正值
TW_DOWN = "#4ADE80"   # green → 跌 / 負值
NEUTRAL = "#9CA3AF"


def _color(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return f"color: {NEUTRAL}"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return ""
    if v > 0:
        return f"color: {TW_UP}; font-weight: 600"
    if v < 0:
        return f"color: {TW_DOWN}; font-weight: 600"
    return f"color: {NEUTRAL}"


def style_table(df: pd.DataFrame, color_cols: Iterable[str],
                pct_cols: Iterable[str] = (), money_cols: Iterable[str] = (),
                price_cols: Iterable[str] = ()):
    """Return a Styler: red/green on `color_cols`, formatted numbers, right-aligned."""
    color_cols = [c for c in color_cols if c in df.columns]
    fmt: dict = {}
    for c in pct_cols:
        if c in df.columns:
            fmt[c] = lambda x: "—" if pd.isna(x) else f"{x:+.2f}%"
    for c in money_cols:
        if c in df.columns:
            fmt[c] = lambda x: "—" if pd.isna(x) else f"${x:,.0f}"
    for c in price_cols:
        if c in df.columns:
            fmt[c] = lambda x: "—" if pd.isna(x) else f"${x:,.2f}"

    sty = df.style
    if color_cols:
        sty = sty.map(_color, subset=color_cols)
    if fmt:
        sty = sty.format(fmt, na_rep="—")
    sty = sty.set_properties(**{"text-align": "right"})
    return sty
