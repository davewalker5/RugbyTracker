from __future__ import annotations

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from rugby_tracker.app import (
    DRAW_BACKGROUND,
    LOSS_BACKGROUND,
    WIN_BACKGROUND,
    _export_validation_error,
    _filter_by_gender,
    _style_match_results,
)
from rugby_tracker.database import apply_migrations, connect
from rugby_tracker.services import RugbyService


APP_PATH = Path(__file__).resolve().parents[1] / "src" / "streamlit_app.py"


def test_match_result_styles_colour_team_cells() -> None:
    """Completed results receive winner, loser, or draw backgrounds.

    :return: None.
    """
    table = pd.DataFrame([
        {"Home": "Home winner", "Home Country": "A", "Away": "Away loser", "Away Country": "B"},
        {"Home": "Home loser", "Home Country": "A", "Away": "Away winner", "Away Country": "B"},
        {"Home": "Drawn home", "Home Country": "A", "Away": "Drawn away", "Away Country": "B"},
        {"Home": "Future home", "Home Country": "A", "Away": "Future away", "Away Country": "B"},
    ])
    matches = [
        {"home_score": 24, "away_score": 17},
        {"home_score": 10, "away_score": 15},
        {"home_score": 20, "away_score": 20},
        {"home_score": None, "away_score": None},
    ]

    context = _style_match_results(table, matches)._compute().ctx

    assert context[(0, 0)] == [("background-color", WIN_BACKGROUND)]
    assert context[(0, 1)] == [("background-color", WIN_BACKGROUND)]
    assert context[(0, 2)] == [("background-color", LOSS_BACKGROUND)]
    assert context[(0, 3)] == [("background-color", LOSS_BACKGROUND)]
    assert context[(1, 0)] == [("background-color", LOSS_BACKGROUND)]
    assert context[(1, 1)] == [("background-color", LOSS_BACKGROUND)]
    assert context[(1, 2)] == [("background-color", WIN_BACKGROUND)]
    assert context[(1, 3)] == [("background-color", WIN_BACKGROUND)]
    assert context[(2, 0)] == [("background-color", DRAW_BACKGROUND)]
    assert context[(2, 1)] == [("background-color", DRAW_BACKGROUND)]
    assert context[(2, 2)] == [("background-color", DRAW_BACKGROUND)]
    assert context[(2, 3)] == [("background-color", DRAW_BACKGROUND)]
    assert (3, 0) not in context
    assert (3, 1) not in context


def test_gender_filter_defaults_to_all_and_selects_one_category() -> None:
    """Filter teams or competitions using the shared category choices.

    :return: None.
    """
    records = [
        {"name": "Men's team", "gender": "Men"},
        {"name": "Women's team", "gender": "Women"},
    ]

    assert _filter_by_gender(records, "Men and Women") == records
    assert [row["name"] for row in _filter_by_gender(records, "Men")] == ["Men's team"]
    assert [row["name"] for row in _filter_by_gender(records, "Women")] == ["Women's team"]


def test_app_starts_with_an_empty_database(monkeypatch, tmp_path):
    monkeypatch.setenv("RUGBY_TRACKER_DB", str(tmp_path / "app.db"))
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    assert not app.exception
    assert app.title[0].value == "🏉 Rugby Tracker"
    assert [tab.label for tab in app.tabs] == [
        "Competition Summary", "Head-to-Head", "Team Summary"
    ]
    assert "Add a competition" in app.info[0].value


def test_all_pages_render_against_empty_database(monkeypatch, tmp_path):
    monkeypatch.setenv("RUGBY_TRACKER_DB", str(tmp_path / "pages.db"))
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    assert "Competition Summary" not in app.radio[0].options
    for page in (
        "League Table", "Matches", "CSV Import", "CSV Export",
        "Competitions", "Teams", "Venues", "Referees", "Countries",
    ):
        app.radio[0].set_value(page).run()
        assert not app.exception, page


def test_csv_export_defaults_and_resets_file_stem(monkeypatch, tmp_path):
    """Changing export type always restores its conventional filename stem.

    :param monkeypatch: Pytest helper used to configure the application database.
    :param tmp_path: Temporary directory in which to create the test database.
    :return: None.
    """
    # Select, edit, and change type to prove user changes never leak across types.
    monkeypatch.setenv("RUGBY_TRACKER_DB", str(tmp_path / "exports.db"))
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    app.radio[0].set_value("CSV Export").run()

    assert app.selectbox[0].value is None
    assert app.selectbox[1].value == "All"
    assert app.text_input[0].value == ""
    assert app.button[0].label == "Download"
    app.button[0].click().run()
    assert app.warning[0].value == (
        "Specify an export type and a file stem before downloading."
    )
    app.selectbox[0].set_value("Competitions").run()
    assert app.text_input[0].value == "competitions"
    app.text_input[0].set_value("custom_name").run()
    assert app.text_input[0].value == "custom_name"
    app.selectbox[0].set_value("Matches").run()
    assert app.text_input[0].value == "matches"


def test_csv_export_requires_type_and_file_stem():
    """Reject download attempts missing either required export field.

    :return: None.
    """
    # Validate each missing-field combination and the successful case.
    assert _export_validation_error(None, "") == (
        "Specify an export type and a file stem before downloading."
    )
    assert _export_validation_error("Teams", "") == (
        "Specify a file stem before downloading."
    )
    assert _export_validation_error(None, "teams") == (
        "Specify an export type before downloading."
    )
    assert _export_validation_error("Teams", "teams") is None


