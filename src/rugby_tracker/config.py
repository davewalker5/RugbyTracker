"""Application configuration."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def database_path() -> Path:
    """Return the configured SQLite database path.

    :return: The environment override, or the default project database path.
    """
    configured = os.environ.get("RUGBY_TRACKER_DB")
    return Path(configured).expanduser() if configured else PROJECT_ROOT / "data" / "rugbytracker.db"


def migrations_path() -> Path:
    """Return the directory containing the yoyo migrations.

    :return: The project's migrations directory.
    """
    return PROJECT_ROOT / "migrations"
