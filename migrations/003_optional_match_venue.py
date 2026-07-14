"""Allow fixtures to be recorded before their venue is announced."""

from yoyo import step


steps = [
    step(
        """
        CREATE TABLE matches_with_optional_venue (
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
    step("INSERT INTO matches_with_optional_venue SELECT * FROM matches"),
    step("DROP TABLE matches"),
    step("ALTER TABLE matches_with_optional_venue RENAME TO matches"),
    step("CREATE INDEX matches_competition_idx ON matches(competition_id)"),
    step("CREATE INDEX matches_date_idx ON matches(match_date)"),
]
