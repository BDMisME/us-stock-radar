"""One-time migration: holdings.category core/high_focus → long_term.

Safe to run multiple times (idempotent). Run once after deploying the Phase 4
category rename so existing demo/production data is updated.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings  # noqa: E402
from db import database as db         # noqa: E402


def migrate() -> None:
    db.init_db()
    # Migrate legacy values → long_term
    db.execute(
        "UPDATE holdings SET category='long_term', updated_at=? "
        "WHERE category IN ('core', 'high_focus') OR category IS NULL",
        (db.utcnow_iso(),),
    )
    n = db.query_one("SELECT changes() c")
    changed = n["c"] if n else 0
    total = db.query_one("SELECT COUNT(*) c FROM holdings WHERE active=1")
    print(f"Migration complete: {changed} rows updated → 'long_term'")
    print(f"Total active holdings: {total['c'] if total else 0}")


if __name__ == "__main__":
    migrate()
