"""Store versioned competition ruleset configuration in the database."""

from yoyo import step


steps = [
    step(
        """
        CREATE TABLE competition_rulesets (
            identifier TEXT PRIMARY KEY CHECK (trim(identifier) <> ''),
            label TEXT NOT NULL CHECK (trim(label) <> ''),
            team_count INTEGER CHECK (team_count IS NULL OR team_count > 1),
            matches_per_team INTEGER CHECK (
                matches_per_team IS NULL OR matches_per_team > 0
            ),
            single_round_robin INTEGER NOT NULL DEFAULT 0 CHECK (single_round_robin IN (0, 1)),
            home_and_away INTEGER NOT NULL DEFAULT 0 CHECK (home_and_away IN (0, 1)),
            knockout_stage INTEGER NOT NULL DEFAULT 0 CHECK (knockout_stage IN (0, 1)),
            playoff_teams INTEGER NOT NULL DEFAULT 0 CHECK (playoff_teams >= 0),
            win_points INTEGER NOT NULL CHECK (win_points >= 0),
            draw_points INTEGER NOT NULL CHECK (draw_points >= 0),
            loss_points INTEGER NOT NULL CHECK (loss_points >= 0),
            try_bonus_threshold INTEGER NOT NULL CHECK (try_bonus_threshold >= 0),
            try_bonus_points INTEGER NOT NULL CHECK (try_bonus_points >= 0),
            losing_bonus_margin INTEGER NOT NULL CHECK (losing_bonus_margin >= 0),
            losing_bonus_points INTEGER NOT NULL CHECK (losing_bonus_points >= 0),
            grand_slam_bonus_points INTEGER NOT NULL DEFAULT 0 CHECK (
                grand_slam_bonus_points >= 0
            ),
            tie_breakers TEXT NOT NULL CHECK (json_valid(tie_breakers)),
            excluded_rounds TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(excluded_rounds)),
            share_equal_positions INTEGER NOT NULL DEFAULT 0 CHECK (
                share_equal_positions IN (0, 1)
            ),
            champion INTEGER NOT NULL DEFAULT 0 CHECK (champion IN (0, 1)),
            grand_slam INTEGER NOT NULL DEFAULT 0 CHECK (grand_slam IN (0, 1)),
            triple_crown INTEGER NOT NULL DEFAULT 0 CHECK (triple_crown IN (0, 1)),
            wooden_spoon INTEGER NOT NULL DEFAULT 0 CHECK (wooden_spoon IN (0, 1)),
            triple_crown_teams TEXT NOT NULL DEFAULT '[]' CHECK (
                json_valid(triple_crown_teams)
            ),
            special_handler TEXT
        )
        """,
        "DROP TABLE competition_rulesets",
    ),
    step(
        """
        INSERT INTO competition_rulesets (
            identifier, label, team_count, matches_per_team, single_round_robin,
            home_and_away, knockout_stage, playoff_teams, win_points, draw_points,
            loss_points, try_bonus_threshold, try_bonus_points, losing_bonus_margin,
            losing_bonus_points, grand_slam_bonus_points, tie_breakers,
            excluded_rounds, share_equal_positions, champion, grand_slam,
            triple_crown, wooden_spoon, triple_crown_teams
        ) VALUES
        ('prem_2025_26', 'Premiership Rugby (2025/26)', 10, 18, 0, 1, 1, 4,
         4, 2, 0, 4, 1, 7, 1, 0,
         '["competition_points","wins","points_difference","points_for","head_to_head_points"]',
         '["quarter-final","semi-final","final"]', 1, 0, 0, 0, 0, '[]'),
        ('pwr_2025_26', 'Premiership Women''s Rugby (2025/26)', NULL, NULL, 0, 0, 0, 0,
         4, 2, 0, 4, 1, 7, 1, 0,
         '["competition_points","points_difference"]',
         '["quarter-final","semi-final","final"]', 0, 0, 0, 0, 0, '[]'),
        ('m6n', 'Men''s Six Nations', 6, 5, 1, 0, 0, 0,
         4, 2, 0, 4, 1, 7, 1, 3,
         '["competition_points","points_difference","tries_for"]', '[]', 1,
         1, 1, 1, 1, '["England","Ireland","Scotland","Wales"]'),
        ('w6n', 'Women''s Six Nations', 6, 5, 1, 0, 0, 0,
         4, 2, 0, 4, 1, 7, 1, 3,
         '["competition_points","points_difference","tries_for"]', '[]', 1,
         1, 1, 1, 1, '["England","Ireland","Scotland","Wales"]'),
        ('wxv_global_2026', 'WXV Global Series (2026)', 12, NULL, 0, 0, 0, 0,
         4, 2, 0, 4, 1, 7, 1, 0,
         '["competition_points","points_difference","tries_for"]', '[]', 0,
         1, 0, 0, 0, '[]'),
        ('wxv_challenger_2026', 'WXV Global Series Challenger (2026)', 6, 3, 0, 0, 0, 0,
         4, 2, 0, 4, 1, 7, 1, 0,
         '["competition_points","points_difference","tries_for"]', '[]', 0,
         1, 0, 0, 0, '[]'),
        ('nations_2026', 'Nations Championship Series (2026)', 12, 3, 0, 0, 0, 0,
         4, 2, 0, 4, 1, 7, 1, 0,
         '["competition_points","wins","points_difference","tries_for"]', '[]', 0,
         1, 0, 0, 0, '[]')
        """,
        "DELETE FROM competition_rulesets",
    ),
]
