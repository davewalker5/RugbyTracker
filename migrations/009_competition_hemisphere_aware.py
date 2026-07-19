"""Mark competitions that require hemisphere-aware standings."""

from yoyo import step


steps = [
    step(
        """
        ALTER TABLE competitions ADD COLUMN hemisphere_aware INTEGER NOT NULL DEFAULT 0
        CHECK (hemisphere_aware IN (0, 1))
        """,
        "ALTER TABLE competitions DROP COLUMN hemisphere_aware",
    ),
]
