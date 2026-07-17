"""Validation and business operations for the application."""

from __future__ import annotations

import sqlite3
import json
from datetime import date, time
from typing import Any

from rugby_tracker.repositories import Repository, RugbyRepository
from rugby_tracker.analysis import (
    CompetitionSummaryReport,
    HeadToHeadReport,
    TeamFormReport,
    TeamSummaryReport,
    build_competition_summary,
    build_head_to_head,
    build_team_form,
    build_team_summary,
)
from rugby_tracker.standings import (
    RULESETS,
    SUPPORTED_TIE_BREAKERS,
    calculate_competition,
    reload_rulesets,
    table_to_csv,
)


GENDERS = ("Men", "Women")


class ValidationError(ValueError):
    """An input error that is safe to display to a user."""


def required_text(value: Any, label: str) -> str:
    """Normalise a mandatory text value.

    :param value: Candidate value supplied by the user.
    :param label: User-facing field label used in validation messages.
    :return: The stripped, non-empty text.
    :raises ValidationError: If the value is empty.
    """
    cleaned = str(value).strip() if value is not None else ""
    if not cleaned:
        raise ValidationError(f"{label} is required.")
    return cleaned


def optional_text(value: Any) -> str | None:
    """Normalise an optional text value.

    :param value: Candidate value supplied by the user.
    :return: Stripped text, or ``None`` when the value is empty.
    """
    cleaned = str(value).strip() if value is not None else ""
    return cleaned or None


def valid_gender(value: Any) -> str:
    """Validate a competition or team category.

    :param value: Candidate category supplied by the user.
    :return: The validated category.
    :raises ValidationError: If the category is unsupported.
    """
    if value not in GENDERS:
        raise ValidationError("Category must be Men or Women.")
    return str(value)


def non_negative(value: Any, label: str) -> int:
    """Convert a value to a non-negative whole number.

    :param value: Candidate numeric value supplied by the user.
    :param label: User-facing field label used in validation messages.
    :return: The validated integer.
    :raises ValidationError: If the value is not a non-negative whole number.
    """
    if isinstance(value, bool):
        raise ValidationError(f"{label} must be a whole number of zero or more.")
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValidationError(f"{label} must be a whole number of zero or more.") from error
    if number < 0 or (isinstance(value, float) and not value.is_integer()):
        raise ValidationError(f"{label} must be a whole number of zero or more.")
    return number


def valid_ruleset(value: Any) -> str | None:
    """Validate an optional league-table ruleset identifier.

    :param value: Candidate identifier supplied by the user or an import.
    :return: Canonical identifier, or ``None`` when no ruleset is selected.
    :raises ValidationError: If the identifier is unsupported.
    """
    candidate = optional_text(value)
    if candidate is None:
        return None
    for identifier, ruleset in RULESETS.items():
        if candidate.casefold() in {identifier.casefold(), ruleset.label.casefold()}:
            return identifier
    raise ValidationError("Select a valid league-table ruleset.")


