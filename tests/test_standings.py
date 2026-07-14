from __future__ import annotations

import csv
import io

import pytest

from rugby_tracker.services import ValidationError
from rugby_tracker.standings import (
    RULESETS,
    calculate_competition,
    calculate_table,
    table_to_csv,
    validate_competition,
)


def match(
    home_id,
    home_name,
    away_id,
    away_name,
    home_score,
    away_score,
    home_tries,
    away_tries,
    round_name=None,
):
    return {
        "home_team_id": home_id,
        "home_team_name": home_name,
        "away_team_id": away_id,
        "away_team_name": away_name,
        "home_score": home_score,
        "away_score": away_score,
        "home_tries": home_tries,
        "away_tries": away_tries,
        "round": round_name,
    }


def test_table_calculates_every_required_column_and_order():
    matches = [
        match(1, "Alpha", 2, "Bravo", 30, 25, 4, 3),
        match(2, "Bravo", 3, "Charlie", 20, 20, 4, 4),
        match(3, "Charlie", 1, "Alpha", 40, 10, 5, 2),
    ]
    table = calculate_table(matches, "prem_2025_26")

    assert table == [
        {"Pos": 1, "Team": "Charlie", "P": 2, "W": 1, "D": 1, "L": 0,
         "PF": 60, "PA": 30, "PD": 30, "TF": 9, "TA": 6,
         "TBP": 2, "LBP": 0, "GSBP": 0, "BP": 2, "Pts": 8},
        {"Pos": 2, "Team": "Alpha", "P": 2, "W": 1, "D": 0, "L": 1,
         "PF": 40, "PA": 65, "PD": -25, "TF": 6, "TA": 8,
         "TBP": 1, "LBP": 0, "GSBP": 0, "BP": 1, "Pts": 5},
        {"Pos": 3, "Team": "Bravo", "P": 2, "W": 0, "D": 1, "L": 1,
         "PF": 45, "PA": 50, "PD": -5, "TF": 7, "TA": 8,
         "TBP": 1, "LBP": 1, "GSBP": 0, "BP": 2, "Pts": 4},
    ]


def test_losing_bonus_includes_seven_points_but_not_eight():
    table = calculate_table(
        [
            match(1, "Winner", 2, "Seven", 27, 20, 3, 3),
            match(1, "Winner", 3, "Eight", 28, 20, 3, 3),
        ],
        "pwr_2025_26",
    )
    by_team = {row["Team"]: row for row in table}
    assert by_team["Seven"]["LBP"] == 1
    assert by_team["Seven"]["Pts"] == 1
    assert by_team["Eight"]["LBP"] == 0
    assert by_team["Eight"]["Pts"] == 0


def test_future_fixture_includes_teams_without_affecting_values():
    table = calculate_table(
        [match(1, "Alpha", 2, "Bravo", None, None, None, None)],
        "prem_2025_26",
    )
    assert [row["Team"] for row in table] == ["Alpha", "Bravo"]
    assert all(row["P"] == 0 and row["Pts"] == 0 for row in table)


@pytest.mark.parametrize("round_name", ("Quarter-Final", "Semi-Final", "Final", "semi-final"))
@pytest.mark.parametrize("ruleset", ("prem_2025_26", "pwr_2025_26"))
def test_knockout_rounds_are_excluded_from_league_tables(round_name, ruleset):
    regular = match(1, "Alpha", 2, "Bravo", 20, 10, 3, 1, "Round 18")
    knockout = match(2, "Bravo", 1, "Alpha", 50, 0, 7, 0, round_name)
    table = calculate_table([regular, knockout], ruleset)
    by_team = {row["Team"]: row for row in table}

    assert by_team["Alpha"]["P"] == 1
    assert by_team["Alpha"]["Pts"] == 4
    assert by_team["Alpha"]["PD"] == 10
    assert by_team["Bravo"]["P"] == 1
    assert by_team["Bravo"]["Pts"] == 0


def test_table_ranks_by_points_then_points_difference_not_wins():
    matches = [
        match(1, "One Win", 2, "Opponent B", 10, 9, 0, 0),
        match(3, "Opponent D", 1, "One Win", 100, 0, 0, 0),
        match(4, "No Wins", 5, "Opponent E", 3, 3, 0, 0),
        match(4, "No Wins", 6, "Opponent F", 6, 6, 0, 0),
    ]
    table = calculate_table(matches, "prem_2025_26")
    positions = {row["Team"]: row["Pos"] for row in table}

    assert next(row for row in table if row["Team"] == "One Win")["Pts"] == 4
    assert next(row for row in table if row["Team"] == "No Wins")["Pts"] == 4
    assert positions["No Wins"] < positions["One Win"]


