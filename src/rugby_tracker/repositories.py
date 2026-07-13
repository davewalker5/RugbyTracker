"""Data access layer for Rugby Tracker entities."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from typing import Any


class Repository:
    """Small repository around a single, known table."""

    def __init__(self, connection: sqlite3.Connection, table: str, columns: Iterable[str]):
        self.connection = connection
        self.table = table
        self.columns = tuple(columns)

    def list_all(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            f"SELECT * FROM {self.table} ORDER BY name COLLATE NOCASE, id"
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, entity_id: int) -> dict[str, Any] | None:
        row = self.connection.execute(
            f"SELECT * FROM {self.table} WHERE id = ?", (entity_id,)
        ).fetchone()
        return dict(row) if row else None

    def insert(self, values: Mapping[str, Any]) -> int:
        columns = [column for column in self.columns if column in values]
        placeholders = ", ".join("?" for _ in columns)
        cursor = self.connection.execute(
            f"INSERT INTO {self.table} ({', '.join(columns)}) VALUES ({placeholders})",
            [values[column] for column in columns],
        )
        return int(cursor.lastrowid)

    def update(self, entity_id: int, values: Mapping[str, Any]) -> None:
        columns = [column for column in self.columns if column in values]
        assignments = ", ".join(f"{column} = ?" for column in columns)
        cursor = self.connection.execute(
            f"UPDATE {self.table} SET {assignments} WHERE id = ?",
            [values[column] for column in columns] + [entity_id],
        )
        if cursor.rowcount == 0:
            raise LookupError(f"No {self.table.rstrip('s')} exists with ID {entity_id}.")

    def delete(self, entity_id: int) -> None:
        cursor = self.connection.execute(
            f"DELETE FROM {self.table} WHERE id = ?", (entity_id,)
        )
        if cursor.rowcount == 0:
            raise LookupError(f"No {self.table.rstrip('s')} exists with ID {entity_id}.")


class RugbyRepository:
    """Repositories and read models sharing one transaction."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.venues = Repository(connection, "venues", ("name", "town_city", "country"))
        self.teams = Repository(connection, "teams", ("name", "gender", "home_venue_id"))
        self.competitions = Repository(connection, "competitions", ("name", "season", "gender"))
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
        where = "WHERE m.competition_id = ?" if competition_id is not None else ""
        parameters = (competition_id,) if competition_id is not None else ()
        rows = self.connection.execute(
            f"""
            SELECT m.*, c.name AS competition_name, c.season AS competition_season,
                   v.name AS venue_name, r.name AS referee_name,
                   h.name AS home_team_name, a.name AS away_team_name
            FROM matches m
            JOIN competitions c ON c.id = m.competition_id
            JOIN venues v ON v.id = m.venue_id
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
        row = self.connection.execute(
            "SELECT * FROM matches WHERE id = ?", (match_id,)
        ).fetchone()
        return dict(row) if row else None
