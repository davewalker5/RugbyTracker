"""Replace venue and team country text with country foreign keys."""

from yoyo import step


steps = [
    # Preserve every existing text value before rebuilding the related tables.
    step(
        """
        INSERT OR IGNORE INTO countries(name)
        SELECT DISTINCT trim(country) FROM venues
        WHERE country IS NOT NULL AND trim(country) <> ''
        """
    ),
    step(
        """
        INSERT OR IGNORE INTO countries(name)
        SELECT DISTINCT trim(country) FROM teams
        WHERE trim(country) <> ''
        """
    ),
    step(
        """
        CREATE TABLE venues_country_backup AS
        SELECT v.id, v.name, v.town_city, c.id AS country_id
        FROM venues v
        LEFT JOIN countries c ON c.name = trim(v.country) COLLATE NOCASE
        """
    ),
    step(
        """
        CREATE TABLE teams_country_backup AS
        SELECT t.id, t.name, c.id AS country_id, t.gender, t.home_venue_id
        FROM teams t
        JOIN countries c ON c.name = trim(t.country) COLLATE NOCASE
        """
    ),
    step("CREATE TABLE matches_country_backup AS SELECT * FROM matches"),
    step("DROP TABLE matches"),
    step("DROP TABLE teams"),
    step("DROP TABLE venues"),
    step(
        """
        CREATE TABLE venues (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL CHECK (trim(name) <> ''),
            town_city TEXT,
            country_id INTEGER REFERENCES countries(id) ON DELETE RESTRICT
        )
        """
    ),
    step("INSERT INTO venues SELECT * FROM venues_country_backup"),
    step(
        """
        CREATE TABLE teams (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL CHECK (trim(name) <> ''),
            country_id INTEGER NOT NULL REFERENCES countries(id) ON DELETE RESTRICT,
            gender TEXT NOT NULL CHECK (gender IN ('Men', 'Women')),
            home_venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE RESTRICT,
            UNIQUE (name COLLATE NOCASE, country_id)
        )
        """
    ),
    step("INSERT INTO teams SELECT * FROM teams_country_backup"),
    step(
        """
        CREATE TABLE matches (
            id INTEGER PRIMARY KEY,
            competition_id INTEGER NOT NULL REFERENCES competitions(id) ON DELETE RESTRICT,
            round TEXT,
            venue_id INTEGER REFERENCES venues(id) ON DELETE RESTRICT,
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
        """
    ),
    step("INSERT INTO matches SELECT * FROM matches_country_backup"),
    step("DROP TABLE matches_country_backup"),
    step("DROP TABLE teams_country_backup"),
    step("DROP TABLE venues_country_backup"),
    step("CREATE INDEX matches_competition_idx ON matches(competition_id)"),
    step("CREATE INDEX matches_date_idx ON matches(match_date)"),
]
