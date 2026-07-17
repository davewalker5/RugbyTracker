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
    playoff_teams: int = 0


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
_INTERNATIONAL_SCORING = ScoringRules(4, 2, 0, 4, 1, 7, 1)
_INTERNATIONAL_TABLE = LeagueTableRules(
    ("competition_points", "points_difference", "tries_for")
)


RULESETS = {
    "prem_2025_26": Ruleset(
        "prem_2025_26",
        "Premiership Rugby (2025/26)",
        CompetitionFormat(
            team_count=10,
            matches_per_team=18,
            home_and_away=True,
            knockout_stage=True,
            playoff_teams=4,
        ),
        _CLUB_SCORING,
        LeagueTableRules(
            (
                "competition_points", "wins", "points_difference",
                "points_for", "head_to_head_points",
            ),
            excluded_rounds=frozenset({"quarter-final", "semi-final", "final"}),
            share_equal_positions=True,
        ),
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
    "wxv_global_2026": Ruleset(
        "wxv_global_2026",
        "WXV Global Series (2026)",
        CompetitionFormat(team_count=12),
        _INTERNATIONAL_SCORING,
        _INTERNATIONAL_TABLE,
        AwardRules(champion=True),
    ),
    "wxv_challenger_2026": Ruleset(
        "wxv_challenger_2026",
        "WXV Global Series Challenger (2026)",
        CompetitionFormat(team_count=6, matches_per_team=3),
        _INTERNATIONAL_SCORING,
        _INTERNATIONAL_TABLE,
        AwardRules(champion=True),
    ),
    "nations_2026": Ruleset(
        "nations_2026",
        "Nations Championship Series (2026)",
        # Each geographic series contains three cross-hemisphere fixtures per team.
        CompetitionFormat(team_count=12, matches_per_team=3),
        _INTERNATIONAL_SCORING,
        LeagueTableRules(
            ("competition_points", "wins", "points_difference", "tries_for")
        ),
        AwardRules(champion=True),
    ),
}


@dataclass
class Standing:
    """Mutable aggregate for one team while a table is calculated."""

    team_id: int
    team: str
    country: str = ""
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
            "Country": self.country,
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
    "Pos", "Team", "Country", "P", "W", "D", "L", "PF", "PA", "PD", "TF", "TA",
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
    head_to_head = _head_to_head_points(matches, standings, ruleset)
    ordered = sorted(
        standings.values(),
        key=lambda row: (
            *_ranking_key(row, ruleset, head_to_head), row.team.casefold(), row.team_id
        ),
    )

    rows: list[dict[str, Any]] = []
    previous_rank: tuple[int, ...] | None = None
    position = 0
    for index, standing in enumerate(ordered, start=1):
        rank = _ranking_key(standing, ruleset, head_to_head)
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
    qualifiers: tuple[str, ...] = ()
    semi_finals: tuple[tuple[str, str], ...] = ()
    if complete and ruleset.competition.playoff_teams:
        cutoff = ruleset.competition.playoff_teams
        cutoff_is_decided = len(table) == cutoff or (
            len(table) > cutoff and table[cutoff - 1]["Pos"] != table[cutoff]["Pos"]
        )
        if cutoff_is_decided:
            qualifiers = tuple(str(row["Team"]) for row in table[:cutoff])
        seeds_are_decided = len({row["Pos"] for row in table[:cutoff]}) == cutoff
        if len(qualifiers) == 4 and seeds_are_decided:
            semi_finals = ((qualifiers[0], qualifiers[3]), (qualifiers[1], qualifiers[2]))
    return {
        "table": table,
        "complete": complete,
        "validation_errors": validation_errors,
        "awards": awards,
        "qualifiers": qualifiers,
        "semi_finals": semi_finals,
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
    directed_pairings: set[tuple[int, int]] = set()
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
        directed_pairings.add((home_id, away_id))

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
    if format_rules.home_and_away:
        expected_matches *= 2
        if len(included) != expected_matches:
            errors.append(f"Expected {expected_matches} matches, found {len(included)}.")
        if len(teams) == format_rules.team_count and any(
            home_id == away_id or (away_id, home_id) not in directed_pairings
            for home_id, away_id in directed_pairings
        ):
            errors.append("Each pair of teams must play once at home and once away.")
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
            Standing(
                int(match["home_team_id"]), str(match["home_team_name"]),
                str(match.get("home_team_country") or ""),
            ),
        )
        away = standings.setdefault(
            int(match["away_team_id"]),
            Standing(
                int(match["away_team_id"]), str(match["away_team_name"]),
                str(match.get("away_team_country") or ""),
            ),
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
        if _normalised_stage(match) not in ruleset.league_table.excluded_rounds
    ]


def _normalised_stage(match: dict[str, Any]) -> str:
    """Return a canonical stage, preferring an explicit stage field when supplied.

    :param match: Candidate match with a stage, match type or round value.
    :return: Case-folded, hyphenated canonical stage name.
    """
    value = match.get("stage") or match.get("match_type") or match.get("round") or ""
    stage = "-".join(str(value).strip().casefold().replace("_", " ").split())
    aliases = {
        "semifinal": "semi-final",
        "semi-finals": "semi-final",
        "semifinals": "semi-final",
        "the-final": "final",
    }
    return aliases.get(stage, stage)


def _is_completed(match: dict[str, Any]) -> bool:
    """Return whether a match has both final scores.

    :param match: Candidate match row.
    :return: ``True`` when the result is complete.
    """
    return match.get("home_score") is not None and match.get("away_score") is not None


def _ranking_key(
    standing: Standing,
    ruleset: Ruleset,
    head_to_head: dict[int, int] | None = None,
) -> tuple[int, ...]:
    """Build a descending sort key from configured criteria.

    :param standing: Aggregated team record.
    :param ruleset: Rules containing ordered tie-break criteria.
    :param head_to_head: Optional aggregate direct-fixture points keyed by team.
    :return: Numeric key suitable for ascending sorting.
    """
    values = {
        "competition_points": standing.league_points,
        "wins": standing.won,
        "points_difference": standing.points_difference,
        "points_for": standing.points_for,
        "tries_for": standing.tries_for,
        "head_to_head_points": (head_to_head or {}).get(standing.team_id, 0),
    }
    return tuple(-values[criterion] for criterion in ruleset.league_table.tie_breakers)


def _head_to_head_points(
    matches: list[dict[str, Any]],
    standings: dict[int, Standing],
    ruleset: Ruleset,
) -> dict[int, int]:
    """Return points scored against teams level on all preceding criteria.

    :param matches: Enriched fixture and result rows.
    :param standings: Aggregated regular-season standings keyed by team.
    :param ruleset: Rules containing the ordered tie-break criteria.
    :return: Aggregate direct-fixture match points keyed by tied team.
    """
    criteria = ruleset.league_table.tie_breakers
    if "head_to_head_points" not in criteria:
        return {}
    preceding = criteria[:criteria.index("head_to_head_points")]
    groups: dict[tuple[int, ...], set[int]] = {}
    for standing in standings.values():
        key = _ranking_key(
            standing,
            Ruleset(
                ruleset.identifier, ruleset.label, ruleset.competition, ruleset.scoring,
                LeagueTableRules(preceding), ruleset.awards,
            ),
        )
        groups.setdefault(key, set()).add(standing.team_id)

    scores = {team_id: 0 for team_id in standings}
    tied_by_team = {
        team_id: group
        for group in groups.values() if len(group) > 1
        for team_id in group
    }
    for match in _included_matches(matches, ruleset):
        if not _is_completed(match):
            continue
        home_id = int(match["home_team_id"])
        away_id = int(match["away_team_id"])
        if away_id not in tied_by_team.get(home_id, set()):
            continue
        scores[home_id] += int(match["home_score"])
        scores[away_id] += int(match["away_score"])
    return scores


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
