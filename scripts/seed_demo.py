"""Seed the database with a demo universe: 20 holdings + 80 watchlist
(10 high-focus + 70 general), from config/symbols.example.json.

Idempotent: skips symbols that already exist (by symbol+category).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import PROJECT_ROOT  # noqa: E402
from db import database as db  # noqa: E402

SEED_FILE = PROJECT_ROOT / "config" / "symbols.example.json"


def _holding_exists(symbol: str) -> bool:
    return db.query_one("SELECT id FROM holdings WHERE symbol=?", (symbol,)) is not None


def _watch_exists(symbol: str) -> bool:
    return db.query_one("SELECT id FROM watchlist WHERE symbol=?", (symbol,)) is not None


def main() -> None:
    db.init_db()
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))

    h_added = 0
    for h in data["holdings"]:
        if _holding_exists(h["symbol"]):
            continue
        db.insert("holdings", {
            "symbol": h["symbol"], "name": h.get("name"), "shares": h.get("shares", 0),
            "avg_cost": h.get("avg_cost", 0), "category": h.get("category", "long_term"),
            "theme_tags": h.get("theme_tags"), "stop_loss": h.get("stop_loss"),
            "take_profit": h.get("take_profit"), "target_price": h.get("target_price"),
            "active": 1, "created_at": db.utcnow_iso(), "updated_at": db.utcnow_iso(),
        })
        h_added += 1

    w_added = 0
    for w in data["high_focus"]:
        if _watch_exists(w["symbol"]):
            continue
        db.insert("watchlist", {
            "symbol": w["symbol"], "name": w.get("name"), "category": "high_focus",
            "theme_tags": w.get("theme_tags"), "watch_level": w.get("watch_level", 4),
            "target_buy_low": w.get("target_buy_low"), "target_buy_high": w.get("target_buy_high"),
            "reason": w.get("reason"), "ai_enabled": 1, "alert_enabled": 1, "active": 1,
            "created_at": db.utcnow_iso(), "updated_at": db.utcnow_iso(),
        })
        w_added += 1

    for symbol in data["general"]:
        if _watch_exists(symbol):
            continue
        db.insert("watchlist", {
            "symbol": symbol, "name": symbol, "category": "general", "watch_level": 1,
            "ai_enabled": 1, "alert_enabled": 1, "active": 1,
            "created_at": db.utcnow_iso(), "updated_at": db.utcnow_iso(),
        })
        w_added += 1

    n_hold = db.query_one("SELECT COUNT(*) c FROM holdings WHERE active=1")["c"]
    n_watch = db.query_one("SELECT COUNT(*) c FROM watchlist WHERE active=1")["c"]
    n_focus = db.query_one("SELECT COUNT(*) c FROM watchlist WHERE active=1 AND category='high_focus'")["c"]
    n_general = db.query_one("SELECT COUNT(*) c FROM watchlist WHERE active=1 AND category='general'")["c"]

    print(f"Added {h_added} holdings, {w_added} watchlist entries.")
    print(f"Totals -> holdings: {n_hold}, watchlist: {n_watch} "
          f"(high_focus: {n_focus}, general: {n_general})")
    print(f"Realtime (Alpaca) symbol set: {len(db.realtime_symbols())} symbols.")


if __name__ == "__main__":
    main()
