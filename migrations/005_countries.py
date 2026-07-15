"""Create the standalone countries reference table."""

from yoyo import step


steps = [
    step(
        """
        CREATE TABLE countries (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL CHECK (trim(name) <> ''),
            UNIQUE (name COLLATE NOCASE)
        )
        """,
        "DROP TABLE countries",
    ),
]
