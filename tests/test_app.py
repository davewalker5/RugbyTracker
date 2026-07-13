from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_app_starts_with_an_empty_database(monkeypatch, tmp_path):
    monkeypatch.setenv("RUGBY_TRACKER_DB", str(tmp_path / "app.db"))
    app = AppTest.from_file("streamlit_app.py", default_timeout=10).run()
    assert not app.exception
    assert app.title[0].value == "🏉 Rugby Tracker"
    assert "Add a competition" in app.info[0].value


def test_all_pages_render_against_empty_database(monkeypatch, tmp_path):
    monkeypatch.setenv("RUGBY_TRACKER_DB", str(tmp_path / "pages.db"))
    app = AppTest.from_file("streamlit_app.py", default_timeout=10).run()
    for page in ("Matches", "Competitions", "Teams", "Venues", "Referees"):
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception, page
