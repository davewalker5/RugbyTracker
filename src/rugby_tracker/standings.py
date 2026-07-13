"""Ruleset-driven competition calculation and CSV export."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CompetitionFormat:
    """The fixture structure expected by a competition."""

    team_count: int | None = None
    matches_per_team: int | None = None
    single_round_robin: bool = False
    home_and_away: bool = False
    knockout_stage: bool = False


@dataclass(frozen=True)
class ScoringRules:
    """Match, bonus and Grand Slam points awarded by a competition."""

    win_points: int
    draw_points: int
    loss_points: int
    try_bonus_threshold: int
    try_bonus_points: int
    losing_bonus_margin: int
    losing_bonus_points: int
    grand_slam_bonus_points: int = 0


@dataclass(frozen=True)
class LeagueTableRules:
    """Match inclusion and ordered table tie-break criteria."""

    tie_breakers: tuple[str, ...]
    excluded_rounds: frozenset[str] = frozenset()
    share_equal_positions: bool = False


@dataclass(frozen=True)
class AwardRules:
    """Awards enabled for a competition and their eligible teams."""

    champion: bool = False
    grand_slam: bool = False
    triple_crown: bool = False
    wooden_spoon: bool = False
    triple_crown_teams: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Ruleset:
    """All configurable behaviour for one kind of competition."""

    identifier: str
    label: str
    competition: CompetitionFormat
    scoring: ScoringRules
    league_table: LeagueTableRules
    awards: AwardRules = AwardRules()

    # These compatibility properties keep the original small ruleset API useful.
    @property
    def win_points(self) -> int:
        """Return configured points for a win.

        :return: Win points from the scoring section.
        """
        return self.scoring.win_points

    @property
    def draw_points(self) -> int:
        """Return configured points for a draw.

        :return: Draw points from the scoring section.
        """
        return self.scoring.draw_points

    @property
    def try_bonus_threshold(self) -> int:
        """Return the number of tries required for a try bonus.

        :return: Try threshold from the scoring section.
        """
        return self.scoring.try_bonus_threshold

    @property
    def losing_bonus_margin(self) -> int:
        """Return the maximum losing margin that earns a bonus.

        :return: Losing margin from the scoring section.
        """
        return self.scoring.losing_bonus_margin

    @property
    def excluded_rounds(self) -> frozenset[str]:
        """Return rounds excluded from league calculations.

        :return: Normalised excluded round names.
        """
        return self.league_table.excluded_rounds


_CLUB_SCORING = ScoringRules(4, 2, 0, 4, 1, 7, 1)
_CLUB_TABLE = LeagueTableRules(
    tie_breakers=("competition_points", "points_difference"),
    excluded_rounds=frozenset({"quarter-final", "semi-final", "final"}),
)
_HOME_NATIONS = frozenset({"England", "Ireland", "Scotland", "Wales"})


RULESETS = {
    "prem_2025_26": Ruleset(
        "prem_2025_26",
        "Premiership Rugby (2025/26)",
        CompetitionFormat(),
        _CLUB_SCORING,
        _CLUB_TABLE,
    ),
    "pwr_2025_26": Ruleset(
        "pwr_2025_26",
        "Premiership Women's Rugby (2025/26)",
        CompetitionFormat(),
        _CLUB_SCORING,
        _CLUB_TABLE,
    ),
    "m6n": Ruleset(
        "m6n",
        "Men's Six Nations",
        CompetitionFormat(6, 5, single_round_robin=True),
        ScoringRules(4, 2, 0, 4, 1, 7, 1, 3),
        LeagueTableRules(
            ("competition_points", "points_difference", "tries_for"),
            share_equal_positions=True,
        ),
        AwardRules(True, True, True, True, _HOME_NATIONS),
    ),
    "w6n": Ruleset(
        "w6n",
        "Women's Six Nations",
        CompetitionFormat(6, 5, single_round_robin=True),
        ScoringRules(4, 2, 0, 4, 1, 7, 1, 3),
        LeagueTableRules(
            ("competition_points", "points_difference", "tries_for"),
            share_equal_positions=True,
        ),
        AwardRules(True, True, True, True, _HOME_NATIONS),
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
    tries_for: int = 0
    tries_against: int = 0
    try_bonus: int = 0
    losing_bonus: int = 0
    grand_slam_bonus: int = 0
    league_points: int = 0

    @property
    def points_difference(self) -> int:
        """Return points scored minus points conceded.

        :return: Current points difference.
        """
        return self.points_for - self.points_against

    @property
    def bonus_points(self) -> int:
        """Return all try, losing and Grand Slam bonus points.

        :return: Current total bonus points.
        """
        return self.try_bonus + self.losing_bonus + self.grand_slam_bonus

    def as_row(self, position: int) -> dict[str, Any]:
        """Convert this aggregate to a display/export row.

        :param position: One-based competition position.
        :return: A row using the standard abbreviated column names.
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
            "TF": self.tries_for,
            "TA": self.tries_against,
            "TBP": self.try_bonus,
            "LBP": self.losing_bonus,
            "GSBP": self.grand_slam_bonus,
            "BP": self.bonus_points,
            "Pts": self.league_points,
        }


