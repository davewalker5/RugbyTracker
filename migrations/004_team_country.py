"""Add mandatory country-based team identity and backfill existing teams."""

from yoyo import step


steps = [
    step(
        """
        CREATE TABLE teams_with_country (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL CHECK (trim(name) <> ''),
            country TEXT NOT NULL CHECK (trim(country) <> ''),
            gender TEXT NOT NULL CHECK (gender IN ('Men', 'Women')),
            home_venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE RESTRICT,
            UNIQUE (name COLLATE NOCASE, country COLLATE NOCASE)
        )
        """
    ),
    step(
        """
        INSERT INTO teams_with_country (id, name, country, gender, home_venue_id)
        SELECT t.id,
               t.name,
               CASE
                   WHEN EXISTS (
                       SELECT 1
                       FROM matches m
                       JOIN competitions c ON c.id = m.competition_id
                       WHERE (m.home_team_id = t.id OR m.away_team_id = t.id)
                         AND (c.name = 'PWR' COLLATE NOCASE OR c.ruleset = 'pwr_2025_26')
                   ) THEN 'England'
                   WHEN EXISTS (
                       SELECT 1
                       FROM matches m
                       JOIN competitions c ON c.id = m.competition_id
                       WHERE (m.home_team_id = t.id OR m.away_team_id = t.id)
                         AND (c.name = 'W6N' COLLATE NOCASE OR c.ruleset = 'w6n')
                   ) THEN CASE
                       WHEN rtrim(t.name) LIKE '% Women'
                       THEN rtrim(substr(rtrim(t.name), 1, length(rtrim(t.name)) - length('Women')))
                       ELSE trim(t.name)
                   END
                   ELSE trim(t.name)
               END,
               t.gender,
               t.home_venue_id
        FROM teams t
        """
    ),
    # Keep match data in a temporary table while the referenced team table is rebuilt.
    step("CREATE TABLE matches_team_country_backup AS SELECT * FROM matches"),
    step("DROP TABLE matches"),
    step("DROP TABLE teams"),
    step("ALTER TABLE teams_with_country RENAME TO teams"),
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
    step("INSERT INTO matches SELECT * FROM matches_team_country_backup"),
    step("DROP TABLE matches_team_country_backup"),
    step("CREATE INDEX matches_competition_idx ON matches(competition_id)"),
    step("CREATE INDEX matches_date_idx ON matches(match_date)"),
]
