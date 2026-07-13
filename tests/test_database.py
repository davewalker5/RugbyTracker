from __future__ import annotations

import sqlite3

import pytest

from rugby_tracker.config import PROJECT_ROOT, database_path
from rugby_tracker.database import apply_migrations, connect


def test_database_is_empty_after_first_migration(connection):
    for table in ("venues", "teams", "competitions", "referees", "matches"):
        assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    competition_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(competitions)").fetchall()
    }
    assert "ruleset" in competition_columns
    assert connection.execute(
        "SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'standings'"
    ).fetchone()[0] == 0


def test_migrations_are_repeatable(database):
    apply_migrations(database)
    apply_migrations(database)
    assert connect(database).execute("SELECT count(*) FROM venues").fetchone()[0] == 0


def test_foreign_keys_are_enforced(connection):
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO teams(name, gender, home_venue_id) VALUES (?, ?, ?)",
            ("Nowhere RFC", "Men", 999),
        )


def test_database_path_uses_environment_override(monkeypatch, tmp_path):
    override = tmp_path / "custom.db"
    monkeypatch.setenv("RUGBY_TRACKER_DB", str(override))
    assert database_path() == override
    monkeypatch.delenv("RUGBY_TRACKER_DB")
    assert database_path() == PROJECT_ROOT / "data" / "rugbytracker.db"