TABLE_COLUMNS = (
    "Pos", "Team", "P", "W", "D", "L", "PF", "PA", "PD", "TF", "TA",
    "TBP", "LBP", "GSBP", "BP", "Pts",
)


def get_ruleset(identifier: str) -> Ruleset:
    """Retrieve a ruleset by its stored identifier.

    :param identifier: Identifier stored on a competition.
    :return: Matching ruleset definition.
    """
    try:
        return RULESETS[identifier]
    except KeyError as error:
        raise ValueError(f"Unknown league-table ruleset: {identifier}") from error


def calculate_table(matches: list[dict[str, Any]], ruleset_identifier: str) -> list[dict[str, Any]]:
    """Calculate an ordered league table from fixture and result records.

    :param matches: Enriched match rows for one competition.
    :param ruleset_identifier: Identifier selecting calculation behavior.
    :return: Ordered rows with one-based, potentially shared positions.
    """
    ruleset = get_ruleset(ruleset_identifier)
    standings = _aggregate(matches, ruleset)
    ordered = sorted(
        standings.values(),
        key=lambda row: (*_ranking_key(row, ruleset), row.team.casefold(), row.team_id),
    )

    rows: list[dict[str, Any]] = []
    previous_rank: tuple[int, ...] | None = None
    position = 0
    for index, standing in enumerate(ordered, start=1):
        rank = _ranking_key(standing, ruleset)
        if not ruleset.league_table.share_equal_positions or rank != previous_rank:
            position = index
        rows.append(standing.as_row(position))
        previous_rank = rank
    return rows


def calculate_competition(
    matches: list[dict[str, Any]], ruleset_identifier: str
) -> dict[str, Any]:
    """Calculate a table together with structure status and final awards.

    :param matches: Enriched match rows for one competition.
    :param ruleset_identifier: Identifier selecting calculation behavior.
    :return: Table, completion flag, validation errors and final awards.
    """
    ruleset = get_ruleset(ruleset_identifier)
    table = calculate_table(matches, ruleset_identifier)
    validation_errors = validate_competition(matches, ruleset_identifier)
    included = _included_matches(matches, ruleset)
    complete = not validation_errors and all(_is_completed(match) for match in included)
    awards = _calculate_awards(matches, table, ruleset) if complete else {}
    return {
        "table": table,
        "complete": complete,
        "validation_errors": validation_errors,
        "awards": awards,
    }


