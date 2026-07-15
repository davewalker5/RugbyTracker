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

    countries = importer.import_csv(
        "Countries", "name\nEngland\nENGLAND\nScotland\n"
    )
    assert (countries.imported, countries.skipped, countries.invalid) == (1, 2, 0)
    assert {row["name"] for row in service.list_countries()} >= {"England", "Scotland"}

    teams = importer.import_csv(
        "Teams",
        "name,country,gender,home venue\nGloucester Rugby,England,MEN,the rec\nGloucester Rugby,England,Men,The Rec\n",
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
        "Teams", "name,country,gender,home_venue\nGloucester Rugby,England,Men,The Rec\n"
    )
    assert (repeated.imported, repeated.skipped, repeated.invalid) == (0, 1, 0)
    assert len(service.list_teams()) == 3


def test_venue_import_supports_optional_fields_and_skips_duplicates(connection):
    importer = CsvImportService(connection)
    importer.import_csv("Countries", "name\nEngland\nChanged\n")
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


def test_every_import_type_ignores_existing_entities_and_leaves_them_intact(
    service, core_records, connection
):
    service.save_match(
        competition_id=core_records["competition"],
        venue_id=core_records["venue"],
        referee_id=core_records["referee"],
        match_date="2025-09-20",
        kickoff_time="15:00",
        round="Round 1",
        home_team_id=core_records["home"],
        away_team_id=core_records["away"],
        home_tries=4,
        away_tries=2,
        home_score=31,
        away_score=17,
    )
    importer = CsvImportService(connection)

    reports = [
        importer.import_csv(
            "Venues", "name,town_city,country\nthe rec,Changed Town,Changed Country\n"
        ),
        importer.import_csv(
            "Teams", "name,country,gender,home_venue\nBATH,Bath,men,Unknown Ground\n"
        ),
        importer.import_csv(
            "Competitions",
            "name,season,gender,ruleset\nPREMIERSHIP RUGBY,2025/26,MEN,not-a-ruleset\n",
        ),
        importer.import_csv("Referees", "name\nluke pearce\n"),
        importer.import_csv(
            "Matches",
            """competition,season,venue,referee,date,home_team,home_country,away_team,away_country,home_tries,away_tries,home_score,away_score
Premiership Rugby,2025/26,,Unknown Referee,2025-09-20,Bath,Bath,Leicester Tigers,Leicester Tigers,-1,,,999
""",
        ),
    ]

    assert all((report.imported, report.skipped, report.invalid) == (0, 1, 0) for report in reports)
    assert service.list_venues()[0] == {
        "id": core_records["venue"],
        "name": "The Rec",
        "town_city": "Bath",
        "country_id": core_records["england"],
        "country": "England",
    }
    assert service.list_teams()[0]["home_venue_id"] == core_records["venue"]
    competition = service.repo.competitions.get(core_records["competition"])
    assert competition is not None and competition["ruleset"] is None
    assert service.list_referees()[0]["name"] == "Luke Pearce"
    existing_match = service.list_matches(core_records["competition"])[0]
    assert existing_match["round"] == "Round 1"
    assert existing_match["venue_id"] == core_records["venue"]
    assert existing_match["referee_id"] == core_records["referee"]
    assert existing_match["home_score"] == 31
    assert existing_match["away_score"] == 17


def test_match_import_resolves_names_and_supports_fixtures_and_results(service, core_records, connection):
    importer = CsvImportService(connection)
    content = """competition,season,round,venue,referee,date,kick-off time,home team,home country,away team,away country,home tries,away tries,home score,away score
premiership rugby,2025/26,Semi-Final,THE REC,luke pearce,2025-09-20,15:00,bath,Bath,LEICESTER TIGERS,Leicester Tigers,4,2,31,17
Premiership Rugby,2025/26,Final,Welford Road,,2025-09-27,,Leicester Tigers,Leicester Tigers,Bath,Bath,,,,
"""
    report = importer.import_csv("Matches", content)
    connection.commit()
    assert (report.total_rows, report.imported, report.skipped, report.invalid) == (2, 2, 0, 0)
    matches = service.list_matches(core_records["competition"])
    assert matches[0]["referee_name"] == "Luke Pearce"
    assert matches[0]["round"] == "Semi-Final"
    assert matches[0]["home_score"] == 31
    assert matches[1]["referee_id"] is None
    assert matches[1]["round"] == "Final"
    assert matches[1]["home_score"] is None

    repeated = importer.import_csv("Matches", content)
    assert (repeated.imported, repeated.skipped) == (0, 2)


