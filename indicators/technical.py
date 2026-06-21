"""Technical indicator calculations.

Pure functions over an OHLCV DataFrame. We prefer pandas-ta when available but
fall back to hand-rolled pandas so the project installs cleanly without TA-Lib.

Expected input DataFrame columns (case-insensitive): open, high, low, close,
volume — ordered oldest -> newest.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

try:  # pandas-ta is optional; we degrade to manual pandas if it's missing.
    import pandas_ta as pta  # noqa: F401
    _HAS_PTA = True
except Exception:  # pragma: no cover - depends on environment
    _HAS_PTA = False


def _norm(df: pd.DataFrame) -> pd.DataFrame:
    """Lower-case columns and ensure a clean numeric close/volume series."""
    out = df.rename(columns={c: c.lower() for c in df.columns}).copy()
    for col in ("open", "high", "low", "close", "volume"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    # Wilder's smoothing
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100 - (100 / (1 + rs))
    # When avg_loss == 0 (only gains), RSI is 100.
    out[avg_loss == 0] = 100.0
    return out


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "macd_signal": signal_line, "macd_hist": hist})


def bollinger(series: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    middle = sma(series, window)
    std = series.rolling(window=window, min_periods=window).std(ddof=0)
    return pd.DataFrame({
        "bb_upper": middle + num_std * std,
        "bb_middle": middle,
        "bb_lower": middle - num_std * std,
    })


def vwap(df: pd.DataFrame) -> pd.Series:
    """Cumulative VWAP over the supplied window (typical price * volume)."""
    d = _norm(df)
    typical = (d["high"] + d["low"] + d["close"]) / 3
    cum_vol = d["volume"].cumsum()
    cum_pv = (typical * d["volume"]).cumsum()
    return cum_pv / cum_vol.replace(0.0, np.nan)


def volume_ratio(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Latest volume relative to its N-day average."""
    d = _norm(df)
    avg = d["volume"].rolling(window=window, min_periods=1).mean()
    return d["volume"] / avg.replace(0.0, np.nan)


def _last(series: pd.Series) -> Optional[float]:
    if series is None or series.empty:
        return None
    val = series.iloc[-1]
    if pd.isna(val):
        return None
    return float(val)


def compute_indicators(df: pd.DataFrame) -> dict[str, Any]:
    """Compute the full indicator snapshot used by signals/AI/dashboard.

    Returns a dict with the column names matching the technical_indicators
    table. Values that cannot be computed (insufficient history) are None.
    """
    d = _norm(df).dropna(subset=["close"])
    if d.empty:
        return {}

    close = d["close"]
    snapshot: dict[str, Any] = {
        "ma5": _last(sma(close, 5)),
        "ma10": _last(sma(close, 10)),
        "ma20": _last(sma(close, 20)),
        "ma60": _last(sma(close, 60)),
        "ma120": _last(sma(close, 120)),
        "rsi14": _last(rsi(close, 14)),
    }

    macd_df = macd(close)
    snapshot["macd"] = _last(macd_df["macd"])
    snapshot["macd_signal"] = _last(macd_df["macd_signal"])
    snapshot["macd_hist"] = _last(macd_df["macd_hist"])

    bb = bollinger(close)
    snapshot["bb_upper"] = _last(bb["bb_upper"])
    snapshot["bb_middle"] = _last(bb["bb_middle"])
    snapshot["bb_lower"] = _last(bb["bb_lower"])

    if {"high", "low", "volume"}.issubset(d.columns):
        snapshot["vwap"] = _last(vwap(d))
        snapshot["volume_ratio"] = _last(volume_ratio(d))
    else:
        snapshot["vwap"] = None
        snapshot["volume_ratio"] = None

    last_close = float(close.iloc[-1])
    ma20, ma60 = snapshot["ma20"], snapshot["ma60"]
    snapshot["distance_ma20_pct"] = (
        round((last_close - ma20) / ma20 * 100, 4) if ma20 else None
    )
    snapshot["distance_ma60_pct"] = (
        round((last_close - ma60) / ma60 * 100, 4) if ma60 else None
    )
    snapshot["last_close"] = last_close
    return snapshot


def macd_cross(df: pd.DataFrame) -> Optional[str]:
    """Detect a MACD cross on the latest bar: 'golden', 'death', or None."""
    d = _norm(df).dropna(subset=["close"])
    if len(d) < 2:
        return None
    m = macd(d["close"])
    hist = m["macd_hist"].dropna()
    if len(hist) < 2:
        return None
    prev, cur = hist.iloc[-2], hist.iloc[-1]
    if prev <= 0 < cur:
        return "golden"
    if prev >= 0 > cur:
        return "death"
    return None
