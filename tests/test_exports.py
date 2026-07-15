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

    exported = {entity_type: exporter.export_csv(entity_type) for entity_type in EXPORT_TYPES}
    assert list(csv.DictReader(io.StringIO(exported["Venues"])))[0]["name"] == "The Rec"
    assert list(csv.DictReader(io.StringIO(exported["Teams"])))[0]["home_venue"] == "The Rec"
    assert list(csv.DictReader(io.StringIO(exported["Teams"])))[0]["country"] == "Bath"
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