def test_match_import_uses_country_to_disambiguate_team_names(
    service, core_records, connection
):
    """Resolve teams sharing a name through their mandatory countries.

    :param service: Rugby service backed by the test database.
    :param core_records: Identifiers for existing reference records.
    :param connection: Open test database connection.
    :return: None.
    """
    england = service.save_team(
        name="United", country_id=service.save_country(name="United England"), gender="Men",
        home_venue_id=core_records["venue"],
    )
    scotland = service.save_team(
        name="United", country_id=service.save_country(name="United Scotland"), gender="Men",
        home_venue_id=core_records["away_venue"],
    )
    importer = CsvImportService(connection)
    report = importer.import_csv(
        "Matches",
        """competition,season,venue,date,home_team,home_country,away_team,away_country
Premiership Rugby,2025/26,The Rec,2026-01-01,United,United England,United,United Scotland
""",
    )

    match_row = service.list_matches(core_records["competition"])[0]
    assert (report.imported, report.invalid) == (1, 0)
    assert match_row["home_team_id"] == england
    assert match_row["away_team_id"] == scotland


def test_match_import_allows_a_venue_to_be_announced_later(
    service, core_records, connection
):
    """Import an international fixture whose venue is still unknown.

    :param service: Rugby service backed by the test database.
    :param core_records: Identifiers for existing reference records.
    :param connection: Open test database connection.
    :return: None.
    """
    # A blank venue should persist as NULL and remain editable through the service.
    importer = CsvImportService(connection)
    report = importer.import_csv(
        "Matches",
        """competition,season,venue,date,home_team,home_country,away_team,away_country
Premiership Rugby,2025/26,,2026-10-01,Bath,Bath,Leicester Tigers,Leicester Tigers
""",
    )

    assert (report.imported, report.invalid) == (1, 0)
    match_row = service.list_matches(core_records["competition"])[0]
    assert match_row["venue_id"] is None
    assert match_row["venue_name"] is None


def test_m6n_2026_import_bundle_produces_the_official_final_table(connection):
    importer = CsvImportService(connection)
    root = Path("data/imports/M6N-2026")
    imports = (
        ("Countries", "countries.csv", 6),
        ("Venues", "venues.csv", 7),
        ("Teams", "teams.csv", 6),
        ("Competitions", "competitions.csv", 1),
        ("Referees", "referees.csv", 12),
        ("Matches", "matches.csv", 15),
    )

    for entity_type, filename, expected in imports:
        report = importer.import_csv(entity_type, (root / filename).read_bytes())
        assert (report.imported, report.skipped, report.invalid) == (expected, 0, 0)

    competition = importer.rugby.list_competitions()[0]
    result = importer.rugby.league_table(competition["id"])
    summary = [
        (row["Team"], row["PF"], row["PA"], row["Pts"])
        for row in result["table"]
    ]

    assert result["complete"] is True
    assert summary == [
        ("France", 211, 130, 21),
        ("Ireland", 146, 108, 18),
        ("Scotland", 143, 144, 16),
        ("Italy", 79, 117, 9),
        ("England", 153, 151, 8),
        ("Wales", 90, 172, 6),
    ]


def test_wxv_2026_import_bundles_are_complete_and_repeatable(connection):
    """Import both WXV bundles and verify their selectable competition data.

    :param connection: Empty migrated test database connection.
    :return: None.
    """
    # Import shared reference data additively, just as sequential CLI imports do.
    importer = CsvImportService(connection)
    bundles = (
        (Path("data/imports/WXV-GLOBAL-2026"), 12, 27, "wxv_global_2026"),
        (Path("data/imports/WXV-CHALLENGER-2026"), 6, 9, "wxv_challenger_2026"),
    )
    for root, team_count, match_count, ruleset in bundles:
        for entity_type, filename in (
            ("Countries", "countries.csv"),
            ("Venues", "venues.csv"),
            ("Teams", "teams.csv"),
            ("Competitions", "competitions.csv"),
            ("Referees", "referees.csv"),
            ("Matches", "matches.csv"),
        ):
            report = importer.import_csv(entity_type, (root / filename).read_bytes())
            assert report.invalid == 0, report.error_rows()

        competition = next(
            row for row in importer.rugby.list_competitions()
            if row["ruleset"] == ruleset
        )
        matches = importer.rugby.list_matches(competition["id"])
        assert len(matches) == match_count
        assert len({match["home_team_id"] for match in matches} |
                   {match["away_team_id"] for match in matches}) == team_count
        assert importer.rugby.league_table(competition["id"])["validation_errors"] == []

    # Re-importing every file must leave the stored competition data unchanged.
    for root, _, _, _ in bundles:
        for entity_type, filename in (
            ("Countries", "countries.csv"),
            ("Venues", "venues.csv"),
            ("Teams", "teams.csv"),
            ("Competitions", "competitions.csv"),
            ("Referees", "referees.csv"),
            ("Matches", "matches.csv"),
        ):
            report = importer.import_csv(entity_type, (root / filename).read_bytes())
            assert report.imported == 0
            assert report.invalid == 0


