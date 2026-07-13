"""CSV import validation and persistence for Rugby Tracker."""

from __future__ import annotations

import csv
import io
import sqlite3
from dataclasses import dataclass, field
from datetime import date, time
from typing import Any, Callable

from rugby_tracker.services import (
    GENDERS,
    RugbyService,
    ValidationError,
    non_negative,
    optional_text,
    required_text,
    valid_ruleset,
)


IMPORT_TYPES = ("Venues", "Teams", "Competitions", "Referees", "Matches")

TEMPLATE_HEADERS = {
    "Venues": ("name", "town_city", "country"),
    "Teams": ("name", "gender", "home_venue"),
    "Competitions": ("name", "season", "gender", "ruleset"),
    "Referees": ("name",),
    "Matches": (
        "competition", "season", "round", "venue", "referee", "date", "kickoff_time",
        "home_team", "away_team", "home_tries", "away_tries", "home_score", "away_score",
    ),
}

REQUIRED_HEADERS = {
    "Venues": {"name"},
    "Teams": {"name", "gender", "home_venue"},
    "Competitions": {"name", "season", "gender"},
    "Referees": {"name"},
    "Matches": {"competition", "season", "venue", "date", "home_team", "away_team"},
}

HEADER_ALIASES = {
    "category": "gender",
    "mens_womens": "gender",
    "home_ground": "home_venue",
    "match_date": "date",
    "kick_off": "kickoff_time",
    "kick_off_time": "kickoff_time",
}


@dataclass(frozen=True)
class ImportIssue:
    """A validation failure associated with a CSV row."""

    row: int
    messages: tuple[str, ...]


@dataclass
class ImportReport:
    """Counts and validation details produced by one CSV import."""

    entity_type: str
    total_rows: int = 0
    imported: int = 0
    skipped: int = 0
    issues: list[ImportIssue] = field(default_factory=list)

    @property
    def invalid(self) -> int:
        """Return the number of distinct invalid CSV rows.

        :return: Count of rows that contain one or more validation failures.
        """
        return len({issue.row for issue in self.issues})

    @property
    def successful(self) -> bool:
        """Return whether the import contains no validation failures.

        :return: ``True`` when every parsed row was valid or a duplicate.
        """
        return not self.issues

    def error_rows(self) -> list[dict[str, Any]]:
        """Convert validation issues into rows suitable for UI display.

        :return: Dictionaries containing CSV row numbers and error messages.
        """
        return [
            {"CSV row": issue.row, "Validation errors": "; ".join(issue.messages)}
            for issue in self.issues
        ]


