from __future__ import annotations

import csv
import io

import pytest

from rugby_tracker.services import ValidationError
from rugby_tracker.standings import RULESETS, calculate_table, table_to_csv


def match(
    home_id,
    home_name,
    away_id,
    away_name,
    home_score,
    away_score,
    home_tries,
    away_tries,
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
         "PF": 60, "PA": 30, "PD": 30, "TBP": 2, "LBP": 0, "BP": 2, "Pts": 8},
        {"Pos": 2, "Team": "Alpha", "P": 2, "W": 1, "D": 0, "L": 1,
         "PF": 40, "PA": 65, "PD": -25, "TBP": 1, "LBP": 0, "BP": 1, "Pts": 5},
        {"Pos": 3, "Team": "Bravo", "P": 2, "W": 0, "D": 1, "L": 1,
         "PF": 45, "PA": 50, "PD": -5, "TBP": 1, "LBP": 1, "BP": 2, "Pts": 4},
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


def test_2025_26_rulesets_have_independent_identifiers_and_currently_same_result():
    matches = [match(1, "Alpha", 2, "Bravo", 31, 27, 4, 4)]
    assert set(RULESETS) == {"prem_2025_26", "pwr_2025_26"}
    assert calculate_table(matches, "prem_2025_26") == calculate_table(matches, "pwr_2025_26")


def test_unknown_ruleset_is_rejected():
    with pytest.raises(ValueError, match="Unknown league-table ruleset"):
        calculate_table([], "unknown")


def test_table_csv_has_the_required_columns_and_rows():
    table = calculate_table(
        [match(1, "Alpha", 2, "Bravo", 20, 10, 4, 1)],
        "prem_2025_26",
    )
    rows = list(csv.DictReader(io.StringIO(table_to_csv(table))))
    assert list(rows[0]) == ["Pos", "Team", "P", "W", "D", "L", "PF", "PA", "PD", "TBP", "LBP", "BP", "Pts"]
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