def test_nations_2026_import_bundle_provides_both_series(connection):
    """Import the Nations Championship reference data and both fixture series.

    :param connection: Empty migrated test database connection.
    :return: None.
    """
    importer = CsvImportService(connection)
    root = Path("data/imports/NATIONS-2026")

    # Import in dependency order so names in later files resolve to stored rows.
    for entity_type, filename in (
        ("Countries", "countries.csv"),
        ("Venues", "venues.csv"),
        ("Teams", "teams.csv"),
        ("Competitions", "competitions.csv"),
        ("Referees", "referees.csv"),
        ("Matches", "matches.csv"),
    ):
        report = importer.import_csv(entity_type, (root / filename).read_bytes())
        assert report.invalid == 0, report.error_rows()

    competitions = {
        row["name"]: row for row in importer.rugby.list_competitions()
    }
    assert set(competitions) == {
        "Nations Championship Southern Series",
        "Nations Championship Northern Series",
    }
    for competition in competitions.values():
        matches = importer.rugby.list_matches(competition["id"])
        result = importer.rugby.league_table(competition["id"])

        assert competition["ruleset"] == "nations_2026"
        assert len(matches) == 18
        assert result["validation_errors"] == []


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

    content = """competition,season,venue,date,home_team,home_country,away_team,away_country
PREMIERSHIP RUGBY,2026/27,The Rec,2026-09-20,Bath,Bath,Leicester Tigers,Leicester Tigers
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


def test_competition_import_accepts_ruleset_identifier_or_label(connection):
    importer = CsvImportService(connection)
    report = importer.import_csv(
        "Competitions",
        """name,season,gender,ruleset
PREM,2025/26,Men,prem_2025_26
PWR,2025/26,Women,Premiership Women's Rugby (2025/26)
Unknown,2025/26,Men,not_a_ruleset
""",
    )
    assert (report.imported, report.invalid) == (2, 1)
    competitions = importer.rugby.list_competitions()
    assert {row["ruleset"] for row in competitions} == {"prem_2025_26", "pwr_2025_26"}
    assert "valid league-table ruleset" in report.issues[0].messages[0]


def test_match_import_reports_every_missing_reference_and_bad_result(connection):
    importer = CsvImportService(connection)
    content = """competition,season,venue,date,home_team,home_country,away_team,away_country,home_tries,away_tries,home_score,away_score,referee
Unknown League,2025/26,Unknown Ground,not-a-date,Home RFC,Home Country,Away RFC,Away Country,-1,nope,10,,Unknown Ref
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
    missing = importer.import_csv("Teams", "name,country,gender\nBath,Bath,Men\n")
    assert missing.total_rows == 0
    assert "home_venue" in missing.issues[0].messages[0]

    missing_season = importer.import_csv(
        "Matches", "competition,venue,date,home_team,home_country,away_team,away_country\nLeague,Ground,2026-01-01,A,A,B,B\n"
    )
    assert missing_season.total_rows == 0
    assert "season" in missing_season.issues[0].messages[0]

    encoding = importer.import_csv("Referees", b"name\n\xff")
    assert encoding.total_rows == 0
    assert "UTF-8" in encoding.issues[0].messages[0]


def test_ambiguous_case_insensitive_reference_is_refused(service, connection):
    service.save_country(name="Bath")
    service.save_venue(name="The Rec")
    service.save_venue(name="the rec")
    importer = CsvImportService(connection)
    report = importer.import_csv(
        "Teams", "name,country,gender,home_venue\nBath,Bath,Men,THE REC\n"
    )
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
