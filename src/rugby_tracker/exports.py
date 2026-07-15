"""CSV export generation for Rugby Tracker."""

from __future__ import annotations

import csv
import io
import sqlite3
from typing import Any, Callable

from rugby_tracker.services import RugbyService


EXPORT_TYPES = ("Countries", "Venues", "Teams", "Competitions", "Referees", "Matches")

EXPORT_HEADERS = {
    "Countries": ("name",),
    "Venues": ("name", "town_city", "country"),
    "Teams": ("name", "country", "gender", "home_venue"),
    "Competitions": ("name", "season", "gender", "ruleset"),
    "Referees": ("name",),
    "Matches": (
        "competition", "season", "round", "venue", "referee", "date", "kickoff_time",
        "home_team", "home_country", "away_team", "away_country",
        "home_tries", "away_tries", "home_score", "away_score",
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

    def export_csv(self, entity_type: str, competition_id: int | None = None) -> str:
        """Serialise one supported record type as import-compatible CSV.

        :param entity_type: One of the values in :data:`EXPORT_TYPES`.
        :param competition_id: Optional competition limiting records and relations.
        :return: CSV text containing headers and all records of the selected type.
        :raises ValueError: If the entity type is unsupported.
        """
        # Select the dedicated row builder before writing a consistent header,
        # including when the database does not yet contain any matching records.
        builders: dict[str, Callable[[int | None], list[dict[str, Any]]]] = {
            "Countries": self._country_rows,
            "Venues": self._venue_rows,
            "Teams": self._team_rows,
            "Competitions": self._competition_rows,
            "Referees": self._referee_rows,
            "Matches": self._match_rows,
        }
        if entity_type not in builders:
            raise ValueError(f"Unsupported export type: {entity_type}")
        rows = builders[entity_type](competition_id)
        headers = EXPORT_HEADERS[entity_type]
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()

    def _country_rows(self, competition_id: int | None) -> list[dict[str, Any]]:
        """Build standalone country rows in import-column order.

        :param competition_id: Unused competition filter retained for builder consistency.
        :return: Country dictionaries ready for CSV writing.
        """
        # Countries are not referenced by existing entities yet, so all are exported.
        return self.rugby.list_countries()

    def _venue_rows(self, competition_id: int | None) -> list[dict[str, Any]]:
        """Build venue rows in import-column order.

        :param competition_id: Optional competition limiting related venues.
        :return: Venue dictionaries ready for CSV writing.
        """
        if competition_id is None:
            return self.rugby.list_venues()
        team_ids = self._team_ids(competition_id)
        # Include match grounds and the nominal home grounds needed by team imports.
        rows = self.connection.execute(
            "SELECT venue_id FROM matches WHERE competition_id = ? AND venue_id IS NOT NULL",
            (competition_id,),
        ).fetchall()
        venue_ids = {int(row["venue_id"]) for row in rows}
        venue_ids.update(
            int(row["home_venue_id"])
            for row in self.rugby.list_teams()
            if int(row["id"]) in team_ids
        )
        return [row for row in self.rugby.list_venues() if int(row["id"]) in venue_ids]

    def _team_rows(self, competition_id: int | None) -> list[dict[str, Any]]:
        """Build team rows with nominal venue names.

        :param competition_id: Optional competition limiting participating teams.
        :return: Team dictionaries ready for CSV writing.
        """
        # Resolve foreign keys to the names expected by the team importer.
        venue_names = {row["id"]: row["name"] for row in self.rugby.list_venues()}
        team_ids = self._team_ids(competition_id) if competition_id is not None else None
        return [
            {
                "name": row["name"],
                "country": row["country"],
                "gender": row["gender"],
                "home_venue": venue_names.get(row["home_venue_id"], ""),
            }
            for row in self.rugby.list_teams()
            if team_ids is None or int(row["id"]) in team_ids
        ]

    def _competition_rows(self, competition_id: int | None) -> list[dict[str, Any]]:
        """Build competition rows including their league-table rulesets.

        :param competition_id: Optional competition identifier to export alone.
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
            if competition_id is None or int(row["id"]) == competition_id
        ]

    def _referee_rows(self, competition_id: int | None) -> list[dict[str, Any]]:
        """Build referee rows in import-column order.

        :param competition_id: Optional competition limiting appointed referees.
        :return: Referee dictionaries ready for CSV writing.
        """
        if competition_id is None:
            return self.rugby.list_referees()
        rows = self.connection.execute(
            """
            SELECT DISTINCT referee_id FROM matches
            WHERE competition_id = ? AND referee_id IS NOT NULL
            """,
            (competition_id,),
        ).fetchall()
        referee_ids = {int(row["referee_id"]) for row in rows}
        return [
            row for row in self.rugby.list_referees()
            if int(row["id"]) in referee_ids
        ]

    def _match_rows(self, competition_id: int | None) -> list[dict[str, Any]]:
        """Build fixture and result rows using related entity names.

        :param competition_id: Optional competition limiting fixtures and results.
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
                "home_country": row["home_team_country"],
                "away_team": row["away_team_name"],
                "away_country": row["away_team_country"],
                "home_tries": "" if row["home_tries"] is None else row["home_tries"],
                "away_tries": "" if row["away_tries"] is None else row["away_tries"],
                "home_score": "" if row["home_score"] is None else row["home_score"],
                "away_score": "" if row["away_score"] is None else row["away_score"],
            }
            for row in self.rugby.list_matches(competition_id)
        ]

    def _team_ids(self, competition_id: int) -> set[int]:
        """Return identifiers of teams appearing in a competition's matches.

        :param competition_id: Competition whose home and away teams are required.
        :return: Set of participating team identifiers.
        """
        rows = self.connection.execute(
            """
            SELECT home_team_id, away_team_id
            FROM matches WHERE competition_id = ?
            """,
            (competition_id,),
        ).fetchall()
        return {
            int(team_id)
            for row in rows
            for team_id in (row["home_team_id"], row["away_team_id"])
        }
