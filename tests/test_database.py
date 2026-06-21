"""Database CRUD + queue-helper tests against a temp DB."""
from __future__ import annotations


def test_init_creates_tables(temp_db):
    from db import database as db
    names = {r["name"] for r in db.query(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("holdings", "watchlist", "price_ticks", "bars",
              "technical_indicators", "signals", "ai_analysis_logs",
              "news_items", "alerts", "api_usage_logs"):
        assert t in names
    holding_cols = {r["name"] for r in db.query("PRAGMA table_info(holdings)")}
    watch_cols = {r["name"] for r in db.query("PRAGMA table_info(watchlist)")}
    assert "group_name" in holding_cols
    assert "group_name" in watch_cols


def test_holdings_and_realtime_set(temp_db):
    from db import database as db
    db.insert("holdings", {"symbol": "AAPL", "shares": 10, "avg_cost": 100,
                           "category": "core", "active": 1})
    db.insert("watchlist", {"symbol": "PLTR", "category": "high_focus",
                            "watch_level": 5, "active": 1})
    db.insert("watchlist", {"symbol": "INTC", "category": "general",
                            "watch_level": 1, "active": 1})
    rt = db.realtime_symbols()
    assert "AAPL" in rt and "PLTR" in rt and "INTC" not in rt
    assert db.general_watch_symbols() == ["INTC"]


def test_signal_queue_flow(temp_db):
    from db import database as db
    sid = db.create_signal("NVDA", "break_below_ma20", severity="warning",
                           title="t", description="d", price=100.0,
                           indicator_snapshot={"ma20": 101}, pending_ai=True)
    pend = db.pending_ai_signals()
    assert len(pend) == 1 and pend[0]["id"] == sid
    db.set_signal_status(sid, "analyzed")
    assert db.pending_ai_signals() == []


def test_alert_queue_flow(temp_db):
    from db import database as db
    aid = db.create_alert(symbol="NVDA", alert_type="ai_analysis",
                          title="t", message="m", channel="all")
    assert len(db.pending_alerts()) == 1
    db.mark_alert(aid, "sent")
    assert db.pending_alerts() == []


def test_tick_and_latest_price(temp_db):
    from db import database as db
    db.record_tick("NVDA", price=120.5, source="test")
    db.record_tick("NVDA", price=121.0, source="test")
    assert db.latest_price("NVDA") == 121.0


def test_prune_price_ticks(temp_db):
    from db import database as db
    db.execute(
        "INSERT INTO price_ticks (symbol, price, source, timestamp) VALUES (?,?,?,?)",
        ("OLD", 1.0, "test", "2000-01-01T00:00:000000Z"),
    )
    db.record_tick("NEW", price=2.0, source="test")
    assert db.prune_price_ticks(older_than_hours=72) == 1
    rows = db.query("SELECT symbol FROM price_ticks ORDER BY symbol")
    assert [r["symbol"] for r in rows] == ["NEW"]


def test_upsert_bar_idempotent(temp_db):
    from db import database as db
    for _ in range(2):
        db.upsert_bar("NVDA", "1Day", open=1, high=2, low=0.5, close=1.5,
                      volume=100, timestamp="2024-01-01T00:00:00.000Z")
    rows = db.query("SELECT * FROM bars WHERE symbol='NVDA'")
    assert len(rows) == 1


def test_usage_count_today(temp_db):
    from db import database as db
    db.log_api_usage("manual", "stock_analysis")
    db.log_api_usage("manual", "news_search")
    assert db.usage_count_today("manual", "stock_analysis") == 1
    assert db.usage_count_today("manual", "news_search") == 1
    assert db.usage_count_today("manual", "missing") == 0


def test_group_names(temp_db):
    from db import database as db
    db.insert("holdings", {"symbol": "AAPL", "shares": 10, "avg_cost": 100,
                           "group_name": "AI", "active": 1})
    db.insert("holdings", {"symbol": "JPM", "shares": 1, "avg_cost": 100,
                           "group_name": "金融", "active": 1})
    db.insert("watchlist", {"symbol": "NVDA", "category": "high_focus",
                            "group_name": "AI", "watch_level": 5, "active": 1})
    assert db.group_names("holdings") == ["AI", "金融"]
    assert db.group_names("watchlist") == ["AI"]