class CsvImportService:
    """Validate CSV rows and import supported Rugby Tracker entities."""

    def __init__(self, connection: sqlite3.Connection):
        """Initialise the importer over an open database connection.

        :param connection: Open SQLite connection used for lookups and inserts.
        :return: None.
        """
        self.connection = connection
        self.rugby = RugbyService(connection)

    @staticmethod
    def template(entity_type: str) -> str:
        """Build an empty CSV template for a supported entity type.

        :param entity_type: One of the values in :data:`IMPORT_TYPES`.
        :return: CSV text containing the supported column headings.
        :raises ValueError: If the entity type is unsupported.
        """
        try:
            headers = TEMPLATE_HEADERS[entity_type]
        except KeyError as error:
            raise ValueError(f"Unsupported import type: {entity_type}") from error
        output = io.StringIO(newline="")
        csv.writer(output).writerow(headers)
        return output.getvalue()

    def import_csv(self, entity_type: str, content: bytes | str) -> ImportReport:
        """Validate and import a CSV document.

        Valid rows are imported, duplicate rows are skipped, and invalid rows are
        refused without preventing other valid rows from being processed.

        :param entity_type: Supported entity type selected by the user.
        :param content: UTF-8 CSV content as bytes or text.
        :return: Import counts and all discovered validation issues.
        :raises ValueError: If the entity type is unsupported.
        """
        if entity_type not in IMPORT_TYPES:
            raise ValueError(f"Unsupported import type: {entity_type}")
        report = ImportReport(entity_type)
        rows = self._read_rows(content, report)
        if rows is None:
            return report
        validator = {
            "Venues": self._validate_venue,
            "Teams": self._validate_team,
            "Competitions": self._validate_competition,
            "Referees": self._validate_referee,
            "Matches": self._validate_match,
        }[entity_type]
        seen = self._existing_keys(entity_type)
        for row_number, row in rows:
            report.total_rows += 1
            values, messages = validator(row)
            if messages:
                report.issues.append(ImportIssue(row_number, tuple(messages)))
                continue
            assert values is not None
            key = self._duplicate_key(entity_type, values)
            if key in seen:
                report.skipped += 1
                continue
            try:
                self._persist(entity_type, values)
            except ValidationError as error:
                report.issues.append(ImportIssue(row_number, (str(error),)))
                continue
            seen.add(key)
            report.imported += 1
        return report

    def _read_rows(
        self, content: bytes | str, report: ImportReport
    ) -> list[tuple[int, dict[str, str]]] | None:
        """Decode CSV content and normalise its headers and rows.

        :param content: UTF-8 CSV content as bytes or text.
        :param report: Report that receives document-level validation issues.
        :return: Numbered, normalised rows, or ``None`` for an invalid document.
        """
        try:
            text = content.decode("utf-8-sig") if isinstance(content, bytes) else content.lstrip("\ufeff")
        except UnicodeDecodeError:
            report.issues.append(ImportIssue(1, ("The file must use UTF-8 encoding.",)))
            return None
        try:
            reader = csv.DictReader(io.StringIO(text, newline=""))
            if not reader.fieldnames:
                report.issues.append(ImportIssue(1, ("The CSV file must contain a header row.",)))
                return None
            headers = [self._header(name) for name in reader.fieldnames]
            if len(headers) != len(set(headers)):
                report.issues.append(ImportIssue(1, ("The CSV contains duplicate column headings.",)))
                return None
            missing = sorted(REQUIRED_HEADERS[report.entity_type] - set(headers))
            if missing:
                report.issues.append(
                    ImportIssue(1, ("Missing required columns: " + ", ".join(missing) + ".",))
                )
                return None
            numbered_rows: list[tuple[int, dict[str, str]]] = []
            for row_number, raw in enumerate(reader, start=2):
                row = {
                    self._header(key): (value.strip() if value is not None else "")
                    for key, value in raw.items() if key is not None
                }
                if any(row.values()):
                    numbered_rows.append((row_number, row))
            return numbered_rows
        except csv.Error as error:
            report.issues.append(ImportIssue(1, (f"The CSV could not be read: {error}.",)))
            return None

    @staticmethod
    def _header(value: str) -> str:
        """Normalise a CSV heading and apply supported aliases.

        :param value: Raw CSV heading.
        :return: Lowercase underscore-separated canonical heading.
        """
        normalised = "_".join(value.strip().lower().replace("-", " ").replace("/", " ").split())
        return HEADER_ALIASES.get(normalised, normalised)

    def _validate_team(self, row: dict[str, str]) -> tuple[dict[str, Any] | None, list[str]]:
        """Validate and resolve one team import row.

        :param row: Normalised CSV row.
        :return: Prepared service values and validation messages.
        """
        messages: list[str] = []
        name = self._value(lambda: required_text(row.get("name"), "Team name"), messages)
        gender = self._value(lambda: self._gender(row.get("gender")), messages)
        venue_id = self._resolve("venues", row.get("home_venue"), "Home venue", messages)
        if messages:
            return None, messages
        return {"name": name, "gender": gender, "home_venue_id": venue_id}, messages

    def _validate_venue(self, row: dict[str, str]) -> tuple[dict[str, Any] | None, list[str]]:
        """Validate one venue import row.

        :param row: Normalised CSV row.
        :return: Prepared service values and validation messages.
        """
        messages: list[str] = []
        name = self._value(lambda: required_text(row.get("name"), "Venue name"), messages)
        if messages:
            return None, messages
        return {
            "name": name,
            "town_city": optional_text(row.get("town_city")),
            "country": optional_text(row.get("country")),
        }, messages

    def _validate_competition(self, row: dict[str, str]) -> tuple[dict[str, Any] | None, list[str]]:
        """Validate one competition import row.

        :param row: Normalised CSV row.
        :return: Prepared service values and validation messages.
        """
        messages: list[str] = []
        name = self._value(lambda: required_text(row.get("name"), "Competition name"), messages)
        season = self._value(lambda: required_text(row.get("season"), "Season"), messages)
        gender = self._value(lambda: self._gender(row.get("gender")), messages)
        ruleset = self._value(lambda: valid_ruleset(row.get("ruleset")), messages)
        if messages:
            return None, messages
        return {
            "name": name,
            "season": season,
            "gender": gender,
            "ruleset": ruleset,
        }, messages

    def _validate_referee(self, row: dict[str, str]) -> tuple[dict[str, Any] | None, list[str]]:
        """Validate one referee import row.

        :param row: Normalised CSV row.
        :return: Prepared service values and validation messages.
        """
        messages: list[str] = []
        name = self._value(lambda: required_text(row.get("name"), "Referee name"), messages)
        return (None, messages) if messages else ({"name": name}, messages)

    def _validate_match(self, row: dict[str, str]) -> tuple[dict[str, Any] | None, list[str]]:
        """Validate and resolve one match import row.

        :param row: Normalised CSV row using entity names instead of identifiers.
        :return: Prepared service values and all validation messages.
        """
        messages: list[str] = []
        values: dict[str, Any] = {
            "competition_id": self._resolve_competition(
                row.get("competition"), row.get("season"), messages
            ),
            "venue_id": self._resolve("venues", row.get("venue"), "Venue", messages),
            "home_team_id": self._resolve("teams", row.get("home_team"), "Home team", messages),
            "away_team_id": self._resolve("teams", row.get("away_team"), "Away team", messages),
            "referee_id": self._resolve("referees", row.get("referee"), "Referee", messages, optional=True),
            "round": optional_text(row.get("round")),
            "match_date": self._value(lambda: self._date(row.get("date")), messages),
            "kickoff_time": self._value(lambda: self._time(row.get("kickoff_time")), messages),
        }
        if values["home_team_id"] is not None and values["home_team_id"] == values["away_team_id"]:
            messages.append("Home team and away team must be different.")
        scores = self._scores(row, messages)
        values.update(scores)
        return (None, messages) if messages else (values, messages)

    def _resolve_competition(
        self,
        name_value: str | None,
        season_value: str | None,
        messages: list[str],
    ) -> int | None:
        """Resolve a competition by case-insensitive name and season.

        :param name_value: Competition name supplied by the CSV row.
        :param season_value: Competition season supplied by the CSV row.
        :param messages: Collection that receives validation failures.
        :return: The unique matching identifier, or ``None`` on failure.
        """
        name = optional_text(name_value)
        season = optional_text(season_value)
        if name is None:
            messages.append("Competition is required.")
        if season is None:
            messages.append("Season is required.")
        if name is None or season is None:
            return None
        rows = self.connection.execute(
            """
            SELECT id
            FROM competitions
            WHERE name = ? COLLATE NOCASE
              AND season = ? COLLATE NOCASE
            ORDER BY id
            """,
            (name, season),
        ).fetchall()
        if not rows:
            messages.append(f'Competition "{name}" for season "{season}" was not found.')
            return None
        if len(rows) > 1:
            messages.append(
                f'Competition "{name}" for season "{season}" matches more than one record.'
            )
            return None
        return int(rows[0]["id"])

    def _resolve(
        self,
        table: str,
        value: str | None,
        label: str,
        messages: list[str],
        optional: bool = False,
    ) -> int | None:
        """Resolve a case-insensitive entity name to one identifier.

        :param table: Trusted entity table to search.
        :param value: Entity name supplied by the CSV row.
        :param label: User-facing field label used in validation messages.
        :param messages: Collection that receives validation failures.
        :param optional: Whether an empty name is permitted.
        :return: The unique matching identifier, or ``None`` on failure or omission.
        """
        name = optional_text(value)
        if name is None:
            if not optional:
                messages.append(f"{label} is required.")
            return None
        rows = self.connection.execute(
            f"SELECT id FROM {table} WHERE name = ? COLLATE NOCASE ORDER BY id", (name,)
        ).fetchall()
        if not rows:
            messages.append(f'{label} "{name}" was not found.')
            return None
        if len(rows) > 1:
            messages.append(f'{label} "{name}" matches more than one record.')
            return None
        return int(rows[0]["id"])

    @staticmethod
    def _value(action: Callable[[], Any], messages: list[str]) -> Any:
        """Run one validator and collect a user-facing failure.

        :param action: Zero-argument validation function.
        :param messages: Collection that receives validation failures.
        :return: The validated value, or ``None`` when validation fails.
        """
        try:
            return action()
        except ValidationError as error:
            messages.append(str(error))
            return None

    @staticmethod
    def _gender(value: str | None) -> str:
        """Normalise a case-insensitive gender category.

        :param value: Category supplied by a CSV row.
        :return: The canonical category used by the database.
        :raises ValidationError: If the category is unsupported.
        """
        candidate = optional_text(value)
        matches = [gender for gender in GENDERS if candidate and gender.casefold() == candidate.casefold()]
        if not matches:
            raise ValidationError("Category must be Men or Women.")
        return matches[0]

    @staticmethod
    def _date(value: str | None) -> str:
        """Validate an imported match date.

        :param value: ISO-formatted date supplied by a CSV row.
        :return: The date in ``YYYY-MM-DD`` format.
        :raises ValidationError: If the value is missing or invalid.
        """
        try:
            return date.fromisoformat(required_text(value, "Match date")).isoformat()
        except ValueError as error:
            raise ValidationError("Match date must be a valid date in YYYY-MM-DD format.") from error

    @staticmethod
    def _time(value: str | None) -> str | None:
        """Validate an optional imported kick-off time.

        :param value: Time supplied by a CSV row.
        :return: Time in ``HH:MM`` format, or ``None`` when omitted.
        :raises ValidationError: If a supplied time is invalid.
        """
        candidate = optional_text(value)
        if candidate is None:
            return None
        try:
            return time.fromisoformat(candidate).strftime("%H:%M")
        except ValueError as error:
            raise ValidationError("Kick-off time must be a valid time in HH:MM format.") from error

    @staticmethod
    def _scores(row: dict[str, str], messages: list[str]) -> dict[str, int | None]:
        """Validate the four optional result fields as one complete group.

        :param row: Normalised CSV row containing try and score fields.
        :param messages: Collection that receives validation failures.
        :return: Prepared score values, with ``None`` values for a fixture.
        """
        fields = ("home_tries", "away_tries", "home_score", "away_score")
        labels = ("Home tries", "Away tries", "Home score", "Away score")
        raw = [optional_text(row.get(name)) for name in fields]
        has_any = any(value is not None for value in raw)
        has_all = all(value is not None for value in raw)
        if has_any and not has_all:
            messages.append("Enter all try and score values, or leave all four blank for a fixture.")
        if not has_any:
            return dict.fromkeys(fields)
        converted: list[int | None] = []
        for value, label in zip(raw, labels, strict=True):
            if value is None:
                converted.append(None)
                continue
            try:
                converted.append(non_negative(value, label))
            except ValidationError as error:
                messages.append(str(error))
                converted.append(None)
        return dict(zip(fields, converted, strict=True))

    def _existing_keys(self, entity_type: str) -> set[tuple[Any, ...]]:
        """Build duplicate keys for records already in the database.

        :param entity_type: Supported entity type being imported.
        :return: Set of normalised duplicate-detection keys.
        """
        if entity_type == "Venues":
            rows = self.connection.execute("SELECT name FROM venues").fetchall()
            return {(row["name"].casefold(),) for row in rows}
        if entity_type == "Teams":
            rows = self.connection.execute("SELECT name, gender FROM teams").fetchall()
            return {(row["name"].casefold(), row["gender"].casefold()) for row in rows}
        if entity_type == "Competitions":
            rows = self.connection.execute("SELECT name, season, gender FROM competitions").fetchall()
            return {(row["name"].casefold(), row["season"].casefold(), row["gender"].casefold()) for row in rows}
        if entity_type == "Referees":
            rows = self.connection.execute("SELECT name FROM referees").fetchall()
            return {(row["name"].casefold(),) for row in rows}
        rows = self.connection.execute(
            "SELECT competition_id, match_date, home_team_id, away_team_id FROM matches"
        ).fetchall()
        return {
            (row["competition_id"], row["match_date"], row["home_team_id"], row["away_team_id"])
            for row in rows
        }

    @staticmethod
    def _duplicate_key(entity_type: str, values: dict[str, Any]) -> tuple[Any, ...]:
        """Build a practical duplicate key for one prepared row.

        :param entity_type: Supported entity type being imported.
        :param values: Validated values ready for persistence.
        :return: Normalised tuple used for duplicate detection.
        """
        if entity_type == "Venues":
            return (values["name"].casefold(),)
        if entity_type == "Teams":
            return values["name"].casefold(), values["gender"].casefold()
        if entity_type == "Competitions":
            return values["name"].casefold(), values["season"].casefold(), values["gender"].casefold()
        if entity_type == "Referees":
            return (values["name"].casefold(),)
        return (
            values["competition_id"], values["match_date"],
            values["home_team_id"], values["away_team_id"],
        )

    def _persist(self, entity_type: str, values: dict[str, Any]) -> int:
        """Persist one validated import row through the business service.

        :param entity_type: Supported entity type being imported.
        :param values: Validated values ready for persistence.
        :return: Identifier of the imported record.
        """
        action = {
            "Venues": self.rugby.save_venue,
            "Teams": self.rugby.save_team,
            "Competitions": self.rugby.save_competition,
            "Referees": self.rugby.save_referee,
            "Matches": self.rugby.save_match,
        }[entity_type]
        return action(**values)
