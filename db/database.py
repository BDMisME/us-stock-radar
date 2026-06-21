"""SQLite access layer.

Several long-running processes (market_monitor, signal_engine, ai_worker,
alert_worker) plus Streamlit read/write the same file concurrently, so we run
in WAL mode with a busy timeout and keep every write in a short transaction.

The module exposes a thin set of helpers rather than an ORM — the schema is
small and stable, and explicit SQL keeps the data contract obvious.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional, Sequence

from config.settings import PROJECT_ROOT, settings

SCHEMA_PATH = PROJECT_ROOT / "db" / "schema.sql"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def _connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else settings.db_file
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


@contextmanager
def get_conn(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    """Context-managed connection. Commits on success, rolls back on error."""
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN;")
        yield conn
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[Path] = None) -> None:
    """Create all tables from schema.sql (idempotent)."""
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = _connect(db_path)
    try:
        conn.executescript(schema_sql)
        _ensure_column(conn, "holdings", "group_name", "TEXT")
        _ensure_column(conn, "watchlist", "group_name", "TEXT")
    finally:
        conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


# --------------------------------------------------------------------------
# Generic helpers
# --------------------------------------------------------------------------
def query(sql: str, params: Sequence[Any] = (), db_path: Optional[Path] = None) -> list[sqlite3.Row]:
    conn = _connect(db_path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def query_one(sql: str, params: Sequence[Any] = (), db_path: Optional[Path] = None) -> Optional[sqlite3.Row]:
    conn = _connect(db_path)
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def execute(sql: str, params: Sequence[Any] = (), db_path: Optional[Path] = None) -> int:
    """Run a single write. Returns lastrowid."""
    with get_conn(db_path) as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid


def insert(table: str, data: dict[str, Any], db_path: Optional[Path] = None) -> int:
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
    return execute(sql, tuple(data.values()), db_path)


def to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Symbol universe helpers
# --------------------------------------------------------------------------
def active_holdings(db_path: Optional[Path] = None) -> list[dict[str, Any]]:
    return to_dicts(query(
        "SELECT * FROM holdings WHERE active=1 ORDER BY COALESCE(group_name,''), symbol",
        db_path=db_path,
    ))


def active_watchlist(category: Optional[str] = None, db_path: Optional[Path] = None) -> list[dict[str, Any]]:
    if category:
        rows = query(
            "SELECT * FROM watchlist WHERE active=1 AND category=? "
            "ORDER BY COALESCE(group_name,''), watch_level DESC, symbol",
            (category,), db_path=db_path,
        )
    else:
        rows = query(
            "SELECT * FROM watchlist WHERE active=1 "
            "ORDER BY COALESCE(group_name,''), watch_level DESC, symbol",
            db_path=db_path,
        )
    return to_dicts(rows)


def group_names(table: str, db_path: Optional[Path] = None) -> list[str]:
    if table not in {"holdings", "watchlist"}:
        raise ValueError("table must be holdings or watchlist")
    rows = query(
        f"SELECT DISTINCT group_name FROM {table} "
        "WHERE active=1 AND group_name IS NOT NULL AND trim(group_name)<>'' "
        "ORDER BY group_name",
        db_path=db_path,
    )
    return [r["group_name"] for r in rows]


def realtime_symbols(limit: int = 30, db_path: Optional[Path] = None) -> list[str]:
    """The 30 names fed to the Alpaca IEX websocket: all holdings + high_focus
    watchlist, de-duplicated, capped at ``limit``."""
    holds = [h["symbol"] for h in active_holdings(db_path=db_path)]
    focus = [w["symbol"] for w in active_watchlist("high_focus", db_path=db_path)]
    seen: list[str] = []
    for s in holds + focus:
        if s not in seen:
            seen.append(s)
    return seen[:limit]


def general_watch_symbols(db_path: Optional[Path] = None) -> list[str]:
    return [w["symbol"] for w in active_watchlist("general", db_path=db_path)]


def all_tracked_symbols(db_path: Optional[Path] = None) -> list[str]:
    holds = [h["symbol"] for h in active_holdings(db_path=db_path)]
    watch = [w["symbol"] for w in active_watchlist(db_path=db_path)]
    out: list[str] = []
    for s in holds + watch:
        if s not in out:
            out.append(s)
    return out


# --------------------------------------------------------------------------
# Price / bar writers
# --------------------------------------------------------------------------
def record_tick(symbol: str, *, price: Optional[float] = None, bid: Optional[float] = None,
                ask: Optional[float] = None, volume: Optional[float] = None,
                source: str = "", db_path: Optional[Path] = None) -> int:
    return insert("price_ticks", {
        "symbol": symbol, "price": price, "bid": bid, "ask": ask,
        "volume": volume, "source": source, "timestamp": utcnow_iso(),
    }, db_path)


def prune_price_ticks(*, older_than_hours: int = 72,
                      db_path: Optional[Path] = None) -> int:
    """Delete stale raw ticks so frequent polling does not bloat SQLite."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=older_than_hours)).strftime(
        "%Y-%m-%dT%H:%M:%fZ"
    )
    with get_conn(db_path) as conn:
        cur = conn.execute("DELETE FROM price_ticks WHERE timestamp < ?", (cutoff,))
        return cur.rowcount


