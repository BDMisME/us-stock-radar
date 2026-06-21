"""Initialise the SQLite database (create all tables). Idempotent."""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running as `python scripts/init_db.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings  # noqa: E402
from db import database as db  # noqa: E402


def main() -> None:
    db.init_db()
    tables = db.query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    print(f"Database initialised at: {settings.db_file}")
    print("Tables:")
    for t in tables:
        print(f"  - {t['name']}")


if __name__ == "__main__":
    main()
