"""Validation and business operations for the application."""

from __future__ import annotations

import sqlite3
from datetime import date, time
from typing import Any

from rugby_tracker.repositories import Repository, RugbyRepository


GENDERS = ("Men's", "Women's")


class ValidationError(ValueError):
    """An input error that is safe to display to a user."""


def required_text(value: Any, label: str) -> str:
    cleaned = str(value).strip() if value is not None else ""
    if not cleaned:
        raise ValidationError(f"{label} is required.")
    return cleaned


def optional_text(value: Any) -> str | None:
    cleaned = str(value).strip() if value is not None else ""
    return cleaned or None


def valid_gender(value: Any) -> str:
    if value not in GENDERS:
        raise ValidationError("Category must be Men's or Women's.")
    return str(value)


def non_negative(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValidationError(f"{label} must be a whole number of zero or more.")
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValidationError(f"{label} must be a whole number of zero or more.") from error
    if number < 0 or (isinstance(value, float) and not value.is_integer()):
        raise ValidationError(f"{label} must be a whole number of zero or more.")
    return number


class RugbyService:
    def __init__(self, connection: sqlite3.Connection):
        self.repo = RugbyRepository(connection)

    def list_venues(self) -> list[dict[str, Any]]:
        return self.repo.venues.list_all()

    def save_venue(self, entity_id: int | None = None, **values: Any) -> int:
        data = {
            "name": required_text(values.get("name"), "Venue name"),
            "town_city": optional_text(values.get("town_city")),
            "country": optional_text(values.get("country")),
        }
        return self._save(self.repo.venues, entity_id, data)

    def list_teams(self) -> list[dict[str, Any]]:
        return self.repo.teams.list_all()

    def save_team(self, entity_id: int | None = None, **values: Any) -> int:
        name = required_text(values.get("name"), "Team name")
        gender = valid_gender(values.get("gender"))
        venue_id = self._foreign_key(self.repo.venues, values.get("home_venue_id"), "Home venue")
        data = {
            "name": name,
            "gender": gender,
            "home_venue_id": venue_id,
        }
        return self._save(self.repo.teams, entity_id, data)

    def list_competitions(self) -> list[dict[str, Any]]:
        return self.repo.competitions.list_all()

    def save_competition(self, entity_id: int | None = None, **values: Any) -> int:
        data = {
            "name": required_text(values.get("name"), "Competition name"),
            "season": required_text(values.get("season"), "Season"),
            "gender": valid_gender(values.get("gender")),
        }
        return self._save(self.repo.competitions, entity_id, data)

    def list_referees(self) -> list[dict[str, Any]]:
        return self.repo.referees.list_all()

    def save_referee(self, entity_id: int | None = None, **values: Any) -> int:
        return self._save(
            self.repo.referees,
            entity_id,
            {"name": required_text(values.get("name"), "Referee name")},
        )

    def list_matches(self, competition_id: int | None = None) -> list[dict[str, Any]]:
        return self.repo.list_matches(competition_id)

    def save_match(self, entity_id: int | None = None, **values: Any) -> int:
        competition_id = self._foreign_key(
            self.repo.competitions, values.get("competition_id"), "Competition"
        )
        venue_id = self._foreign_key(self.repo.venues, values.get("venue_id"), "Venue")
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
        repositories = {
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

    def competition_summary(self, competition_id: int) -> dict[str, Any]:
        competition = self.repo.competitions.get(competition_id)
        if competition is None:
            raise ValidationError("Select a valid competition.")
        matches = self.repo.list_matches(competition_id)
        rounds: list[dict[str, Any]] = []
        by_name: dict[str, dict[str, Any]] = {}
        for match in matches:
            name = match["round"] or "Unspecified round"
            if name not in by_name:
                by_name[name] = {"name": name, "matches": []}
                rounds.append(by_name[name])
            match["is_result"] = match["home_score"] is not None
            match.update(self._outcome(match))
            by_name[name]["matches"].append(match)
        return {"competition": competition, "rounds": rounds, "matches": matches}

    @staticmethod
    def _save(repository: Repository, entity_id: int | None, data: dict[str, Any]) -> int:
        try:
            if entity_id is None:
                return repository.insert(data)
            repository.update(entity_id, data)
            return entity_id
        except sqlite3.IntegrityError as error:
            raise ValidationError("The record could not be saved because it contains invalid or referenced data.") from error

    @staticmethod
    def _foreign_key(repository: Repository, value: Any, label: str) -> int:
        try:
            entity_id = int(value)
        except (TypeError, ValueError) as error:
            raise ValidationError(f"{label} is required.") from error
        if repository.get(entity_id) is None:
            raise ValidationError(f"Select a valid {label.lower()}.")
        return entity_id

    @staticmethod
    def _date_value(value: Any) -> str:
        if isinstance(value, date):
            return value.isoformat()
        try:
            return date.fromisoformat(required_text(value, "Match date")).isoformat()
        except ValueError as error:
            raise ValidationError("Match date must be a valid date.") from error

    @staticmethod
    def _time_value(value: Any) -> str | None:
        if value in (None, ""):
            return None
        if isinstance(value, time):
            return value.strftime("%H:%M")
        try:
            return time.fromisoformat(str(value)).strftime("%H:%M")
        except ValueError as error:
            raise ValidationError("Kick-off time must be a valid time.") from error

    @staticmethod
    def _outcome(match: dict[str, Any]) -> dict[str, Any]:
        if match["home_score"] is None:
            return {"winner": None, "loser": None, "is_draw": False}
        if match["home_score"] == match["away_score"]:
            return {"winner": None, "loser": None, "is_draw": True}
        if match["home_score"] > match["away_score"]:
            return {
                "winner": match["home_team_name"],
                "loser": match["away_team_name"],
                "is_draw": False,
            }
        return {
            "winner": match["away_team_name"],
            "loser": match["home_team_name"],
            "is_draw": False,
        }
