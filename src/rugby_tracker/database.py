"""SQLite connection and migration management."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from rugby_tracker.config import database_path, migrations_path


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open a configured connection with integrity checks enabled.

    :param path: Optional database path; the configured path is used when omitted.
    :return: An open SQLite connection whose rows support name-based access.
    """
    target = Path(path) if path is not None else database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def session(path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    """Provide a transaction that commits or rolls back automatically.

    :param path: Optional database path; the configured path is used when omitted.
    :return: An iterator yielding one open SQLite connection.
    """
    connection = connect(path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def apply_migrations(path: Path | str | None = None) -> None:
    """Apply all pending yoyo migrations to the selected database.

    :param path: Optional database path; the configured path is used when omitted.
    :return: None.
    """
    from yoyo import get_backend, read_migrations

    target = Path(path) if path is not None else database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    backend = get_backend(f"sqlite:///{target.resolve()}")
    migrations = read_migrations(str(migrations_path()))
    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))
