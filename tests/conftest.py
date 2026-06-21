"""Shared pytest fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """A throwaway SQLite DB pointed at by the settings + database module."""
    db_file = tmp_path / "test.sqlite"
    from config.settings import settings
    monkeypatch.setattr(settings, "db_path", str(db_file), raising=False)

    from db import database as db
    # Force every helper to use this file by patching db_file resolution.
    monkeypatch.setattr(type(settings), "db_file",
                        property(lambda self: db_file), raising=False)
    db.init_db()
    return db_file
