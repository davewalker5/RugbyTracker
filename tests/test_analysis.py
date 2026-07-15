"""Tests for supporter-focused summary calculations and PDF export."""

from __future__ import annotations

from rugby_tracker.analysis import (
    competition_round_summary,
    competition_summary_filename,
    competition_team_rankings,
    head_to_head_filename,
    head_to_head_host_record,
    render_competition_summary_pdf,
    render_head_to_head_pdf,
    render_team_summary_pdf,
    team_summary_filename,
)
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


def test_competition_summary_calculates_rankings_rounds_and_pdf(connection) -> None:
    """Calculate competition totals, rankings, rounds, and a standalone PDF."""
    service = RugbyService(connection)
    country = service.save_country(name="England")
    venue = service.save_venue(name="National Ground", country_id=country)
    alpha = service.save_team(name="Alpha", country_id=country, gender="Women", home_venue_id=venue)
    beta = service.save_team(name="Beta", country_id=country, gender="Women", home_venue_id=venue)
    competition = service.save_competition(
        name="Test Cup", season="2026", gender="Women", ruleset="w6n"
    )
    service.save_match(
        competition_id=competition, round="1", venue_id=venue,
        match_date="2026-03-01", home_team_id=alpha, away_team_id=beta,
        home_score=30, away_score=10, home_tries=4, away_tries=1,
    )
    service.save_match(
        competition_id=competition, round="2", venue_id=venue,
        match_date="2026-03-08", home_team_id=beta, away_team_id=alpha,
        home_score=20, away_score=20, home_tries=2, away_tries=2,
    )
    service.save_match(
        competition_id=competition, round="3", venue_id=venue,
        match_date="2026-03-15", home_team_id=alpha, away_team_id=beta,
    )

    report = service.competition_summary(competition)

    assert (report.team_count, report.completed_matches, report.scheduled_matches) == (2, 2, 3)
    assert (report.total_points, report.total_tries) == (80, 9)
    assert (report.home_wins, report.away_wins, report.draws) == (1, 0, 1)
    assert report.average_points == 40
    assert report.highest_scoring and report.highest_scoring.score == "30–10"
    assert report.largest_margin and report.largest_margin.winning_margin == 20
    assert competition_team_rankings(report)[0] == {
        "Category": "Most competition points", "Leader": "Alpha", "Value": 7,
    }
    assert [row["Round"] for row in competition_round_summary(report)] == ["1", "2"]
    assert competition_summary_filename(report) == "competition-summary_test-cup_2026.pdf"
    assert render_competition_summary_pdf(report).startswith(b"%PDF")


def test_competition_summary_requires_matches_and_ruleset(connection) -> None:
    """Reject seasons that cannot yet produce a meaningful summary."""
    service = RugbyService(connection)
    competition = service.save_competition(
        name="Empty League", season="2026", gender="Men", ruleset="m6n"
    )

    try:
        service.competition_summary(competition)
    except ValueError as error:
        assert "matches" in str(error)
    else:
        raise AssertionError("Expected a competition without fixtures to be rejected.")


def test_head_to_head_combines_seasons_and_exports_pdf(connection) -> None:
    """Calculate historical records, home splits, highlights, and PDF output."""
    service = RugbyService(connection)
    country = service.save_country(name="France")
    venue = service.save_venue(name="National Stadium", country_id=country)
    alpha = service.save_team(name="Alpha", country_id=country, gender="Women", home_venue_id=venue)
    beta = service.save_team(name="Beta", country_id=country, gender="Women", home_venue_id=venue)
    first = service.save_competition(name="Test Series", season="2025", gender="Women", ruleset="w6n")
    second = service.save_competition(name="Test Series", season="2026", gender="Women", ruleset="w6n")
    service.save_match(
        competition_id=first, round="1", venue_id=venue, match_date="2025-03-01",
        home_team_id=alpha, away_team_id=beta, home_score=24, away_score=20,
        home_tries=3, away_tries=2,
    )
    service.save_match(
        competition_id=second, round="1", venue_id=venue, match_date="2026-03-01",
        home_team_id=beta, away_team_id=alpha, home_score=30, away_score=10,
        home_tries=4, away_tries=1,
    )
    service.save_match(
        competition_id=second, round="Final", venue_id=venue, match_date="2026-03-08",
        home_team_id=alpha, away_team_id=beta, home_score=18, away_score=18,
        home_tries=2, away_tries=2,
    )

    report = service.head_to_head([first, second], alpha, beta)

    assert report.season == "All Seasons"
    assert (report.meetings, report.team_a_wins, report.team_b_wins, report.draws) == (3, 1, 1, 1)
    assert (report.team_a_points, report.team_b_points) == (52, 68)
    assert (report.team_a_tries, report.team_b_tries) == (6, 8)
    assert report.largest_team_a_victory and report.largest_team_a_victory.margin == 4
    assert report.largest_team_b_victory and report.largest_team_b_victory.margin == -20
    assert len(report.closest_matches) == 2
    assert report.current_streak == "The teams drew their latest meeting."
    assert head_to_head_host_record(report, "Alpha")["W"] == 1
    assert head_to_head_filename(report) == "head-to-head_alpha_beta_test-series_all-seasons.pdf"
    assert render_head_to_head_pdf(report).startswith(b"%PDF")


def test_head_to_head_requires_different_teams_with_completed_meetings(connection) -> None:
    """Reject invalid selections and pairs without a completed result."""
    service = RugbyService(connection)
    country = service.save_country(name="Ireland")
    venue = service.save_venue(name="Ground", country_id=country)
    alpha = service.save_team(name="Alpha", country_id=country, gender="Men", home_venue_id=venue)
    beta = service.save_team(name="Beta", country_id=country, gender="Men", home_venue_id=venue)
    competition = service.save_competition(name="Series", season="2026", gender="Men", ruleset="m6n")
    service.save_match(
        competition_id=competition, venue_id=venue, match_date="2026-01-01",
        home_team_id=alpha, away_team_id=beta,
    )

    for team_a, team_b, message in ((alpha, alpha, "different"), (alpha, beta, "completed")):
        try:
            service.head_to_head([competition], team_a, team_b)
        except ValueError as error:
            assert message in str(error)
        else:
            raise AssertionError("Expected invalid Head-to-Head selections to be rejected.")
