from __future__ import annotations

import pytest

from rugby_tracker.services import ValidationError


def test_crud_for_reference_entities(service, core_records):
    venue = service.list_venues()[0]
    assert venue == {
        "id": core_records["venue"], "name": "The Rec", "town_city": "Bath",
        "country_id": core_records["england"], "country": "England",
    }
    service.save_venue(
        core_records["venue"], name="Recreation Ground", town_city="Bath",
        country_id=core_records["england"],
    )
    assert service.repo.venues.get(core_records["venue"])["name"] == "Recreation Ground"

    service.save_referee(core_records["referee"], name="  Luke Pearce  ")
    assert service.repo.referees.get(core_records["referee"])["name"] == "Luke Pearce"


@pytest.mark.parametrize(
    "action, message",
    [
        (lambda service: service.save_venue(name="   "), "Venue name is required."),
        (lambda service: service.save_referee(name=None), "Referee name is required."),
        (lambda service: service.save_competition(name="League", season="", gender="Men"), "Season is required."),
        (
            lambda service: service.save_team(
                name="Club", country_id=1, gender="Mixed", home_venue_id=1
            ),
            "Category must be",
        ),
        (
            lambda service: service.save_team(
                name="Club", country_id="", gender="Men", home_venue_id=1
            ),
            "Country is required.",
        ),
    ],
)
def test_mandatory_fields_have_clear_errors(service, action, message):
    with pytest.raises(ValidationError, match=message):
        action(service)


def test_match_can_be_a_fixture_then_updated_to_a_result(service, core_records):
    match_id = service.save_match(
        competition_id=core_records["competition"], round="Round 1", venue_id=core_records["venue"],
        referee_id=None, match_date="2025-09-20", kickoff_time="15:05",
        home_team_id=core_records["home"], away_team_id=core_records["away"],
        home_tries="", away_tries="", home_score="", away_score="",
    )
    fixture = service.list_matches()[0]
    assert fixture["id"] == match_id
    assert fixture["home_score"] is None

    service.save_match(
        entity_id=match_id, competition_id=core_records["competition"], round="Round 1",
        venue_id=core_records["venue"], referee_id=core_records["referee"],
        match_date="2025-09-20", kickoff_time="15:05", home_team_id=core_records["home"],
        away_team_id=core_records["away"], home_tries=4, away_tries=2, home_score=31, away_score=17,
    )
    result = service.list_matches(core_records["competition"])[0]
    assert result["home_score"] == 31
    assert result["away_score"] == 17


def test_team_identity_is_name_plus_country(service, core_records):
    """Allow a shared name across countries but reject a duplicate identity.

    :param service: Rugby service backed by the test database.
    :param core_records: Identifiers for existing reference records.
    :return: None.
    """
    service.save_team(
        name="United", country_id=core_records["england"], gender="Women",
        home_venue_id=core_records["venue"],
    )
    scotland = service.save_country(name="Scotland")
    service.save_team(
        name="United", country_id=scotland, gender="Men",
        home_venue_id=core_records["venue"],
    )

    with pytest.raises(ValidationError, match="name and country already exists"):
        service.save_team(
            name="united", country_id=core_records["england"], gender="Men",
            home_venue_id=core_records["venue"],
        )


def test_match_validation_reports_incomplete_scores_and_same_team(service, core_records):
    base = {
        "competition_id": core_records["competition"], "venue_id": core_records["venue"],
        "match_date": "2025-09-20", "home_team_id": core_records["home"],
        "away_team_id": core_records["away"],
    }
    with pytest.raises(ValidationError, match="all try and score values"):
        service.save_match(**base, home_tries=1, away_tries=0, home_score=5)
    with pytest.raises(ValidationError, match="must be different"):
        service.save_match(**{**base, "away_team_id": core_records["home"]})
    with pytest.raises(ValidationError, match="zero or more"):
        service.save_match(**base, home_tries=-1, away_tries=0, home_score=0, away_score=0)


def test_referenced_record_cannot_be_deleted(service, core_records):
    with pytest.raises(ValidationError, match="in use"):
        service.delete("venue", core_records["venue"])
    with pytest.raises(ValidationError, match="in use"):
        service.delete("country", core_records["england"])


def test_unreferenced_record_can_be_deleted(service):
    referee_id = service.save_referee(name="Temporary Official")
    service.delete("referee", referee_id)
    assert service.list_referees() == []

    country_id = service.save_country(name="Temporary Country")
    service.delete("country", country_id)
    assert service.list_countries() == []


def test_duplicate_country_name_is_rejected(service):
    """Reject case-insensitive duplicate country names with a clear error.

    :param service: Rugby service backed by the test database.
    :return: None.
    """
    service.save_country(name="England")
    with pytest.raises(ValidationError, match="already exists"):
        service.save_country(name="ENGLAND")


@pytest.mark.parametrize("round_name", ("1", "Quarter-Final", "Semi-Final", "Final"))
def test_match_round_supports_numbers_and_knockout_names(service, core_records, round_name):
    service.save_match(
        competition_id=core_records["competition"],
        round=round_name,
        venue_id=core_records["venue"],
        match_date="2026-05-01",
        home_team_id=core_records["home"],
        away_team_id=core_records["away"],
    )
    match = service.list_matches(core_records["competition"])[0]
    assert match["round"] == round_name
