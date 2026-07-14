"""Data access layer for Rugby Tracker entities."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from typing import Any


class Repository:
    """Small repository around a single, known table."""

    def __init__(self, connection: sqlite3.Connection, table: str, columns: Iterable[str]):
        """Initialise a repository for a known table and set of writable columns.

        :param connection: Open SQLite connection used for all operations.
        :param table: Trusted database table name.
        :param columns: Trusted column names that may be written.
        :return: None.
        """
        self.connection = connection
        self.table = table
        self.columns = tuple(columns)

    def list_all(self) -> list[dict[str, Any]]:
        """List every entity ordered by name and identifier.

        :return: Entity rows represented as dictionaries.
        """
        rows = self.connection.execute(
            f"SELECT * FROM {self.table} ORDER BY name COLLATE NOCASE, id"
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, entity_id: int) -> dict[str, Any] | None:
        """Retrieve an entity by identifier.

        :param entity_id: Primary-key identifier to find.
        :return: The entity dictionary, or ``None`` when it does not exist.
        """
        row = self.connection.execute(
            f"SELECT * FROM {self.table} WHERE id = ?", (entity_id,)
        ).fetchone()
        return dict(row) if row else None

    def insert(self, values: Mapping[str, Any]) -> int:
        """Insert an entity using the repository's writable columns.

        :param values: Mapping of column names to values.
        :return: The new entity's primary-key identifier.
        """
        columns = [column for column in self.columns if column in values]
        placeholders = ", ".join("?" for _ in columns)
        cursor = self.connection.execute(
            f"INSERT INTO {self.table} ({', '.join(columns)}) VALUES ({placeholders})",
            [values[column] for column in columns],
        )
        return int(cursor.lastrowid)

    def update(self, entity_id: int, values: Mapping[str, Any]) -> None:
        """Update an existing entity.

        :param entity_id: Primary-key identifier of the entity to update.
        :param values: Mapping of column names to replacement values.
        :return: None.
        :raises LookupError: If the entity does not exist.
        """
        columns = [column for column in self.columns if column in values]
        assignments = ", ".join(f"{column} = ?" for column in columns)
        cursor = self.connection.execute(
            f"UPDATE {self.table} SET {assignments} WHERE id = ?",
            [values[column] for column in columns] + [entity_id],
        )
        if cursor.rowcount == 0:
            raise LookupError(f"No {self.table.rstrip('s')} exists with ID {entity_id}.")

    def delete(self, entity_id: int) -> None:
        """Delete an existing entity.

        :param entity_id: Primary-key identifier of the entity to delete.
        :return: None.
        :raises LookupError: If the entity does not exist.
        """
        cursor = self.connection.execute(
            f"DELETE FROM {self.table} WHERE id = ?", (entity_id,)
        )
        if cursor.rowcount == 0:
            raise LookupError(f"No {self.table.rstrip('s')} exists with ID {entity_id}.")


class RugbyRepository:
    """Repositories and read models sharing one transaction."""

    def __init__(self, connection: sqlite3.Connection):
        """Initialise entity repositories over a shared transaction.

        :param connection: Open SQLite connection used for all operations.
        :return: None.
        """
        self.connection = connection
        self.venues = Repository(connection, "venues", ("name", "town_city", "country"))
        self.teams = Repository(connection, "teams", ("name", "gender", "home_venue_id"))
        self.competitions = Repository(
            connection, "competitions", ("name", "season", "gender", "ruleset")
        )
        self.referees = Repository(connection, "referees", ("name",))
        self.matches = Repository(
            connection,
            "matches",
            (
                "competition_id", "round", "venue_id", "referee_id", "match_date",
                "kickoff_time", "home_team_id", "away_team_id", "home_tries",
                "away_tries", "home_score", "away_score",
            ),
        )

    def list_matches(self, competition_id: int | None = None) -> list[dict[str, Any]]:
        """List matches with their related entity names in fixture order.

        :param competition_id: Optional competition identifier used to filter matches.
        :return: Enriched match rows represented as dictionaries.
        """
        where = "WHERE m.competition_id = ?" if competition_id is not None else ""
        parameters = (competition_id,) if competition_id is not None else ()
        rows = self.connection.execute(
            f"""
            SELECT m.*, c.name AS competition_name, c.season AS competition_season,
                   v.name AS venue_name, r.name AS referee_name,
                   h.name AS home_team_name, a.name AS away_team_name
            FROM matches m
            JOIN competitions c ON c.id = m.competition_id
            LEFT JOIN venues v ON v.id = m.venue_id
            LEFT JOIN referees r ON r.id = m.referee_id
            JOIN teams h ON h.id = m.home_team_id
            JOIN teams a ON a.id = m.away_team_id
            {where}
            ORDER BY m.match_date, COALESCE(m.kickoff_time, ''), m.id
            """,
            parameters,
        ).fetchall()
        return [dict(row) for row in rows]

    def get_match(self, match_id: int) -> dict[str, Any] | None:
        """Retrieve a raw match row by identifier.

        :param match_id: Primary-key identifier to find.
        :return: The match dictionary, or ``None`` when it does not exist.
        """
        row = self.connection.execute(
            "SELECT * FROM matches WHERE id = ?", (match_id,)
        ).fetchone()
        return dict(row) if row else None