def latest_price(symbol: str, db_path: Optional[Path] = None) -> Optional[float]:
    """Most recent known price. Prefers a live/polled tick; when the market is
    closed and no tick exists, falls back to the latest daily-bar close so the
    UI always shows a price."""
    row = query_one(
        "SELECT price FROM price_ticks WHERE symbol=? AND price IS NOT NULL "
        "ORDER BY timestamp DESC LIMIT 1", (symbol,), db_path=db_path,
    )
    if row and row["price"] is not None:
        return row["price"]
    bar = query_one(
        "SELECT close FROM bars WHERE symbol=? AND timeframe='1Day' AND close IS NOT NULL "
        "ORDER BY timestamp DESC LIMIT 1", (symbol,), db_path=db_path,
    )
    return bar["close"] if bar else None


def upsert_bar(symbol: str, timeframe: str, *, open: float, high: float, low: float,
               close: float, volume: float, timestamp: str, source: str = "",
               db_path: Optional[Path] = None) -> None:
    execute(
        """INSERT INTO bars (symbol, timeframe, open, high, low, close, volume, timestamp, source)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(symbol, timeframe, timestamp) DO UPDATE SET
             open=excluded.open, high=excluded.high, low=excluded.low,
             close=excluded.close, volume=excluded.volume, source=excluded.source""",
        (symbol, timeframe, open, high, low, close, volume, timestamp, source),
        db_path,
    )


# --------------------------------------------------------------------------
# Signal queue helpers
# --------------------------------------------------------------------------
def create_signal(symbol: str, signal_type: str, *, severity: str = "info",
                  title: str = "", description: str = "", price: Optional[float] = None,
                  indicator_snapshot: Optional[dict] = None, source: str = "signal_engine",
                  pending_ai: bool = False, db_path: Optional[Path] = None) -> int:
    return insert("signals", {
        "symbol": symbol, "signal_type": signal_type, "severity": severity,
        "title": title, "description": description, "price": price,
        "indicator_snapshot_json": json.dumps(indicator_snapshot) if indicator_snapshot else None,
        "source": source,
        "status": "pending_ai" if pending_ai else "new",
        "created_at": utcnow_iso(),
    }, db_path)


def pending_ai_signals(limit: int = 20, db_path: Optional[Path] = None) -> list[dict[str, Any]]:
    return to_dicts(query(
        "SELECT * FROM signals WHERE status='pending_ai' ORDER BY created_at ASC LIMIT ?",
        (limit,), db_path=db_path,
    ))


def set_signal_status(signal_id: int, status: str, db_path: Optional[Path] = None) -> None:
    execute("UPDATE signals SET status=? WHERE id=?", (status, signal_id), db_path)


# --------------------------------------------------------------------------
# Alert queue helpers
# --------------------------------------------------------------------------
def create_alert(*, symbol: Optional[str], alert_type: str, title: str, message: str,
                 channel: str = "all", db_path: Optional[Path] = None) -> int:
    return insert("alerts", {
        "symbol": symbol, "alert_type": alert_type, "title": title,
        "message": message, "channel": channel, "status": "pending",
        "created_at": utcnow_iso(),
    }, db_path)


def pending_alerts(limit: int = 50, db_path: Optional[Path] = None) -> list[dict[str, Any]]:
    return to_dicts(query(
        "SELECT * FROM alerts WHERE status='pending' ORDER BY created_at ASC LIMIT ?",
        (limit,), db_path=db_path,
    ))


def mark_alert(alert_id: int, status: str, db_path: Optional[Path] = None) -> None:
    execute("UPDATE alerts SET status=?, sent_at=? WHERE id=?",
            (status, utcnow_iso(), alert_id), db_path)


# --------------------------------------------------------------------------
# AI / usage writers
# --------------------------------------------------------------------------
def log_ai_analysis(payload: dict[str, Any], db_path: Optional[Path] = None) -> int:
    payload = {**payload, "created_at": utcnow_iso()}
    return insert("ai_analysis_logs", payload, db_path)


def log_api_usage(provider: str, endpoint: str, *, input_tokens: int = 0,
                  output_tokens: int = 0, cost_estimate: float = 0.0,
                  db_path: Optional[Path] = None) -> int:
    return insert("api_usage_logs", {
        "provider": provider, "endpoint": endpoint, "input_tokens": input_tokens,
        "output_tokens": output_tokens, "cost_estimate": cost_estimate,
        "created_at": utcnow_iso(),
    }, db_path)


def usage_count_today(provider: str, endpoint: str, *, tz_offset_hours: int = 8,
                      db_path: Optional[Path] = None) -> int:
    """Count usage events for the Taiwan calendar day by default."""
    tz = timezone(timedelta(hours=tz_offset_hours))
    local_today = datetime.now(tz).date()
    start_local = datetime.combine(local_today, datetime.min.time(), tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
    end_utc = end_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
    row = query_one(
        "SELECT COUNT(*) c FROM api_usage_logs "
        "WHERE provider=? AND endpoint=? AND created_at >= ? AND created_at < ?",
        (provider, endpoint, start_utc, end_utc),
        db_path,
    )
    return int(row["c"] if row else 0)
