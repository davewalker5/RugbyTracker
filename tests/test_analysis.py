"""Tests for Team Summary calculations and PDF export."""

from __future__ import annotations

from rugby_tracker.analysis import render_team_summary_pdf, team_summary_filename
from rugby_tracker.services import RugbyService


def test_team_summary_calculates_team_perspective_and_pdf(connection) -> None:
    """Calculate all core totals and render a standalone PDF.

    :param connection: Empty migrated test database connection.
    :return: None.
    """
    # Create one home win and one away loss to exercise both perspectives.
    service = RugbyService(connection)
    country = service.save_country(name="England")
    venue = service.save_venue(name="Twickenham", country_id=country)
    team = service.save_team(name="London", country_id=country, gender="Women", home_venue_id=venue)
    opponent = service.save_team(name="York", country_id=country, gender="Women", home_venue_id=venue)
    competition = service.save_competition(name="Test League", season="2025/26", gender="Women", ruleset="w6n")
    service.save_match(competition_id=competition, venue_id=venue, match_date="2025-09-01", home_team_id=team, away_team_id=opponent, home_score=30, away_score=10, home_tries=4, away_tries=1)
    service.save_match(competition_id=competition, venue_id=venue, match_date="2025-09-08", home_team_id=opponent, away_team_id=team, home_score=21, away_score=17, home_tries=3, away_tries=2)

    report = service.team_summary(competition, team)

    assert (report.played, report.won, report.drawn, report.lost) == (2, 1, 0, 1)
    assert (report.points_for, report.points_against) == (47, 31)
    assert (report.tries_for, report.tries_against) == (6, 4)
    assert report.home_record["points_difference"] == 20
    assert report.away_record["points_difference"] == -4
    assert report.largest_victory and report.largest_victory.opponent == "York"
    assert report.largest_defeat and report.largest_defeat.location == "Away"
    assert team_summary_filename(report) == "team-summary_london_test-league_2025-26.pdf"
    assert render_team_summary_pdf(report).startswith(b"%PDF")


def test_team_summary_rejects_non_participating_team(connection) -> None:
    """Do not generate a report for a team outside the selected season.

    :param connection: Empty migrated test database connection.
    :return: None.
    """
    # A valid but unrelated team must not bypass selector scoping in the service.
    service = RugbyService(connection)
    country = service.save_country(name="Wales")
    venue = service.save_venue(name="Ground", country_id=country)
    team = service.save_team(name="Cardiff", country_id=country, gender="Men", home_venue_id=venue)
    competition = service.save_competition(name="League", season="2026", gender="Men", ruleset="m6n")

    try:
        service.team_summary(competition, team)
    except ValueError as error:
        assert "participating" in str(error)
    else:
        raise AssertionError("Expected an unrelated team to be rejected.")
