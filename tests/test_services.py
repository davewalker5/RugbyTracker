from __future__ import annotations

import pytest

from rugby_tracker.services import ValidationError


def test_crud_for_reference_entities(service, core_records):
    venue = service.repo.venues.get(core_records["venue"])
    assert venue == {
        "id": core_records["venue"], "name": "The Rec", "town_city": "Bath", "country": "England"
    }
    service.save_venue(core_records["venue"], name="Recreation Ground", town_city="Bath", country="England")
    assert service.repo.venues.get(core_records["venue"])["name"] == "Recreation Ground"

    service.save_referee(core_records["referee"], name="  Luke Pearce  ")
    assert service.repo.referees.get(core_records["referee"])["name"] == "Luke Pearce"


@pytest.mark.parametrize(
    "action, message",
    [
        (lambda service: service.save_venue(name="   "), "Venue name is required."),
        (lambda service: service.save_referee(name=None), "Referee name is required."),
        (lambda service: service.save_competition(name="League", season="", gender="Men"), "Season is required."),
        (lambda service: service.save_team(name="Club", gender="Mixed", home_venue_id=1), "Category must be"),
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
    result = service.competition_summary(core_records["competition"])["matches"][0]
    assert result["is_result"] is True
    assert result["winner"] == "Bath"
    assert result["loser"] == "Leicester Tigers"
    assert result["is_draw"] is False


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


def test_summary_groups_rounds_in_fixture_order_and_marks_draw(service, core_records):
    common = {
        "competition_id": core_records["competition"], "venue_id": core_records["venue"],
        "home_team_id": core_records["home"], "away_team_id": core_records["away"],
        "home_tries": 1, "away_tries": 1, "home_score": 10, "away_score": 10,
    }
    service.save_match(**common, round="Round 2", match_date="2025-09-27")
    service.save_match(**common, round="Round 1", match_date="2025-09-20")
    summary = service.competition_summary(core_records["competition"])
    assert [round_data["name"] for round_data in summary["rounds"]] == ["Round 1", "Round 2"]
    assert summary["matches"][0]["winner"] is None
    assert summary["matches"][0]["loser"] is None
    assert summary["matches"][0]["is_draw"] is True


def test_referenced_record_cannot_be_deleted(service, core_records):
    with pytest.raises(ValidationError, match="in use"):
        service.delete("venue", core_records["venue"])


def test_unreferenced_record_can_be_deleted(service):
    referee_id = service.save_referee(name="Temporary Official")
    service.delete("referee", referee_id)
    assert service.list_referees() == []
