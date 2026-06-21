"""Signal engine rule-trigger tests using synthetic bar data."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _seed_bars(db, symbol, closes, volumes=None):
    n = len(closes)
    volumes = volumes if volumes is not None else [1_000_000] * n
    base = pd.Timestamp("2024-01-01", tz="UTC")
    for i, (c, v) in enumerate(zip(closes, volumes)):
        ts = (base + pd.Timedelta(days=i)).strftime("%Y-%m-%dT%H:%M:%fZ")
        db.upsert_bar(symbol, "1Day", open=c, high=c * 1.01, low=c * 0.99,
                      close=c, volume=v, timestamp=ts, source="test")


def test_break_below_ma20_warning_not_queued_for_ai(temp_db):
    """Phase 2 rule: a WARNING signal with no holding / no watchlist context is
    recorded for display only — it must NOT burn AI tokens (status stays 'new').
    Only CRITICAL signals on holdings / high_focus names go to 'pending_ai'."""
    from db import database as db
    from services import signal_engine
    # Flat at 100 (so MA20≈100), then a final close that drops below.
    closes = [100.0] * 40 + [90.0]
    _seed_bars(db, "TST", closes)
    n = signal_engine.evaluate_symbol("TST", None, None)
    assert n >= 1
    sigs = db.query("SELECT * FROM signals WHERE symbol='TST'")
    types = {s["signal_type"] for s in sigs}
    assert "break_below_ma20" in types
    brk = [s for s in sigs if s["signal_type"] == "break_below_ma20"][0]
    assert brk["severity"] == "warning"
    # No holding / no watch → never queued for AI.
    assert all(s["status"] == "new" for s in sigs)


def test_high_focus_entered_buy_zone_queues_ai(temp_db):
    """A high_focus watchlist name entering its target buy band is CRITICAL and
    must be queued for AI analysis."""
    from db import database as db
    from services import signal_engine
    closes = [50.0] * 40 + [48.0]
    _seed_bars(db, "BUY", closes)
    watch = {"symbol": "BUY", "category": "high_focus",
             "target_buy_low": 47.0, "target_buy_high": 49.0}
    signal_engine.evaluate_symbol("BUY", None, watch)
    sigs = db.query("SELECT * FROM signals WHERE symbol='BUY'")
    ez = [s for s in sigs if s["signal_type"] == "entered_buy_zone"]
    assert ez and ez[0]["severity"] == "critical" and ez[0]["status"] == "pending_ai"


def test_volume_surge_detected(temp_db):
    from db import database as db
    from services import signal_engine
    closes = list(np.linspace(100, 105, 40))
    vols = [1_000_000] * 39 + [5_000_000]
    _seed_bars(db, "VOL", closes, vols)
    signal_engine.evaluate_symbol("VOL", None, None)
    types = {s["signal_type"] for s in db.query("SELECT * FROM signals WHERE symbol='VOL'")}
    assert "volume_surge" in types


def test_near_stop_loss_for_holding(temp_db):
    from db import database as db
    from services import signal_engine
    closes = [50.0] * 40 + [50.5]
    _seed_bars(db, "STP", closes)
    holding = {"symbol": "STP", "avg_cost": 60.0, "stop_loss": 50.0, "take_profit": 80.0}
    signal_engine.evaluate_symbol("STP", holding, None)
    sigs = db.query("SELECT * FROM signals WHERE symbol='STP'")
    types = {s["signal_type"] for s in sigs}
    assert "near_stop_loss" in types
    crit = [s for s in sigs if s["signal_type"] == "near_stop_loss"][0]
    assert crit["severity"] == "critical" and crit["status"] == "pending_ai"


def test_persists_indicator_snapshot(temp_db):
    from db import database as db
    from services import signal_engine
    closes = list(np.linspace(100, 120, 80))
    _seed_bars(db, "IND", closes)
    signal_engine.evaluate_symbol("IND", None, None)
    rows = db.query("SELECT * FROM technical_indicators WHERE symbol='IND'")
    assert len(rows) == 1 and rows[0]["ma20"] is not None
