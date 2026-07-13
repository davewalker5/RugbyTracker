"""Application configuration."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def project_root() -> Path:
    """Return the runtime root containing data and database migrations.

    :return: The configured runtime root, or the source project root by default.
    """
    configured = os.environ.get("RUGBY_TRACKER_ROOT")
    return Path(configured).expanduser() if configured else PROJECT_ROOT


def database_path() -> Path:
    """Return the configured SQLite database path.

    :return: The environment override, or the default project database path.
    """
    configured = os.environ.get("RUGBY_TRACKER_DB")
    return Path(configured).expanduser() if configured else project_root() / "data" / "rugbytracker.db"


def migrations_path() -> Path:
    """Return the directory containing the yoyo migrations.

    :return: The project's migrations directory.
    """
    return project_root() / "migrations"