def test_results_render_in_league_table_and_matches_page(monkeypatch, tmp_path):
    """Results appear correctly in both standings and match table displays.

    :param monkeypatch: Pytest helper used to configure the application database.
    :param tmp_path: Temporary directory in which to create the test database.
    :return: None.
    """
    database = tmp_path / "table.db"
    monkeypatch.setenv("RUGBY_TRACKER_DB", str(database))
    apply_migrations(database)
    connection = connect(database)
    service = RugbyService(connection)
    bath_country = service.save_country(name="Bath")
    leicester_country = service.save_country(name="Leicester Tigers")
    england = service.save_country(name="England")
    venue = service.save_venue(name="The Rec", country_id=england)
    home = service.save_team(
        name="Bath", country_id=bath_country, gender="Men", home_venue_id=venue
    )
    away = service.save_team(
        name="Leicester Tigers", country_id=leicester_country, gender="Men",
        home_venue_id=venue,
    )
    service.save_team(
        name="Bath Women", country_id=england, gender="Women", home_venue_id=venue
    )
    competition = service.save_competition(
        name="PREM", season="2025/26", gender="Men", ruleset="prem_2025_26"
    )
    later_competition = service.save_competition(
        name="PREM", season="2026/27", gender="Men", ruleset="prem_2025_26"
    )
    service.save_competition(
        name="W6N", season="2026", gender="Women", ruleset="w6n"
    )
    service.save_match(
        competition_id=competition,
        venue_id=venue,
        match_date="2025-09-20",
        home_team_id=home,
        away_team_id=away,
        home_tries=4,
        away_tries=2,
        home_score=31,
        away_score=17,
    )
    service.save_match(
        competition_id=later_competition,
        venue_id=venue,
        match_date="2026-09-20",
        home_team_id=away,
        away_team_id=home,
        home_tries=3,
        away_tries=1,
        home_score=22,
        away_score=12,
    )
    connection.commit()
    connection.close()

    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    app.radio[0].set_value("League Table").run()

    assert not app.exception
    assert app.selectbox[0].value is None
    app.selectbox[0].set_value(competition).run()
    assert app.dataframe[0].value["Team"].tolist() == ["Bath", "Leicester Tigers"]

    app.radio[0].set_value("Matches").run()

    assert not app.exception
    assert app.selectbox[0].value is None
    app.selectbox[0].set_value(competition).run()
    assert app.dataframe[0].value.columns.tolist() == [
        "Date", "Competition", "Round", "Venue", "Home", "Home Country",
        "Away", "Away Country", "Score", "Tries",
    ]
    assert app.dataframe[0].value["Home"].tolist() == ["Bath"]
    assert app.dataframe[0].value["Home Country"].tolist() == ["Bath"]
    assert app.dataframe[0].value["Away"].tolist() == ["Leicester Tigers"]
    assert app.dataframe[0].value["Away Country"].tolist() == ["Leicester Tigers"]
    assert app.dataframe[0].value["Venue"].tolist() == ["The Rec"]
    assert app.dataframe[0].value["Score"].tolist() == ["31–17"]
    assert app.dataframe[0].value["Tries"].tolist() == ["4–2"]
    assert all(selector.value is None for selector in app.selectbox[1:])

    app.session_state[f"matches_table_{competition}"] = {"selection": {"rows": [0]}}
    app.run()

    assert [selector.value for selector in app.selectbox] == [
        competition, competition, venue, None, home, away,
    ]
    assert [field.value for field in app.text_input] == ["", "", "4", "31", "2", "17"]
    assert [button.label for button in app.button] == ["Save", "Delete", "Clear"]

    app.button[2].click().run()

    assert [selector.value for selector in app.selectbox] == [
        competition, None, None, None, None, None,
    ]
    assert all(field.value == "" for field in app.text_input)

    app.selectbox[0].set_value(later_competition).run()

    assert not app.exception
    assert app.dataframe[0].value["Competition"].tolist() == ["PREM 2026/27"]
    assert app.dataframe[0].value["Score"].tolist() == ["22–12"]
    assert app.dataframe[0].value["Tries"].tolist() == ["3–1"]

    for page in ("Teams", "Competitions"):
        app.radio[0].set_value(page).run()
        assert not app.exception, page
        assert app.selectbox, page
        assert app.selectbox[0].value == "Men and Women", page
        assert all(selector.value is None for selector in app.selectbox[1:]), page
        assert set(app.dataframe[0].value["Category"]) == {"Men", "Women"}
        app.selectbox[0].set_value("Women").run()
        assert set(app.dataframe[0].value["Category"]) == {"Women"}
        app.selectbox[0].set_value("Men and Women").run()
        if page == "Teams":
            # Selecting a team populates both editable identity fields.
            app.session_state["team_table"] = {"selection": {"rows": [0]}}
            app.run()
            assert app.text_input[0].value == "Bath"
            assert app.selectbox[1].value == bath_country

    app.radio[0].set_value("CSV Import").run()
    assert not app.exception
    assert app.selectbox
    assert all(selector.value is None for selector in app.selectbox)

    app.radio[0].set_value("CSV Export").run()
    assert not app.exception
    assert app.selectbox[0].value is None
    assert app.selectbox[1].value == "All"

    app.radio[0].set_value("Competitions").run()
    app.session_state["competition_table"] = {"selection": {"rows": [0]}}
    app.run()

    assert [field.value for field in app.text_input] == ["PREM", "2025/26"]
    assert [selector.value for selector in app.selectbox] == [
        "Men and Women", "Men", "prem_2025_26"
    ]

    app.radio[0].set_value("Venues").run()
    assert not app.exception
    assert len(app.selectbox) == 1
    assert app.selectbox[0].label == "Country"

    app.radio[0].set_value("Referees").run()
    assert not app.exception
    assert not app.selectbox

    app.radio[0].set_value("Countries").run()
    assert not app.exception
    assert not app.selectbox
    assert set(app.dataframe[0].value["Name"]) == {
        "Bath", "England", "Leicester Tigers",
    }
