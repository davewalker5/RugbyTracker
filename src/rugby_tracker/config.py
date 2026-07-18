"""Application configuration."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_READ_ONLY_DOMAINS = ("streamlit.io",)


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


def read_only_domains() -> tuple[str, ...]:
    """Return domains whose web deployments must not modify stored data.

    ``RUGBY_TRACKER_READ_ONLY_DOMAINS`` accepts a comma-separated list. Setting
    it replaces the defaults, making deployment-specific configuration simple.

    :return: Normalised domain names, without ports or leading dots.
    """
    configured = os.environ.get("RUGBY_TRACKER_READ_ONLY_DOMAINS")
    values = configured.split(",") if configured is not None else DEFAULT_READ_ONLY_DOMAINS
    return tuple(
        value.strip().lower().strip(".")
        for value in values
        if value.strip().strip(".")
    )


def is_read_only_domain(hostname: str | None) -> bool:
    """Return whether a hostname is a configured read-only domain or subdomain.

    :param hostname: Request hostname, optionally including a port.
    :return: ``True`` when the hostname matches a configured domain.
    """
    host = (hostname or "").split(":", 1)[0].strip().lower().rstrip(".")
    return any(host == domain or host.endswith(f".{domain}") for domain in read_only_domains())
