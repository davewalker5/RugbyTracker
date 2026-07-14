"""CSV export generation for Rugby Tracker."""

from __future__ import annotations

import csv
import io
import sqlite3
from typing import Any, Callable

from rugby_tracker.services import RugbyService


EXPORT_TYPES = ("Venues", "Teams", "Competitions", "Referees", "Matches")

EXPORT_HEADERS = {
    "Venues": ("name", "town_city", "country"),
    "Teams": ("name", "gender", "home_venue"),
    "Competitions": ("name", "season", "gender", "ruleset"),
    "Referees": ("name",),
    "Matches": (
        "competition", "season", "round", "venue", "referee", "date", "kickoff_time",
        "home_team", "away_team", "home_tries", "away_tries", "home_score", "away_score",
    ),
}


class CsvExportService:
    """Export Rugby Tracker entities using the corresponding import schemas."""

    def __init__(self, connection: sqlite3.Connection):
        """Initialise the exporter over an open database connection.

        :param connection: Open SQLite connection used to read export records.
        :return: None.
        """
        # Reuse the application's read model so exported matches contain names
        # rather than database identifiers.
        self.connection = connection
        self.rugby = RugbyService(connection)

    def export_csv(self, entity_type: str) -> str:
        """Serialise one supported record type as import-compatible CSV.

        :param entity_type: One of the values in :data:`EXPORT_TYPES`.
        :return: CSV text containing headers and all records of the selected type.
        :raises ValueError: If the entity type is unsupported.
        """
        # Select the dedicated row builder before writing a consistent header,
        # including when the database does not yet contain any matching records.
        builders: dict[str, Callable[[], list[dict[str, Any]]]] = {
            "Venues": self._venue_rows,
            "Teams": self._team_rows,
            "Competitions": self._competition_rows,
            "Referees": self._referee_rows,
            "Matches": self._match_rows,
        }
        if entity_type not in builders:
            raise ValueError(f"Unsupported export type: {entity_type}")
        rows = builders[entity_type]()
        headers = EXPORT_HEADERS[entity_type]
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()

    def _venue_rows(self) -> list[dict[str, Any]]:
        """Build venue rows in import-column order.

        :return: Venue dictionaries ready for CSV writing.
        """
        # Repository ordering makes repeated exports deterministic.
        return self.rugby.list_venues()

    def _team_rows(self) -> list[dict[str, Any]]:
        """Build team rows with nominal venue names.

        :return: Team dictionaries ready for CSV writing.
        """
        # Resolve foreign keys to the names expected by the team importer.
        venue_names = {row["id"]: row["name"] for row in self.rugby.list_venues()}
        return [
            {
                "name": row["name"],
                "gender": row["gender"],
                "home_venue": venue_names.get(row["home_venue_id"], ""),
            }
            for row in self.rugby.list_teams()
        ]

    def _competition_rows(self) -> list[dict[str, Any]]:
        """Build competition rows including their league-table rulesets.

        :return: Competition dictionaries ready for CSV writing.
        """
        # Convert nullable rulesets to blank CSV cells for clean round trips.
        return [
            {
                "name": row["name"],
                "season": row["season"],
                "gender": row["gender"],
                "ruleset": row["ruleset"] or "",
            }
            for row in self.rugby.list_competitions()
        ]

    def _referee_rows(self) -> list[dict[str, Any]]:
        """Build referee rows in import-column order.

        :return: Referee dictionaries ready for CSV writing.
        """
        # Referees already share the export schema, so no transformation is needed.
        return self.rugby.list_referees()

    def _match_rows(self) -> list[dict[str, Any]]:
        """Build fixture and result rows using related entity names.

        :return: Match dictionaries ready for CSV writing.
        """
        # Preserve blank optional values so future fixtures can be re-imported.
        return [
            {
                "competition": row["competition_name"],
                "season": row["competition_season"],
                "round": row["round"] or "",
                "venue": row["venue_name"] or "",
                "referee": row["referee_name"] or "",
                "date": row["match_date"],
                "kickoff_time": row["kickoff_time"] or "",
                "home_team": row["home_team_name"],
                "away_team": row["away_team_name"],
                "home_tries": "" if row["home_tries"] is None else row["home_tries"],
                "away_tries": "" if row["away_tries"] is None else row["away_tries"],
                "home_score": "" if row["home_score"] is None else row["home_score"],
                "away_score": "" if row["away_score"] is None else row["away_score"],
            }
            for row in self.rugby.list_matches()
        ]
