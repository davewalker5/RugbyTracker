from __future__ import annotations

import sqlite3

import pytest
from yoyo import get_backend, read_migrations

from rugby_tracker.config import PROJECT_ROOT, database_path, migrations_path
from rugby_tracker.database import apply_migrations, connect


def test_database_is_empty_after_first_migration(connection):
    for table in ("countries", "venues", "teams", "competitions", "referees", "matches"):
        assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    competition_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(competitions)").fetchall()
    }
    assert "ruleset" in competition_columns
    team_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(teams)").fetchall()
    }
    assert "country_id" in team_columns
    assert "country" not in team_columns
    assert connection.execute(
        "SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'standings'"
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT count(*) FROM competition_rulesets"
    ).fetchone()[0] == 7


def test_migrations_are_repeatable(database):
    apply_migrations(database)
    apply_migrations(database)
    assert connect(database).execute("SELECT count(*) FROM venues").fetchone()[0] == 0


def test_country_names_are_mandatory_and_case_insensitively_unique(connection):
    """Enforce the standalone countries table's name constraints.

    :param connection: Empty migrated test database connection.
    :return: None.
    """
    connection.execute("INSERT INTO countries(name) VALUES ('England')")

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO countries(name) VALUES ('ENGLAND')")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO countries(name) VALUES ('   ')")


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


def test_runtime_root_uses_environment_override(monkeypatch, tmp_path):
    """Runtime data and migrations can be rooted outside the installed package.

    :param monkeypatch: Pytest helper used to configure the runtime root.
    :param tmp_path: Temporary path used as the configured runtime root.
    :return: None.
    """
    monkeypatch.delenv("RUGBY_TRACKER_DB", raising=False)
    monkeypatch.setenv("RUGBY_TRACKER_ROOT", str(tmp_path))

    assert database_path() == tmp_path / "data" / "rugbytracker.db"
    assert migrations_path() == tmp_path / "migrations"


def test_team_country_migration_backfills_from_competition_membership(tmp_path):
    """Backfill PWR, W6N and other team countries using the requested rules.

    :param tmp_path: Temporary directory in which to create the legacy database.
    :return: None.
    """
    database = tmp_path / "legacy.db"
    backend = get_backend(f"sqlite:///{database.resolve()}")
    migrations = read_migrations(str(migrations_path()))
    with backend.lock():
        backend.apply_migrations(migrations[:3])

    connection = connect(database)
    connection.execute("INSERT INTO venues(id, name) VALUES (1, 'Ground')")
    connection.executemany(
        "INSERT INTO competitions(id, name, season, gender, ruleset) VALUES (?, ?, '2026', ?, ?)",
        ((1, "PWR", "Women", "pwr_2025_26"),
         (2, "W6N", "Women", "w6n"),
         (3, "Other", "Men", None)),
    )
    connection.executemany(
        "INSERT INTO teams(id, name, gender, home_venue_id) VALUES (?, ?, ?, 1)",
        ((1, "Harlequins Women", "Women"), (2, "Saracens Women", "Women"),
         (3, "England Women   ", "Women"), (4, "France Women", "Women"),
         (5, "Japan", "Men"), (6, "Fiji", "Men")),
    )
    connection.executemany(
        """
        INSERT INTO matches(
            competition_id, match_date, home_team_id, away_team_id
        ) VALUES (?, ?, ?, ?)
        """,
        ((1, "2026-01-01", 1, 2), (2, "2026-01-02", 3, 4),
         (3, "2026-01-03", 5, 6)),
    )
    connection.commit()
    connection.close()

    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))

    migrated = connect(database)
    countries = {
        row["name"].strip(): row["country"]
        for row in migrated.execute(
            """
            SELECT t.name, c.name AS country FROM teams t
            JOIN countries c ON c.id = t.country_id
            """
        )
    }
    assert countries["Harlequins Women"] == "England"
    assert countries["England Women"] == "England"
    assert countries["Japan"] == "Japan"