def test_2025_26_rulesets_have_independent_identifiers_and_currently_same_result():
    matches = [match(1, "Alpha", 2, "Bravo", 31, 27, 4, 4)]
    assert set(RULESETS) == {
        "prem_2025_26", "pwr_2025_26", "m6n", "w6n",
        "wxv_global_2026", "wxv_challenger_2026",
    }
    assert calculate_table(matches, "prem_2025_26") == calculate_table(matches, "pwr_2025_26")


def test_wxv_rulesets_use_international_scoring_and_published_structures():
    """Verify the two 2026 WXV competition definitions.

    :return: None.
    """
    # Global uses selected fixtures, while Challenger gives each team three games.
    global_series = RULESETS["wxv_global_2026"]
    challenger = RULESETS["wxv_challenger_2026"]

    assert global_series.competition.team_count == 12
    assert global_series.competition.single_round_robin is False
    assert challenger.competition.team_count == 6
    assert challenger.competition.matches_per_team == 3
    assert global_series.scoring == challenger.scoring
    assert global_series.league_table.tie_breakers == (
        "competition_points", "points_difference", "tries_for"
    )


def test_unknown_ruleset_is_rejected():
    with pytest.raises(ValueError, match="Unknown league-table ruleset"):
        calculate_table([], "unknown")


def test_table_csv_has_the_required_columns_and_rows():
    table = calculate_table(
        [match(1, "Alpha", 2, "Bravo", 20, 10, 4, 1)],
        "prem_2025_26",
    )
    rows = list(csv.DictReader(io.StringIO(table_to_csv(table))))
    assert list(rows[0]) == [
        "Pos", "Team", "P", "W", "D", "L", "PF", "PA", "PD", "TF", "TA",
        "TBP", "LBP", "GSBP", "BP", "Pts",
    ]
    assert rows[0]["Team"] == "Alpha"
    assert rows[0]["Pts"] == "5"


def test_service_requires_ruleset_then_calculates_and_exports(service, core_records):
    with pytest.raises(ValidationError, match="ruleset"):
        service.league_table(core_records["competition"])

    service.save_competition(
        entity_id=core_records["competition"],
        name="Premiership Rugby",
        season="2025/26",
        gender="Men",
        ruleset="prem_2025_26",
    )
    service.save_match(
        competition_id=core_records["competition"],
        venue_id=core_records["venue"],
        match_date="2025-09-20",
        home_team_id=core_records["home"],
        away_team_id=core_records["away"],
        home_tries=4,
        away_tries=2,
        home_score=31,
        away_score=17,
    )
    result = service.league_table(core_records["competition"])
    assert result["table"][0]["Team"] == "Bath"
    assert result["table"][0]["Pts"] == 5
    assert "Bath" in service.league_table_csv(core_records["competition"])


SIX_NATIONS_TEAMS = ("England", "France", "Ireland", "Italy", "Scotland", "Wales")


def six_nations_results(result_for_pair=None):
    """Build one complete Six Nations round robin for competition tests."""
    results = []
    for home_id, home_name in enumerate(SIX_NATIONS_TEAMS, start=1):
        for away_id, away_name in list(enumerate(SIX_NATIONS_TEAMS, start=1))[home_id:]:
            score = result_for_pair(home_name, away_name) if result_for_pair else (0, 0, 0, 0)
            results.append(match(home_id, home_name, away_id, away_name, *score))
    return results


def test_six_nations_rulesets_are_separate_complete_definitions():
    men = RULESETS["m6n"]
    women = RULESETS["w6n"]

    assert men is not women
    assert men.competition is not women.competition
    assert men.scoring is not women.scoring
    assert men.league_table is not women.league_table
    assert men.awards is not women.awards
    assert men.competition.team_count == women.competition.team_count == 6
    assert men.competition.matches_per_team == women.competition.matches_per_team == 5
    assert men.scoring.grand_slam_bonus_points == women.scoring.grand_slam_bonus_points == 3
    assert men.league_table.tie_breakers == (
        "competition_points", "points_difference", "tries_for"
    )


