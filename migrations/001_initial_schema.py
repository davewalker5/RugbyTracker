"""Create the v0.1.0 core match database."""

from yoyo import step


steps = [
    step(
        """
        CREATE TABLE venues (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL CHECK (trim(name) <> ''),
            town_city TEXT,
            country TEXT
        )
        """,
        "DROP TABLE venues",
    ),
    step(
        """
        CREATE TABLE teams (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL CHECK (trim(name) <> ''),
            gender TEXT NOT NULL CHECK (gender IN ('Men''s', 'Women''s')),
            home_venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE RESTRICT
        )
        """,
        "DROP TABLE teams",
    ),
    step(
        """
        CREATE TABLE competitions (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL CHECK (trim(name) <> ''),
            season TEXT NOT NULL CHECK (trim(season) <> ''),
            gender TEXT NOT NULL CHECK (gender IN ('Men''s', 'Women''s'))
        )
        """,
        "DROP TABLE competitions",
    ),
    step(
        """
        CREATE TABLE referees (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL CHECK (trim(name) <> '')
        )
        """,
        "DROP TABLE referees",
    ),
    step(
        """
        CREATE TABLE matches (
            id INTEGER PRIMARY KEY,
            competition_id INTEGER NOT NULL REFERENCES competitions(id) ON DELETE RESTRICT,
            round TEXT,
            venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE RESTRICT,
            referee_id INTEGER REFERENCES referees(id) ON DELETE RESTRICT,
            match_date TEXT NOT NULL CHECK (trim(match_date) <> ''),
            kickoff_time TEXT,
            home_team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE RESTRICT,
            away_team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE RESTRICT,
            home_tries INTEGER CHECK (home_tries >= 0),
            away_tries INTEGER CHECK (away_tries >= 0),
            home_score INTEGER CHECK (home_score >= 0),
            away_score INTEGER CHECK (away_score >= 0),
            CHECK (home_team_id <> away_team_id),
            CHECK (
                (home_tries IS NULL AND away_tries IS NULL AND home_score IS NULL AND away_score IS NULL)
                OR
                (home_tries IS NOT NULL AND away_tries IS NOT NULL AND home_score IS NOT NULL AND away_score IS NOT NULL)
            )
        )
        """,
        "DROP TABLE matches",
    ),
    step("CREATE INDEX matches_competition_idx ON matches(competition_id)", "DROP INDEX matches_competition_idx"),
    step("CREATE INDEX matches_date_idx ON matches(match_date)", "DROP INDEX matches_date_idx"),
]
