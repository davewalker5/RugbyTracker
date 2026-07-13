from __future__ import annotations

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from rugby_tracker.app import DRAW_BACKGROUND, LOSS_BACKGROUND, WIN_BACKGROUND, _style_match_results
from rugby_tracker.database import apply_migrations, connect
from rugby_tracker.services import RugbyService


APP_PATH = Path(__file__).resolve().parents[1] / "src" / "streamlit_app.py"


def test_match_result_styles_colour_team_cells() -> None:
    """Completed results receive winner, loser, or draw backgrounds.

    :return: None.
    """
    table = pd.DataFrame([
        {"Home": "Home winner", "Away": "Away loser"},
        {"Home": "Home loser", "Away": "Away winner"},
        {"Home": "Drawn home", "Away": "Drawn away"},
        {"Home": "Future home", "Away": "Future away"},
    ])
    matches = [
        {"home_score": 24, "away_score": 17},
        {"home_score": 10, "away_score": 15},
        {"home_score": 20, "away_score": 20},
        {"home_score": None, "away_score": None},
    ]

    context = _style_match_results(table, matches)._compute().ctx

    assert context[(0, 0)] == [("background-color", WIN_BACKGROUND)]
    assert context[(0, 1)] == [("background-color", LOSS_BACKGROUND)]
    assert context[(1, 0)] == [("background-color", LOSS_BACKGROUND)]
    assert context[(1, 1)] == [("background-color", WIN_BACKGROUND)]
    assert context[(2, 0)] == [("background-color", DRAW_BACKGROUND)]
    assert context[(2, 1)] == [("background-color", DRAW_BACKGROUND)]
    assert (3, 0) not in context
    assert (3, 1) not in context


def test_app_starts_with_an_empty_database(monkeypatch, tmp_path):
    monkeypatch.setenv("RUGBY_TRACKER_DB", str(tmp_path / "app.db"))
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    assert not app.exception
    assert app.title[0].value == "🏉 Rugby Tracker"
    assert "Add a competition" in app.info[0].value


def test_all_pages_render_against_empty_database(monkeypatch, tmp_path):
    monkeypatch.setenv("RUGBY_TRACKER_DB", str(tmp_path / "pages.db"))
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    for page in ("League Table", "Matches", "CSV Import", "Competitions", "Teams", "Venues", "Referees"):
        app.radio[0].set_value(page).run()
        assert not app.exception, page


def test_league_table_page_renders_calculated_standings(monkeypatch, tmp_path):
    database = tmp_path / "table.db"
    monkeypatch.setenv("RUGBY_TRACKER_DB", str(database))
    apply_migrations(database)
    connection = connect(database)
    service = RugbyService(connection)
    venue = service.save_venue(name="The Rec")
    home = service.save_team(name="Bath", gender="Men", home_venue_id=venue)
    away = service.save_team(name="Leicester Tigers", gender="Men", home_venue_id=venue)
    competition = service.save_competition(
        name="PREM", season="2025/26", gender="Men", ruleset="prem_2025_26"
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
    connection.commit()
    connection.close()

    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    app.radio[0].set_value("League Table").run()

    assert not app.exception
    assert app.dataframe[0].value["Team"].tolist() == ["Bath", "Leicester Tigers"]
