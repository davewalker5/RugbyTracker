from __future__ import annotations

import ast
from pathlib import Path

from rugby_tracker.imports import IMPORT_TYPES, CsvImportService


def test_templates_have_supported_headers(connection):
    importer = CsvImportService(connection)
    for entity_type in IMPORT_TYPES:
        template = importer.template(entity_type)
        assert template.strip()
        assert "name" in template or "competition" in template


def test_reference_imports_are_case_insensitive_and_repeatable(service, core_records, connection):
    importer = CsvImportService(connection)

    teams = importer.import_csv(
        "Teams",
        "name,gender,home venue\nGloucester Rugby,MEN,the rec\nGloucester Rugby,Men,The Rec\n",
    )
    assert (teams.imported, teams.skipped, teams.invalid) == (1, 1, 0)

    competitions = importer.import_csv(
        "Competitions",
        "name,season,category\nSix Nations,2026,Men\nSix Nations,2026,men\n",
    )
    assert (competitions.imported, competitions.skipped, competitions.invalid) == (1, 1, 0)

    referees = importer.import_csv("Referees", b"\xef\xbb\xbfname\nSara Cox\nsara cox\n")
    assert (referees.imported, referees.skipped, referees.invalid) == (1, 1, 0)

    repeated = importer.import_csv(
        "Teams", "name,gender,home_venue\nGloucester Rugby,Men,The Rec\n"
    )
    assert (repeated.imported, repeated.skipped, repeated.invalid) == (0, 1, 0)
    assert len(service.list_teams()) == 3


def test_venue_import_supports_optional_fields_and_skips_duplicates(connection):
    importer = CsvImportService(connection)
    report = importer.import_csv(
        "Venues",
        "name,town city,country\nThe Rec,Bath,England\nTwickenham Stadium,,England\nthe rec,Changed,Changed\n",
    )
    assert (report.imported, report.skipped, report.invalid) == (2, 1, 0)
    venues = importer.rugby.list_venues()
    assert venues[0]["town_city"] == "Bath"
    assert venues[1]["town_city"] is None

    repeated = importer.import_csv("Venues", "name\nTWICKENHAM STADIUM\n")
    assert (repeated.imported, repeated.skipped) == (0, 1)


def test_match_import_resolves_names_and_supports_fixtures_and_results(service, core_records, connection):
    importer = CsvImportService(connection)
    content = """competition,season,round,venue,referee,date,kick-off time,home team,away team,home tries,away tries,home score,away score
premiership rugby,2025/26,Round 1,THE REC,luke pearce,2025-09-20,15:00,bath,LEICESTER TIGERS,4,2,31,17
Premiership Rugby,2025/26,Round 2,Welford Road,,2025-09-27,,Leicester Tigers,Bath,,,,
"""
    report = importer.import_csv("Matches", content)
    connection.commit()
    assert (report.total_rows, report.imported, report.skipped, report.invalid) == (2, 2, 0, 0)
    matches = service.list_matches(core_records["competition"])
    assert matches[0]["referee_name"] == "Luke Pearce"
    assert matches[0]["home_score"] == 31
    assert matches[1]["referee_id"] is None
    assert matches[1]["home_score"] is None

    repeated = importer.import_csv("Matches", content)
    assert (repeated.imported, repeated.skipped) == (0, 2)


def test_same_competition_name_across_seasons_is_allowed_and_matches_correctly(
    service, core_records, connection
):
    importer = CsvImportService(connection)
    competition_report = importer.import_csv(
        "Competitions",
        "name,season,gender\nPREMIERSHIP RUGBY,2026/27,Men\n",
    )
    assert (competition_report.imported, competition_report.skipped) == (1, 0)
    later_competition = next(
        competition["id"]
        for competition in service.list_competitions()
        if competition["season"] == "2026/27"
    )
    assert later_competition != core_records["competition"]

    content = """competition,season,venue,date,home_team,away_team
PREMIERSHIP RUGBY,2026/27,The Rec,2026-09-20,Bath,Leicester Tigers
"""
    report = importer.import_csv("Matches", content)

    assert (report.imported, report.invalid) == (1, 0)
    assert service.list_matches(core_records["competition"]) == []
    assert len(service.list_matches(later_competition)) == 1


def test_import_reports_all_bad_rows_while_importing_valid_rows(connection):
    importer = CsvImportService(connection)
    content = """name,season,gender
,2026,Mixed
Six Nations,2026,Women
,2027,Unknown
"""
    report = importer.import_csv("Competitions", content)
    assert (report.total_rows, report.imported, report.invalid) == (3, 1, 2)
    assert len(report.issues[0].messages) == 2
    assert len(report.issues[1].messages) == 2
    assert len(importer.rugby.list_competitions()) == 1


def test_match_import_reports_every_missing_reference_and_bad_result(connection):
    importer = CsvImportService(connection)
    content = """competition,season,venue,date,home_team,away_team,home_tries,away_tries,home_score,away_score,referee
Unknown League,2025/26,Unknown Ground,not-a-date,Home RFC,Away RFC,-1,nope,10,,Unknown Ref
"""
    report = importer.import_csv("Matches", content)
    messages = report.issues[0].messages
    assert report.invalid == 1
    assert any("Competition" in message and "not found" in message for message in messages)
    assert any("Venue" in message and "not found" in message for message in messages)
    assert any("Home team" in message and "not found" in message for message in messages)
    assert any("Away team" in message and "not found" in message for message in messages)
    assert any("Referee" in message and "not found" in message for message in messages)
    assert any("valid date" in message for message in messages)
    assert any("all try and score values" in message for message in messages)
    assert any("Home tries" in message and "zero or more" in message for message in messages)
    assert any("Away tries" in message and "zero or more" in message for message in messages)


def test_document_errors_prevent_import(connection):
    importer = CsvImportService(connection)
    missing = importer.import_csv("Teams", "name,gender\nBath,Men\n")
    assert missing.total_rows == 0
    assert "home_venue" in missing.issues[0].messages[0]

    missing_season = importer.import_csv(
        "Matches", "competition,venue,date,home_team,away_team\nLeague,Ground,2026-01-01,A,B\n"
    )
    assert missing_season.total_rows == 0
    assert "season" in missing_season.issues[0].messages[0]

    encoding = importer.import_csv("Referees", b"name\n\xff")
    assert encoding.total_rows == 0
    assert "UTF-8" in encoding.issues[0].messages[0]


def test_ambiguous_case_insensitive_reference_is_refused(service, connection):
    service.save_venue(name="The Rec")
    service.save_venue(name="the rec")
    importer = CsvImportService(connection)
    report = importer.import_csv("Teams", "name,gender,home_venue\nBath,Men,THE REC\n")
    assert report.imported == 0
    assert "matches more than one" in report.issues[0].messages[0]


def test_source_functions_have_parameter_and_return_docstrings():
    issues = []
    for filename in Path("src").rglob("*.py"):
        tree = ast.parse(filename.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            docstring = ast.get_docstring(node) or ""
            parameters = [
                argument.arg
                for argument in (*node.args.args, *node.args.kwonlyargs)
                if argument.arg not in {"self", "cls"}
            ]
            if node.args.vararg:
                parameters.append(node.args.vararg.arg)
            if node.args.kwarg:
                parameters.append(node.args.kwarg.arg)
            missing = [name for name in parameters if f":param {name}:" not in docstring]
            if not docstring or missing or ":return:" not in docstring:
                issues.append((str(filename), node.lineno, node.name, missing))
    assert issues == []
