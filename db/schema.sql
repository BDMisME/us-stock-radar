-- us-stock-radar — SQLite schema (v1)
-- All timestamps are stored as ISO-8601 UTC strings unless noted.

-- ---------------------------------------------------------------------------
-- holdings: stocks the user actually owns
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS holdings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT    NOT NULL,
    name          TEXT,
    shares        REAL    NOT NULL DEFAULT 0,
    avg_cost      REAL    NOT NULL DEFAULT 0,
    buy_date      TEXT,
    category      TEXT,                 -- long_term / swing  (legacy: core → long_term)
    group_name    TEXT,
    theme_tags    TEXT,                 -- comma-separated or JSON
    strategy_type TEXT,
    stop_loss     REAL,
    take_profit   REAL,
    target_price  REAL,
    notes         TEXT,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_holdings_symbol ON holdings(symbol);

-- ---------------------------------------------------------------------------
-- watchlist: stocks being watched (high focus + general)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS watchlist (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT    NOT NULL,
    name            TEXT,
    category        TEXT,                 -- high_focus / general
    group_name      TEXT,
    theme_tags      TEXT,
    watch_level     INTEGER NOT NULL DEFAULT 1,  -- 1..5 priority
    target_buy_low  REAL,
    target_buy_high REAL,
    reason          TEXT,
    ai_enabled      INTEGER NOT NULL DEFAULT 1,
    alert_enabled   INTEGER NOT NULL DEFAULT 1,
    active          INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_watchlist_symbol ON watchlist(symbol);
CREATE INDEX IF NOT EXISTS idx_watchlist_category ON watchlist(category);

-- ---------------------------------------------------------------------------
-- price_ticks: latest trades / quotes (real-time + polled)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS price_ticks (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol    TEXT NOT NULL,
    price     REAL,
    bid       REAL,
    ask       REAL,
    volume    REAL,
    source    TEXT,                       -- alpaca / finnhub / fmp / yfinance
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_ticks_symbol_ts ON price_ticks(symbol, timestamp);

-- ---------------------------------------------------------------------------
-- bars: OHLCV candles per timeframe
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bars (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol    TEXT NOT NULL,
    timeframe TEXT NOT NULL,              -- 1Day / 1Hour / etc.
    open      REAL,
    high      REAL,
    low       REAL,
    close     REAL,
    volume    REAL,
    timestamp TEXT NOT NULL,
    source    TEXT,
    UNIQUE(symbol, timeframe, timestamp)
);
CREATE INDEX IF NOT EXISTS idx_bars_symbol_tf_ts ON bars(symbol, timeframe, timestamp);

-- ---------------------------------------------------------------------------
-- technical_indicators: computed snapshot per symbol/timeframe
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS technical_indicators (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol            TEXT NOT NULL,
    timeframe         TEXT NOT NULL,
    ma5               REAL,
    ma10              REAL,
    ma20              REAL,
    ma60              REAL,
    ma120             REAL,
    rsi14             REAL,
    macd              REAL,
    macd_signal       REAL,
    macd_hist         REAL,
    bb_upper          REAL,
    bb_middle         REAL,
    bb_lower          REAL,
    vwap              REAL,
    volume_ratio      REAL,
    distance_ma20_pct REAL,
    distance_ma60_pct REAL,
    timestamp         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_ti_symbol_tf_ts ON technical_indicators(symbol, timeframe, timestamp);

-- ---------------------------------------------------------------------------
-- signals: events detected by the rules engine (also the AI work queue)
-- status flow: new -> pending_ai -> analyzed | ignored
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS signals (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol                  TEXT NOT NULL,
    signal_type             TEXT NOT NULL,
    severity                TEXT NOT NULL DEFAULT 'info',  -- info / warning / critical
    title                   TEXT,
    description             TEXT,
    price                   REAL,
    indicator_snapshot_json TEXT,
    source                  TEXT,
    status                  TEXT NOT NULL DEFAULT 'new',
    created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);

-- ---------------------------------------------------------------------------
-- ai_analysis_logs: structured output from the AI analyst
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_analysis_logs (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol                 TEXT NOT NULL,
    analysis_type          TEXT,           -- event / intraday / preopen / close
    trigger_type           TEXT,           -- signal / schedule / manual
    recommendation         TEXT,
    risk_level             TEXT,           -- low / medium / high
    action                 TEXT,           -- hold / buy_watch / add / trim / sell / wait
    summary                TEXT,
    reasoning              TEXT,
    invalidation_condition TEXT,
    next_watch_price       REAL,
    input_snapshot_json    TEXT,
    model                  TEXT,
    input_tokens           INTEGER,
    output_tokens          INTEGER,
    created_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_ai_symbol ON ai_analysis_logs(symbol);
CREATE INDEX IF NOT EXISTS idx_ai_created ON ai_analysis_logs(created_at);

-- ---------------------------------------------------------------------------
-- news_items
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS news_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT,
    source          TEXT,
    url             TEXT UNIQUE,
    published_at    TEXT,
    summary         TEXT,
    related_symbols TEXT,
    sentiment       TEXT,                  -- bullish / bearish / neutral / uncertain
    impact_level    TEXT,                  -- low / medium / high
    ai_summary      TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_news_published ON news_items(published_at);

-- ---------------------------------------------------------------------------
-- alerts: notification queue
-- status flow: pending -> sent | failed | skipped
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alerts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol     TEXT,
    alert_type TEXT,
    title      TEXT,
    message    TEXT,
    channel    TEXT,                       -- telegram / email / all
    status     TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    sent_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);

-- ---------------------------------------------------------------------------
-- api_usage_logs: provider call accounting (tokens / cost)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS api_usage_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    provider      TEXT,
    endpoint      TEXT,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    cost_estimate REAL,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_usage_provider ON api_usage_logs(provider, created_at);
