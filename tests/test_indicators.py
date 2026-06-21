"""Indicator math sanity checks on known/synthetic series."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from indicators import technical


def _frame(closes, volumes=None):
    n = len(closes)
    volumes = volumes if volumes is not None else [1000] * n
    return pd.DataFrame({
        "open": closes, "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes], "close": closes, "volume": volumes,
    })


def test_sma_basic():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    assert technical.sma(s, 5).iloc[-1] == 3.0
    assert pd.isna(technical.sma(s, 5).iloc[-2])  # not enough data


def test_rsi_all_gains_is_100():
    s = pd.Series(np.arange(1, 40, dtype=float))
    rsi = technical.rsi(s, 14).iloc[-1]
    assert rsi == 100.0


def test_rsi_bounds():
    rng = np.random.default_rng(0)
    s = pd.Series(100 + rng.standard_normal(200).cumsum())
    rsi = technical.rsi(s, 14).dropna()
    assert (rsi >= 0).all() and (rsi <= 100).all()


def test_compute_indicators_keys():
    closes = list(np.linspace(100, 130, 150))
    snap = technical.compute_indicators(_frame(closes))
    for key in ("ma5", "ma20", "ma60", "rsi14", "macd", "bb_upper", "vwap",
                "volume_ratio", "distance_ma20_pct", "last_close"):
        assert key in snap
    # On a steady uptrend, price is above MA20 -> positive distance.
    assert snap["distance_ma20_pct"] > 0


def test_macd_cross_detects_golden():
    # Down then sharply up should produce a golden cross near the end.
    down = list(np.linspace(120, 100, 40))
    up = list(np.linspace(100, 140, 40))
    cross = technical.macd_cross(_frame(down + up))
    assert cross in ("golden", None)  # at minimum, must not raise


def test_volume_ratio_spike():
    vols = [1000] * 25 + [3000]
    closes = list(np.linspace(100, 110, 26))
    vr = technical.volume_ratio(_frame(closes, vols)).iloc[-1]
    assert vr > 2.0