def validate_competition(matches: list[dict[str, Any]], ruleset_identifier: str) -> list[str]:
    """Return human-readable fixture-structure errors for configured formats.

    :param matches: Enriched fixture rows for one competition.
    :param ruleset_identifier: Identifier selecting structure requirements.
    :return: Validation messages, empty when the structure is valid.
    """
    ruleset = get_ruleset(ruleset_identifier)
    format_rules = ruleset.competition
    if format_rules.team_count is None:
        return []

    included = _included_matches(matches, ruleset)
    teams: set[int] = set()
    opponents: set[tuple[int, int]] = set()
    appearances: dict[int, int] = {}
    duplicate_pairing = False
    for match in included:
        home_id = int(match["home_team_id"])
        away_id = int(match["away_team_id"])
        teams.update((home_id, away_id))
        appearances[home_id] = appearances.get(home_id, 0) + 1
        appearances[away_id] = appearances.get(away_id, 0) + 1
        pairing = tuple(sorted((home_id, away_id)))
        duplicate_pairing = duplicate_pairing or pairing in opponents
        opponents.add(pairing)

    errors: list[str] = []
    if len(teams) != format_rules.team_count:
        errors.append(
            f"Expected {format_rules.team_count} teams, found {len(teams)}."
        )
    expected_matches = format_rules.team_count * (format_rules.team_count - 1) // 2
    if format_rules.single_round_robin and len(included) != expected_matches:
        errors.append(f"Expected {expected_matches} matches, found {len(included)}.")
    if format_rules.single_round_robin and duplicate_pairing:
        errors.append("Each pair of teams must play exactly once.")
    if format_rules.matches_per_team is not None and any(
        count != format_rules.matches_per_team for count in appearances.values()
    ):
        errors.append(
            f"Each team must have exactly {format_rules.matches_per_team} matches."
        )
    return errors


def _aggregate(matches: list[dict[str, Any]], ruleset: Ruleset) -> dict[int, Standing]:
    """Aggregate included results by team.

    :param matches: Enriched fixture and result rows.
    :param ruleset: Rules governing inclusion and scoring.
    :return: Mutable standing aggregates keyed by team identifier.
    """
    standings: dict[int, Standing] = {}
    for match in _included_matches(matches, ruleset):
        home = standings.setdefault(
            int(match["home_team_id"]),
            Standing(int(match["home_team_id"]), str(match["home_team_name"])),
        )
        away = standings.setdefault(
            int(match["away_team_id"]),
            Standing(int(match["away_team_id"]), str(match["away_team_name"])),
        )
        if not _is_completed(match):
            continue
        _apply_result(home, away, match, ruleset)

    required_wins = ruleset.competition.matches_per_team
    if required_wins and ruleset.scoring.grand_slam_bonus_points:
        for standing in standings.values():
            if standing.won == required_wins:
                standing.grand_slam_bonus = ruleset.scoring.grand_slam_bonus_points
                standing.league_points += standing.grand_slam_bonus
    return standings


def _included_matches(matches: list[dict[str, Any]], ruleset: Ruleset) -> list[dict[str, Any]]:
    """Filter matches according to the league-table rules.

    :param matches: Candidate match rows.
    :param ruleset: Rules governing match inclusion.
    :return: Match rows that contribute to the competition.
    """
    return [
        match for match in matches
        if str(match.get("round") or "").strip().casefold()
        not in ruleset.league_table.excluded_rounds
    ]


def _is_completed(match: dict[str, Any]) -> bool:
    """Return whether a match has both final scores.

    :param match: Candidate match row.
    :return: ``True`` when the result is complete.
    """
    return match.get("home_score") is not None and match.get("away_score") is not None


def _ranking_key(standing: Standing, ruleset: Ruleset) -> tuple[int, ...]:
    """Build a descending sort key from configured criteria.

    :param standing: Aggregated team record.
    :param ruleset: Rules containing ordered tie-break criteria.
    :return: Numeric key suitable for ascending sorting.
    """
    values = {
        "competition_points": standing.league_points,
        "points_difference": standing.points_difference,
        "tries_for": standing.tries_for,
    }
    return tuple(-values[criterion] for criterion in ruleset.league_table.tie_breakers)


