"""Add an optional hemisphere classification to countries."""

from yoyo import step


steps = [
    step(
        """
        ALTER TABLE countries ADD COLUMN hemisphere TEXT
        CHECK (hemisphere IS NULL OR hemisphere IN ('Southern', 'Northern'))
        """,
        "ALTER TABLE countries DROP COLUMN hemisphere",
    ),
]
