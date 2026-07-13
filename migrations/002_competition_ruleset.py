"""Add selectable league-table rulesets to competitions."""

from yoyo import step


steps = [
    step(
        "ALTER TABLE competitions ADD COLUMN ruleset TEXT",
        "ALTER TABLE competitions DROP COLUMN ruleset",
    )
]