class RugbyService:
    """Validate inputs and coordinate Rugby Tracker data operations."""

    def __init__(self, connection: sqlite3.Connection):
        """Initialise the service over an open database connection.

        :param connection: Open SQLite connection for the current transaction.
        :return: None.
        """
        self.repo = RugbyRepository(connection)
        self.rulesets = reload_rulesets(connection)

    def list_rulesets(self) -> dict[str, Any]:
        """Return the current database-backed ruleset registry.

        :return: Rulesets keyed by their stable identifiers.
        """
        self.rulesets = reload_rulesets(self.repo.connection)
        return self.rulesets

    def list_ruleset_records(self) -> list[dict[str, Any]]:
        """Return editable ruleset database rows in display order.

        :return: Complete ruleset records with identifiers exposed as row IDs.
        """
        rows = self.repo.connection.execute(
            "SELECT * FROM competition_rulesets ORDER BY label COLLATE NOCASE, identifier"
        ).fetchall()
        return [{**dict(row), "id": row["identifier"]} for row in rows]

    def save_ruleset(self, entity_id: str | None = None, **values: Any) -> str:
        """Create or update a declarative competition ruleset.

        :param entity_id: Existing immutable identifier, or ``None`` to create one.
        :param values: All supported format, scoring, table, and award fields.
        :return: The saved stable ruleset identifier.
        :raises ValidationError: If configuration is invalid or unsupported.
        """
        requested_identifier = required_text(values.get("identifier"), "Ruleset identifier")
        identifier = entity_id or requested_identifier
        if entity_id and requested_identifier != entity_id:
            raise ValidationError("A ruleset identifier cannot be changed; create a new version.")
        duplicate = self.repo.connection.execute(
            "SELECT 1 FROM competition_rulesets WHERE identifier = ? COLLATE NOCASE "
            "AND identifier <> ?",
            (identifier, entity_id or ""),
        ).fetchone()
        if duplicate:
            raise ValidationError("A ruleset with this identifier already exists.")

        tie_breakers = self._ruleset_list(values.get("tie_breakers"), "Tie breakers", True)
        unsupported = set(tie_breakers) - SUPPORTED_TIE_BREAKERS
        if unsupported:
            raise ValidationError(
                "Unsupported tie breakers: " + ", ".join(sorted(unsupported)) + "."
            )
        special_handler = optional_text(values.get("special_handler"))
        if special_handler:
            raise ValidationError("Special handlers must be implemented in Python first.")
        data = {
            "identifier": identifier,
            "label": required_text(values.get("label"), "Ruleset label"),
            "team_count": self._optional_non_negative(values.get("team_count"), "Team count"),
            "matches_per_team": self._optional_non_negative(
                values.get("matches_per_team"), "Matches per team"
            ),
            "single_round_robin": int(bool(values.get("single_round_robin"))),
            "home_and_away": int(bool(values.get("home_and_away"))),
            "knockout_stage": int(bool(values.get("knockout_stage"))),
            "playoff_teams": non_negative(values.get("playoff_teams", 0), "Play-off teams"),
            "win_points": non_negative(values.get("win_points"), "Win points"),
            "draw_points": non_negative(values.get("draw_points"), "Draw points"),
            "loss_points": non_negative(values.get("loss_points"), "Loss points"),
            "try_bonus_threshold": non_negative(
                values.get("try_bonus_threshold"), "Try bonus threshold"
            ),
            "try_bonus_points": non_negative(values.get("try_bonus_points"), "Try bonus points"),
            "losing_bonus_margin": non_negative(
                values.get("losing_bonus_margin"), "Losing bonus margin"
            ),
            "losing_bonus_points": non_negative(
                values.get("losing_bonus_points"), "Losing bonus points"
            ),
            "grand_slam_bonus_points": non_negative(
                values.get("grand_slam_bonus_points", 0), "Grand Slam bonus points"
            ),
            "tie_breakers": json.dumps(tie_breakers, separators=(",", ":")),
            "excluded_rounds": json.dumps(
                self._ruleset_list(values.get("excluded_rounds"), "Excluded rounds"),
                separators=(",", ":"),
            ),
            "share_equal_positions": int(bool(values.get("share_equal_positions"))),
            "champion": int(bool(values.get("champion"))),
            "grand_slam": int(bool(values.get("grand_slam"))),
            "triple_crown": int(bool(values.get("triple_crown"))),
            "wooden_spoon": int(bool(values.get("wooden_spoon"))),
            "triple_crown_teams": json.dumps(
                self._ruleset_list(values.get("triple_crown_teams"), "Triple Crown teams"),
                separators=(",", ":"),
            ),
            "special_handler": None,
        }
        columns = tuple(data)
        if entity_id:
            assignments = ", ".join(f"{column} = ?" for column in columns if column != "identifier")
            parameters = [data[column] for column in columns if column != "identifier"]
            cursor = self.repo.connection.execute(
                f"UPDATE competition_rulesets SET {assignments} WHERE identifier = ?",
                (*parameters, entity_id),
            )
            if cursor.rowcount == 0:
                raise LookupError(f"No ruleset exists with identifier {entity_id}.")
        else:
            placeholders = ", ".join("?" for _ in columns)
            self.repo.connection.execute(
                f"INSERT INTO competition_rulesets ({', '.join(columns)}) VALUES ({placeholders})",
                tuple(data[column] for column in columns),
            )
        self.list_rulesets()
        return identifier

    def delete_ruleset(self, identifier: str) -> None:
        """Delete an unreferenced ruleset configuration.

        :param identifier: Stable ruleset identifier to remove.
        :return: None.
        :raises ValidationError: If a competition currently references the ruleset.
        """
        referenced = self.repo.connection.execute(
            "SELECT 1 FROM competitions WHERE ruleset = ? LIMIT 1", (identifier,)
        ).fetchone()
        if referenced:
            raise ValidationError(
                "This ruleset is in use and cannot be deleted. Update its competitions first."
            )
        cursor = self.repo.connection.execute(
            "DELETE FROM competition_rulesets WHERE identifier = ?", (identifier,)
        )
        if cursor.rowcount == 0:
            raise LookupError(f"No ruleset exists with identifier {identifier}.")
        self.list_rulesets()

    @staticmethod
    def _optional_non_negative(value: Any, label: str) -> int | None:
        """Validate an optional non-negative integer.

        :param value: Candidate numeric value.
        :param label: User-facing field label.
        :return: Validated integer or ``None`` when omitted.
        """
        return None if value in (None, "") else non_negative(value, label)

    @staticmethod
    def _ruleset_list(value: Any, label: str, required: bool = False) -> list[str]:
        """Validate a JSON string or sequence of non-empty ruleset values.

        :param value: JSON text or an existing sequence.
        :param label: User-facing field label.
        :param required: Whether at least one value is mandatory.
        :return: Normalised string list.
        :raises ValidationError: If the value is malformed.
        """
        try:
            parsed = json.loads(value or "[]") if isinstance(value, str) else list(value or [])
        except (json.JSONDecodeError, TypeError) as error:
            raise ValidationError(f"{label} must be a valid JSON array.") from error
        if not isinstance(parsed, list):
            raise ValidationError(f"{label} must be a valid JSON array.")
        if any(not isinstance(item, str) or not item.strip() for item in parsed):
            raise ValidationError(f"{label} must contain only non-empty text values.")
        result = [item.strip() for item in parsed]
        if required and not result:
            raise ValidationError(f"{label} must contain at least one value.")
        return result

    def list_countries(self) -> list[dict[str, Any]]:
        """List all standalone country records.

        :return: Country rows represented as dictionaries.
        """
        return self.repo.countries.list_all()

    def save_country(self, entity_id: int | None = None, **values: Any) -> int:
        """Create or update a standalone country record.

        :param entity_id: Existing country identifier, or ``None`` to create one.
        :param values: Country fields including the mandatory unique name.
        :return: The saved country's identifier.
        :raises ValidationError: If another country already uses the name.
        """
        name = required_text(values.get("name"), "Country name")
        duplicate = self.repo.connection.execute(
            """
            SELECT id FROM countries
            WHERE name = ? COLLATE NOCASE AND id <> COALESCE(?, -1)
            """,
            (name, entity_id),
        ).fetchone()
        if duplicate:
            raise ValidationError("A country with this name already exists.")
        return self._save(
            self.repo.countries,
            entity_id,
            {"name": name},
        )

    def list_venues(self) -> list[dict[str, Any]]:
        """List all venues.

        :return: Venue rows represented as dictionaries.
        """
        return self.repo.list_venues()

    def save_venue(self, entity_id: int | None = None, **values: Any) -> int:
        """Create or update a venue after validating its fields.

        :param entity_id: Existing venue identifier, or ``None`` to create one.
        :param values: Venue fields including name, town/city, and country identifier.
        :return: The saved venue's identifier.
        """
        data = {
            "name": required_text(values.get("name"), "Venue name"),
            "town_city": optional_text(values.get("town_city")),
            "country_id": (
                self._foreign_key(self.repo.countries, values.get("country_id"), "Country")
                if values.get("country_id") not in (None, "") else None
            ),
        }
        return self._save(self.repo.venues, entity_id, data)

    def list_teams(self) -> list[dict[str, Any]]:
        """List all teams.

        :return: Team rows represented as dictionaries.
        """
        return self.repo.list_teams()

    def save_team(self, entity_id: int | None = None, **values: Any) -> int:
        """Create or update a team after validating its fields.

        :param entity_id: Existing team identifier, or ``None`` to create one.
        :param values: Team fields including name, country identifier, category, and home venue.
        :return: The saved team's identifier.
        :raises ValidationError: If the name and country identify another team.
        """
        name = required_text(values.get("name"), "Team name")
        gender = valid_gender(values.get("gender"))
        country_id = self._foreign_key(
            self.repo.countries, values.get("country_id"), "Country"
        )
        venue_id = self._foreign_key(self.repo.venues, values.get("home_venue_id"), "Home venue")
        # Team identity is deliberately independent of gender and home venue.
        duplicate = self.repo.connection.execute(
            """
            SELECT id FROM teams
            WHERE name = ? COLLATE NOCASE AND country_id = ?
              AND id <> COALESCE(?, -1)
            """,
            (name, country_id, entity_id),
        ).fetchone()
        if duplicate:
            raise ValidationError("A team with this name and country already exists.")
        data = {
            "name": name,
            "country_id": country_id,
            "gender": gender,
            "home_venue_id": venue_id,
        }
        return self._save(self.repo.teams, entity_id, data)

    def list_competitions(self) -> list[dict[str, Any]]:
        """List all competitions.

        :return: Competition rows represented as dictionaries.
        """
        return self.repo.competitions.list_all()

    def save_competition(self, entity_id: int | None = None, **values: Any) -> int:
        """Create or update a competition after validating its fields.

        :param entity_id: Existing competition identifier, or ``None`` to create one.
        :param values: Competition fields including name, season, and category.
        :return: The saved competition's identifier.
        """
        data = {
            "name": required_text(values.get("name"), "Competition name"),
            "season": required_text(values.get("season"), "Season"),
            "gender": valid_gender(values.get("gender")),
            "ruleset": valid_ruleset(values.get("ruleset")),
        }
        return self._save(self.repo.competitions, entity_id, data)

    def list_referees(self) -> list[dict[str, Any]]:
        """List all referees.

        :return: Referee rows represented as dictionaries.
        """
        return self.repo.referees.list_all()

    def save_referee(self, entity_id: int | None = None, **values: Any) -> int:
        """Create or update a referee after validating the name.

        :param entity_id: Existing referee identifier, or ``None`` to create one.
        :param values: Referee fields, including the mandatory name.
        :return: The saved referee's identifier.
        """
        return self._save(
            self.repo.referees,
            entity_id,
            {"name": required_text(values.get("name"), "Referee name")},
        )

    def list_matches(self, competition_id: int | None = None) -> list[dict[str, Any]]:
        """List enriched match records in fixture order.

        :param competition_id: Optional competition identifier used to filter matches.
        :return: Match rows with related entity names.
        """
        return self.repo.list_matches(competition_id)

    def save_match(self, entity_id: int | None = None, **values: Any) -> int:
        """Create or update a fixture or result after full validation.

        :param entity_id: Existing match identifier, or ``None`` to create one.
        :param values: Match fields and referenced entity identifiers.
        :return: The saved match's identifier.
        :raises ValidationError: If required, reference, date, time, or score data is invalid.
        """
        # Resolve required references first, while allowing a future fixture to
        # remain venue-less until the host union confirms its ground.
        competition_id = self._foreign_key(
            self.repo.competitions, values.get("competition_id"), "Competition"
        )
        venue_value = values.get("venue_id")
        venue_id = (
            self._foreign_key(self.repo.venues, venue_value, "Venue")
            if venue_value not in (None, "") else None
        )
        home_team_id = self._foreign_key(self.repo.teams, values.get("home_team_id"), "Home team")
        away_team_id = self._foreign_key(self.repo.teams, values.get("away_team_id"), "Away team")
        if home_team_id == away_team_id:
            raise ValidationError("Home team and away team must be different.")

        referee_value = values.get("referee_id")
        referee_id = (
            self._foreign_key(self.repo.referees, referee_value, "Referee")
            if referee_value not in (None, "") else None
        )
        match_date = self._date_value(values.get("match_date"))
        kickoff_time = self._time_value(values.get("kickoff_time"))
        score_fields = ("home_tries", "away_tries", "home_score", "away_score")
        raw_scores = [values.get(field) for field in score_fields]
        has_value = [value not in (None, "") for value in raw_scores]
        if any(has_value) and not all(has_value):
            raise ValidationError("Enter all try and score values, or leave all four blank for a fixture.")
        scores = (
            [non_negative(value, label) for value, label in zip(raw_scores, ("Home tries", "Away tries", "Home score", "Away score"), strict=True)]
            if all(has_value) else [None, None, None, None]
        )
        data = {
            "competition_id": competition_id,
            "round": optional_text(values.get("round")),
            "venue_id": venue_id,
            "referee_id": referee_id,
            "match_date": match_date,
            "kickoff_time": kickoff_time,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
            **dict(zip(score_fields, scores, strict=True)),
        }
        return self._save(self.repo.matches, entity_id, data)

    def delete(self, entity: str, entity_id: int) -> None:
        """Delete an entity while protecting referenced records.

        :param entity: Singular entity type handled by the service.
        :param entity_id: Primary-key identifier to delete.
        :return: None.
        :raises ValidationError: If another record references the entity.
        """
        repositories = {
            "country": self.repo.countries,
            "venue": self.repo.venues,
            "team": self.repo.teams,
            "competition": self.repo.competitions,
            "referee": self.repo.referees,
            "match": self.repo.matches,
        }
        try:
            repository = repositories[entity]
        except KeyError as error:
            raise ValueError(f"Unknown entity: {entity}") from error
        try:
            repository.delete(entity_id)
        except sqlite3.IntegrityError as error:
            raise ValidationError(
                f"This {entity} is in use and cannot be deleted. Update or delete its related records first."
            ) from error

    def league_table(self, competition_id: int) -> dict[str, Any]:
        """Calculate the current table for a competition.

        :param competition_id: Competition identifier to calculate.
        :return: Competition details and calculated, ordered table rows.
        :raises ValidationError: If the competition is missing or has no ruleset.
        """
        rulesets = self.list_rulesets()
        competition = self.repo.competitions.get(competition_id)
        if competition is None:
            raise ValidationError("Select a valid competition.")
        ruleset = competition.get("ruleset")
        if not ruleset:
            raise ValidationError("Select a league-table ruleset for this competition first.")
        try:
            calculation = calculate_competition(
                self.repo.list_matches(competition_id), str(ruleset)
            )
        except ValueError as error:
            raise ValidationError(str(error)) from error
        return {
            "competition": competition,
            "ruleset": rulesets[str(ruleset)],
            **calculation,
        }

    def league_table_csv(self, competition_id: int) -> str:
        """Export a freshly calculated competition table as CSV text.

        :param competition_id: Competition identifier to calculate and export.
        :return: CSV text containing the current league table.
        """
        return table_to_csv(self.league_table(competition_id)["table"])

    def team_summary(self, competition_id: int, team_id: int) -> TeamSummaryReport:
        """Calculate a team summary for one competition record.

        :param competition_id: Selected competition-season identifier.
        :param team_id: Participating team identifier.
        :return: Structured team summary for UI and PDF rendering.
        :raises ValidationError: If either selection is invalid or unrelated.
        """
        # Resolve selections through existing repositories before calculating.
        competition = self.repo.competitions.get(competition_id)
        team = next((row for row in self.repo.list_teams() if int(row["id"]) == team_id), None)
        if competition is None or team is None:
            raise ValidationError("Select a valid competition and team.")
        matches = self.repo.list_matches(competition_id)
        if not any(team_id in (int(row["home_team_id"]), int(row["away_team_id"])) for row in matches):
            raise ValidationError("Select a team participating in this competition and season.")
        return build_team_summary(competition, team, matches)

    def team_form(
        self, competition_id: int, team_id: int, window: int = 5
    ) -> TeamFormReport:
        """Calculate recent completed form for one competition team.

        :param competition_id: Selected competition-season identifier.
        :param team_id: Participating team identifier.
        :param window: Maximum number of recent completed matches to include.
        :return: Structured Team Form report.
        """
        competition = self.repo.competitions.get(competition_id)
        team = next((row for row in self.repo.list_teams() if int(row["id"]) == team_id), None)
        if competition is None or team is None:
            raise ValidationError("Select a valid competition and team.")
        matches = self.repo.list_matches(competition_id)
        if not any(team_id in (int(row["home_team_id"]), int(row["away_team_id"])) for row in matches):
            raise ValidationError("Select a team participating in this competition and season.")
        try:
            return build_team_form(competition, team, matches, window)
        except ValueError as error:
            raise ValidationError(str(error)) from error

    def competition_summary(self, competition_id: int) -> CompetitionSummaryReport:
        """Calculate a competition-wide summary for one season record.

        :param competition_id: Selected competition-season identifier.
        :return: Structured competition summary for UI and PDF rendering.
        :raises ValidationError: If the selection is invalid or cannot be calculated.
        """
        competition = self.repo.competitions.get(competition_id)
        if competition is None:
            raise ValidationError("Select a valid competition.")
        matches = self.repo.list_matches(competition_id)
        if not matches:
            raise ValidationError("Add matches for this competition before generating a summary.")
        try:
            return build_competition_summary(competition, matches)
        except ValueError as error:
            raise ValidationError(str(error)) from error

    def head_to_head(
        self, competition_ids: list[int], team_a_id: int, team_b_id: int
    ) -> HeadToHeadReport:
        """Calculate a historical comparison for two participating teams.

        :param competition_ids: One or more seasons of the same competition.
        :param team_a_id: First participating team identifier.
        :param team_b_id: Second participating team identifier.
        :return: Structured Head-to-Head report.
        :raises ValidationError: If selections are invalid or have no completed meetings.
        """
        competitions = [
            competition for competition_id in competition_ids
            if (competition := self.repo.competitions.get(int(competition_id))) is not None
        ]
        if not competitions or len(competitions) != len(set(competition_ids)):
            raise ValidationError("Select a valid competition and season.")
        if len({str(row["name"]).casefold() for row in competitions}) != 1:
            raise ValidationError("Selected seasons must belong to the same competition.")
        teams = {int(row["id"]): row for row in self.repo.list_teams()}
        if team_a_id not in teams or team_b_id not in teams:
            raise ValidationError("Select two valid teams.")
        matches = [
            match for competition_id in competition_ids
            for match in self.repo.list_matches(int(competition_id))
        ]
        participating = {
            int(team_id) for match in matches
            for team_id in (match["home_team_id"], match["away_team_id"])
        }
        if team_a_id not in participating or team_b_id not in participating:
            raise ValidationError("Select teams participating in this competition and season.")
        try:
            return build_head_to_head(
                competitions, teams[team_a_id], teams[team_b_id], matches
            )
        except ValueError as error:
            raise ValidationError(str(error)) from error

    @staticmethod
    def _save(repository: Repository, entity_id: int | None, data: dict[str, Any]) -> int:
        """Persist validated entity data through a repository.

        :param repository: Entity repository used for persistence.
        :param entity_id: Existing identifier, or ``None`` for an insert.
        :param data: Validated column values to persist.
        :return: The inserted or updated entity identifier.
        :raises ValidationError: If database integrity validation fails.
        """
        try:
            if entity_id is None:
                return repository.insert(data)
            repository.update(entity_id, data)
            return entity_id
        except sqlite3.IntegrityError as error:
            raise ValidationError("The record could not be saved because it contains invalid or referenced data.") from error

    @staticmethod
    def _foreign_key(repository: Repository, value: Any, label: str) -> int:
        """Validate and return a referenced entity identifier.

        :param repository: Repository containing the referenced entity.
        :param value: Candidate identifier supplied by the user.
        :param label: User-facing field label used in validation messages.
        :return: The validated identifier.
        :raises ValidationError: If the identifier is absent or unknown.
        """
        try:
            entity_id = int(value)
        except (TypeError, ValueError) as error:
            raise ValidationError(f"{label} is required.") from error
        if repository.get(entity_id) is None:
            raise ValidationError(f"Select a valid {label.lower()}.")
        return entity_id

    @staticmethod
    def _date_value(value: Any) -> str:
        """Normalise a date value to ISO format.

        :param value: A date object or ISO-formatted date string.
        :return: The date in ``YYYY-MM-DD`` format.
        :raises ValidationError: If the value is missing or invalid.
        """
        if isinstance(value, date):
            return value.isoformat()
        try:
            return date.fromisoformat(required_text(value, "Match date")).isoformat()
        except ValueError as error:
            raise ValidationError("Match date must be a valid date.") from error

    @staticmethod
    def _time_value(value: Any) -> str | None:
        """Normalise an optional kick-off time.

        :param value: A time object, time string, or empty value.
        :return: Time in ``HH:MM`` format, or ``None`` when omitted.
        :raises ValidationError: If a supplied time is invalid.
        """
        if value in (None, ""):
            return None
        if isinstance(value, time):
            return value.strftime("%H:%M")
        try:
            return time.fromisoformat(str(value)).strftime("%H:%M")
        except ValueError as error:
            raise ValidationError("Kick-off time must be a valid time.") from error
