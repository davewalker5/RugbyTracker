from __future__ import annotations

import csv
import io

from rugby_tracker.exports import EXPORT_TYPES, CsvExportService


def test_csv_exports_use_import_schemas_and_related_names(
    service, core_records, connection
):
    """Export every record type using round-trip-compatible CSV columns.

    :param service: Rugby service backed by the test database.
    :param core_records: Identifiers for existing reference records.
    :param connection: Open test database connection.
    :return: None.
    """
    # Add a completed match so the most detailed export exercises every relation.
    service.save_match(
        competition_id=core_records["competition"],
        round="Round 1",
        venue_id=core_records["venue"],
        referee_id=core_records["referee"],
        match_date="2025-09-20",
        kickoff_time="15:00",
        home_team_id=core_records["home"],
        away_team_id=core_records["away"],
        home_tries=4,
        away_tries=2,
        home_score=31,
        away_score=17,
    )
    exporter = CsvExportService(connection)

    # Core fixtures already create the country records required by their references.

    exported = {entity_type: exporter.export_csv(entity_type) for entity_type in EXPORT_TYPES}
    assert list(csv.DictReader(io.StringIO(exported["Countries"])))[0].keys() == {
        "name", "hemisphere"
    }
    assert {row["name"] for row in csv.DictReader(io.StringIO(exported["Countries"]))} == {
        "Bath", "England", "Leicester Tigers",
    }
    assert list(csv.DictReader(io.StringIO(exported["Venues"])))[0]["name"] == "The Rec"
    assert list(csv.DictReader(io.StringIO(exported["Teams"])))[0]["home_venue"] == "The Rec"
    assert list(csv.DictReader(io.StringIO(exported["Teams"])))[0]["country"] == "Bath"
    rulesets = list(csv.DictReader(io.StringIO(exported["Rulesets"])))
    assert len(rulesets) == 7
    prem = next(row for row in rulesets if row["identifier"] == "prem_2025_26")
    assert prem["tie_breakers"] == (
        '["competition_points","wins","points_difference","points_for",'
        '"head_to_head_points"]'
    )
    assert list(csv.DictReader(io.StringIO(exported["Competitions"])))[0]["name"] == "Premiership Rugby"
    assert list(csv.DictReader(io.StringIO(exported["Referees"])))[0]["name"] == "Luke Pearce"
    match_row = list(csv.DictReader(io.StringIO(exported["Matches"])))[0]
    assert match_row["competition"] == "Premiership Rugby"
    assert match_row["venue"] == "The Rec"
    assert match_row["home_team"] == "Bath"
    assert match_row["home_country"] == "Bath"
    assert match_row["away_country"] == "Leicester Tigers"
    assert match_row["home_score"] == "31"


def test_empty_csv_export_still_contains_the_import_header(connection):
    """Export an empty entity table with its complete schema.

    :param connection: Empty migrated test database connection.
    :return: None.
    """
    # Header-only exports remain valid files and useful import templates.
    exporter = CsvExportService(connection)

    assert exporter.export_csv("Venues") == "name,town_city,country\r\n"


def test_competition_filter_exports_only_related_records(
    service, core_records, connection
):
    """Limit every export type to one competition and its dependencies.

    :param service: Rugby service backed by the test database.
    :param core_records: Identifiers for existing reference records.
    :param connection: Open test database connection.
    :return: None.
    """
    neutral_venue = service.save_venue(
        name="Neutral Ground", town_city="London", country_id=core_records["england"]
    )
    france = service.save_country(name="France")
    unrelated_venue = service.save_venue(
        name="Unrelated Ground", town_city="Paris", country_id=france
    )
    unrelated_team = service.save_team(
        name="Unrelated", country_id=france, gender="Men",
        home_venue_id=unrelated_venue,
    )
    unrelated_competition = service.save_competition(
        name="Other League", season="2025/26", gender="Men"
    )
    unrelated_referee = service.save_referee(name="Unrelated Referee")
    service.save_match(
        competition_id=core_records["competition"],
        venue_id=neutral_venue,
        referee_id=core_records["referee"],
        match_date="2025-09-20",
        home_team_id=core_records["home"],
        away_team_id=core_records["away"],
    )
    service.save_match(
        competition_id=unrelated_competition,
        venue_id=unrelated_venue,
        referee_id=unrelated_referee,
        match_date="2025-09-21",
        home_team_id=unrelated_team,
        away_team_id=core_records["home"],
    )
    exporter = CsvExportService(connection)

    def rows(entity_type: str) -> list[dict[str, str]]:
        """Parse one competition-filtered export.

        :param entity_type: Supported export record type.
        :return: Parsed CSV rows.
        """
        return list(csv.DictReader(io.StringIO(
            exporter.export_csv(entity_type, core_records["competition"])
        )))

    assert {row["name"] for row in rows("Competitions")} == {"Premiership Rugby"}
    assert {row["name"] for row in rows("Countries")} == {
        "Bath", "England", "Leicester Tigers",
    }
    assert {row["name"] for row in rows("Teams")} == {"Bath", "Leicester Tigers"}
    assert {row["name"] for row in rows("Referees")} == {"Luke Pearce"}
    assert {row["name"] for row in rows("Venues")} == {
        "Neutral Ground", "The Rec", "Welford Road",
    }
    assert {row["competition"] for row in rows("Matches")} == {"Premiership Rugby"}


def test_competition_filter_exports_only_its_referenced_ruleset(
    service, core_records, connection
):
    """Include the selected competition's ruleset as an export dependency.

    :param service: Rugby service backed by the test database.
    :param core_records: Identifiers for existing reference records.
    :param connection: Open test database connection.
    :return: None.
    """
    service.save_competition(
        entity_id=core_records["competition"],
        name="Premiership Rugby",
        season="2025/26",
        gender="Men",
        ruleset="prem_2025_26",
    )

    rows = list(csv.DictReader(io.StringIO(
        CsvExportService(connection).export_csv(
            "Rulesets", core_records["competition"]
        )
    )))

    assert [row["identifier"] for row in rows] == ["prem_2025_26"]
