#!/bin/bash
set -e

mkdir -p "$(dirname "${DB_PATH:-./db/us_stock_radar.sqlite}")"

echo "[start] Initialising database..."
python scripts/init_db.py

echo "[start] Seeding demo data (idempotent)..."
python scripts/seed_demo.py

echo "[start] Migrating holding categories (core → long_term, idempotent)..."
python scripts/migrate_holding_category.py || echo "[start] migration had issues (continuing)"

echo "[start] Backfilling daily bars + indicators (so the dashboard has data immediately)..."
python scripts/backfill.py || echo "[start] backfill had issues (continuing; workers will retry)"

echo "[start] Launching background workers..."
python services/market_monitor.py  &
python services/signal_engine.py   &
python services/ai_worker.py       &
python services/alert_worker.py    &
python services/scheduler.py       &

echo "[start] Starting Streamlit dashboard on :8501"
exec streamlit run app/main.py \
  --server.address=0.0.0.0 \
  --server.port=8501 \
  --server.headless=true
