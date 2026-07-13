from __future__ import annotations

import sqlite3

import pytest

from rugby_tracker.database import apply_migrations, connect
from rugby_tracker.services import RugbyService


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "rugby.db"
    apply_migrations(path)
    return path


@pytest.fixture
def connection(database):
    connection = connect(database)
    yield connection
    connection.close()


@pytest.fixture
def service(connection: sqlite3.Connection):
    return RugbyService(connection)


@pytest.fixture
def core_records(service: RugbyService):
    venue = service.save_venue(name="The Rec", town_city="Bath", country="England")
    away_venue = service.save_venue(name="Welford Road", town_city="Leicester", country="England")
    home = service.save_team(name="Bath", gender="Men's", home_venue_id=venue)
    away = service.save_team(name="Leicester Tigers", gender="Men's", home_venue_id=away_venue)
    competition = service.save_competition(name="Premiership Rugby", season="2025/26", gender="Men's")
    referee = service.save_referee(name="Luke Pearce")
    return {
        "venue": venue,
        "away_venue": away_venue,
        "home": home,
        "away": away,
        "competition": competition,
        "referee": referee,
    }