def _apply_result(home: Standing, away: Standing, match: dict[str, Any], ruleset: Ruleset) -> None:
    """Apply one completed match to two aggregates.

    :param home: Home-team aggregate.
    :param away: Away-team aggregate.
    :param match: Completed result row.
    :param ruleset: Rules governing points and bonuses.
    :return: None.
    """
    scoring = ruleset.scoring
    home_score = int(match["home_score"])
    away_score = int(match["away_score"])
    home_tries = int(match["home_tries"])
    away_tries = int(match["away_tries"])
    home.played += 1
    away.played += 1
    home.points_for += home_score
    home.points_against += away_score
    away.points_for += away_score
    away.points_against += home_score
    home.tries_for += home_tries
    home.tries_against += away_tries
    away.tries_for += away_tries
    away.tries_against += home_tries

    if home_tries >= scoring.try_bonus_threshold:
        home.try_bonus += scoring.try_bonus_points
        home.league_points += scoring.try_bonus_points
    if away_tries >= scoring.try_bonus_threshold:
        away.try_bonus += scoring.try_bonus_points
        away.league_points += scoring.try_bonus_points

    if home_score == away_score:
        home.drawn += 1
        away.drawn += 1
        home.league_points += scoring.draw_points
        away.league_points += scoring.draw_points
        return

    winner, loser = (home, away) if home_score > away_score else (away, home)
    winner.won += 1
    winner.league_points += scoring.win_points
    loser.lost += 1
    loser.league_points += scoring.loss_points
    if abs(home_score - away_score) <= scoring.losing_bonus_margin:
        loser.losing_bonus += scoring.losing_bonus_points
        loser.league_points += scoring.losing_bonus_points


def _calculate_awards(
    matches: list[dict[str, Any]], table: list[dict[str, Any]], ruleset: Ruleset
) -> dict[str, tuple[str, ...]]:
    """Determine enabled awards for a complete, structurally valid competition.

    :param matches: Complete enriched result rows.
    :param table: Final ordered table.
    :param ruleset: Rules governing award availability and eligibility.
    :return: Award names mapped to zero, one or several team names.
    """
    awards: dict[str, tuple[str, ...]] = {}
    names_by_id: dict[int, str] = {}
    wins: dict[int, set[int]] = {}
    for match in _included_matches(matches, ruleset):
        home_id = int(match["home_team_id"])
        away_id = int(match["away_team_id"])
        names_by_id[home_id] = str(match["home_team_name"])
        names_by_id[away_id] = str(match["away_team_name"])
        home_score = int(match["home_score"])
        away_score = int(match["away_score"])
        if home_score != away_score:
            winner, loser = (
                (home_id, away_id) if home_score > away_score else (away_id, home_id)
            )
            wins.setdefault(winner, set()).add(loser)

    if ruleset.awards.champion and table:
        awards["Champion"] = tuple(row["Team"] for row in table if row["Pos"] == 1)
    if ruleset.awards.grand_slam:
        needed = ruleset.competition.matches_per_team or 0
        awards["Grand Slam"] = tuple(
            names_by_id[team_id] for team_id, defeated in wins.items() if len(defeated) == needed
        )
    if ruleset.awards.triple_crown:
        eligible_ids = {
            team_id for team_id, name in names_by_id.items()
            if name.casefold() in {team.casefold() for team in ruleset.awards.triple_crown_teams}
        }
        awards["Triple Crown"] = tuple(
            names_by_id[team_id] for team_id in eligible_ids
            if eligible_ids - {team_id} <= wins.get(team_id, set())
        )
    if ruleset.awards.wooden_spoon and table:
        last_position = max(int(row["Pos"]) for row in table)
        awards["Wooden Spoon"] = tuple(
            row["Team"] for row in table if row["Pos"] == last_position
        )
    return awards


def table_to_csv(table: list[dict[str, Any]]) -> str:
    """Serialise a calculated league table to CSV.

    :param table: Rows returned by :func:`calculate_table`.
    :return: CSV text including the standard table header.
    """
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=TABLE_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(table)
    return output.getvalue()
