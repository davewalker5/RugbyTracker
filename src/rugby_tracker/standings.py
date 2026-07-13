"""Ruleset-driven league-table calculation and CSV export."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Ruleset:
    """League points and bonus thresholds for a competition."""

    identifier: str
    label: str
    win_points: int
    draw_points: int
    try_bonus_threshold: int
    losing_bonus_margin: int
    excluded_rounds: frozenset[str]


RULESETS = {
    "prem_2025_26": Ruleset(
        identifier="prem_2025_26",
        label="Premiership Rugby (2025/26)",
        win_points=4,
        draw_points=2,
        try_bonus_threshold=4,
        losing_bonus_margin=7,
        excluded_rounds=frozenset({"quarter-final", "semi-final", "final"}),
    ),
    "pwr_2025_26": Ruleset(
        identifier="pwr_2025_26",
        label="Premiership Women's Rugby (2025/26)",
        win_points=4,
        draw_points=2,
        try_bonus_threshold=4,
        losing_bonus_margin=7,
        excluded_rounds=frozenset({"quarter-final", "semi-final", "final"}),
    ),
}


@dataclass
class Standing:
    """Mutable aggregate for one team while a table is calculated."""

    team_id: int
    team: str
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    points_for: int = 0
    points_against: int = 0
    try_bonus: int = 0
    losing_bonus: int = 0
    league_points: int = 0

    @property
    def points_difference(self) -> int:
        """Calculate points scored minus points conceded.

        :return: The team's current points difference.
        """
        return self.points_for - self.points_against

    @property
    def bonus_points(self) -> int:
        """Calculate total try and losing bonus points.

        :return: The team's total bonus points.
        """
        return self.try_bonus + self.losing_bonus

    def as_row(self, position: int) -> dict[str, Any]:
        """Convert the aggregate to a display and export row.

        :param position: One-based position in the sorted league table.
        :return: Dictionary using the column names from the project brief.
        """
        return {
            "Pos": position,
            "Team": self.team,
            "P": self.played,
            "W": self.won,
            "D": self.drawn,
            "L": self.lost,
            "PF": self.points_for,
            "PA": self.points_against,
            "PD": self.points_difference,
            "TBP": self.try_bonus,
            "LBP": self.losing_bonus,
            "BP": self.bonus_points,
            "Pts": self.league_points,
        }


TABLE_COLUMNS = ("Pos", "Team", "P", "W", "D", "L", "PF", "PA", "PD", "TBP", "LBP", "BP", "Pts")


def get_ruleset(identifier: str) -> Ruleset:
    """Retrieve a ruleset by its stored identifier.

    :param identifier: Identifier stored against a competition.
    :return: The matching ruleset definition.
    :raises ValueError: If the identifier is unsupported.
    """
    try:
        return RULESETS[identifier]
    except KeyError as error:
        raise ValueError(f"Unknown league-table ruleset: {identifier}") from error


def calculate_table(matches: list[dict[str, Any]], ruleset_identifier: str) -> list[dict[str, Any]]:
    """Calculate a league table entirely from match records.

    Teams from future fixtures are included with zero matches played, while only
    completed results contribute to table values.

    :param matches: Enriched match rows for one competition.
    :param ruleset_identifier: Stored identifier selecting the calculation rules.
    :return: Sorted league-table rows with one-based positions.
    """
    ruleset = get_ruleset(ruleset_identifier)
    standings: dict[int, Standing] = {}
    for match in matches:
        round_name = str(match.get("round") or "").strip().casefold()
        if round_name in ruleset.excluded_rounds:
            continue
        home = standings.setdefault(
            int(match["home_team_id"]),
            Standing(int(match["home_team_id"]), str(match["home_team_name"])),
        )
        away = standings.setdefault(
            int(match["away_team_id"]),
            Standing(int(match["away_team_id"]), str(match["away_team_name"])),
        )
        if match["home_score"] is None:
            continue
        _apply_result(home, away, match, ruleset)
    ordered = sorted(
        standings.values(),
        key=lambda row: (
            -row.league_points,
            -row.points_difference,
            row.team.casefold(),
            row.team_id,
        ),
    )
    return [standing.as_row(position) for position, standing in enumerate(ordered, start=1)]


def _apply_result(
    home: Standing,
    away: Standing,
    match: dict[str, Any],
    ruleset: Ruleset,
) -> None:
    """Apply one completed result to its home and away aggregates.

    :param home: Aggregate for the home team.
    :param away: Aggregate for the away team.
    :param match: Completed match containing scores and try counts.
    :param ruleset: Rules governing league and bonus points.
    :return: None.
    """
    home_score = int(match["home_score"])
    away_score = int(match["away_score"])
    home.played += 1
    away.played += 1
    home.points_for += home_score
    home.points_against += away_score
    away.points_for += away_score
    away.points_against += home_score

    if int(match["home_tries"]) >= ruleset.try_bonus_threshold:
        home.try_bonus += 1
        home.league_points += 1
    if int(match["away_tries"]) >= ruleset.try_bonus_threshold:
        away.try_bonus += 1
        away.league_points += 1

    if home_score == away_score:
        home.drawn += 1
        away.drawn += 1
        home.league_points += ruleset.draw_points
        away.league_points += ruleset.draw_points
        return

    winner, loser = (home, away) if home_score > away_score else (away, home)
    winner.won += 1
    winner.league_points += ruleset.win_points
    loser.lost += 1
    if abs(home_score - away_score) <= ruleset.losing_bonus_margin:
        loser.losing_bonus += 1
        loser.league_points += 1


def table_to_csv(table: list[dict[str, Any]]) -> str:
    """Serialise a calculated league table to CSV.

    :param table: League-table rows returned by :func:`calculate_table`.
    :return: CSV text including the standard table header.
    """
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=TABLE_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(table)
    return output.getvalue()