@pytest.mark.parametrize("ruleset", ("m6n", "w6n"))
def test_clean_grand_slam_gets_three_points_and_all_awards(ruleset):
    def england_wins(home, away):
        if home == "England":
            return 20, 10, 3, 1
        if away == "England":
            return 10, 20, 1, 3
        return 10, 10, 1, 1

    result = calculate_competition(six_nations_results(england_wins), ruleset)
    england = next(row for row in result["table"] if row["Team"] == "England")

    assert result["complete"] is True
    assert england["W"] == 5
    assert england["GSBP"] == 3
    assert england["Pts"] == 23
    assert result["awards"]["Champion"] == ("England",)
    assert result["awards"]["Grand Slam"] == ("England",)
    assert result["awards"]["Triple Crown"] == ("England",)


def test_triple_crown_can_be_won_without_a_grand_slam():
    home_nations = {"England", "Ireland", "Scotland", "Wales"}

    def results(home, away):
        if "England" in (home, away):
            opponent = away if home == "England" else home
            england_wins = opponent in home_nations or opponent == "Italy"
            home_wins = england_wins == (home == "England")
            return (20, 10, 2, 1) if home_wins else (10, 20, 1, 2)
        return 10, 10, 1, 1

    outcome = calculate_competition(six_nations_results(results), "m6n")

    assert outcome["awards"]["Grand Slam"] == ()
    assert outcome["awards"]["Triple Crown"] == ("England",)


def test_six_nations_uses_tries_as_third_tiebreak_and_shares_equal_positions():
    table = calculate_table(
        [
            match(1, "More Tries", 3, "Opponent A", 20, 10, 4, 0),
            match(2, "Fewer Tries", 4, "Opponent B", 20, 10, 3, 0),
            match(5, "Equal A", 6, "Equal B", None, None, None, None),
        ],
        "m6n",
    )
    positions = {row["Team"]: row["Pos"] for row in table}

    assert positions["More Tries"] < positions["Fewer Tries"]
    assert positions["Equal A"] == positions["Equal B"]


def test_complete_tie_produces_shared_championship():
    outcome = calculate_competition(six_nations_results(), "w6n")

    assert outcome["complete"] is True
    assert outcome["awards"]["Champion"] == SIX_NATIONS_TEAMS
    assert {row["Pos"] for row in outcome["table"]} == {1}


def test_champion_can_be_decided_on_points_difference():
    def results(home, away):
        if (home, away) == ("England", "France"):
            return 10, 18, 1, 2
        if (home, away) == ("France", "Italy"):
            return 0, 20, 0, 3
        if home == "England":
            return 30, 10, 3, 1
        if away == "England":
            return 10, 30, 1, 3
        if home == "France":
            return 15, 10, 2, 1
        if away == "France":
            return 10, 15, 1, 2
        return 10, 10, 1, 1

    outcome = calculate_competition(six_nations_results(results), "m6n")
    england = next(row for row in outcome["table"] if row["Team"] == "England")
    france = next(row for row in outcome["table"] if row["Team"] == "France")

    assert england["Pts"] == france["Pts"] == 16
    assert england["PD"] > france["PD"]
    assert outcome["awards"]["Champion"] == ("England",)


def test_wooden_spoon_uses_final_try_tiebreak():
    bottom = {"Italy", "Wales"}

    def results(home, away):
        if {home, away} == bottom:
            return 10, 10, 3, 2
        if home in bottom:
            return 10, 20, 0, 2
        if away in bottom:
            return 20, 10, 2, 0
        return 10, 10, 1, 1

    outcome = calculate_competition(six_nations_results(results), "w6n")
    italy = next(row for row in outcome["table"] if row["Team"] == "Italy")
    wales = next(row for row in outcome["table"] if row["Team"] == "Wales")

    assert italy["Pts"] == wales["Pts"]
    assert italy["PD"] == wales["PD"]
    assert italy["TF"] > wales["TF"]
    assert outcome["awards"]["Wooden Spoon"] == ("Wales",)


def test_awards_wait_for_a_valid_complete_competition():
    incomplete = [match(1, "England", 2, "France", 20, 10, 2, 1)]

    errors = validate_competition(incomplete, "m6n")
    outcome = calculate_competition(incomplete, "m6n")

    assert "Expected 6 teams, found 2." in errors
    assert "Expected 15 matches, found 1." in errors
    assert outcome["complete"] is False
    assert outcome["awards"] == {}
