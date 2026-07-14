"""Command-line interface for Rugby Tracker CSV exports."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from rugby_tracker.database import apply_migrations, connect
from rugby_tracker.exports import EXPORT_TYPES, CsvExportService


EXPORT_TYPE_NAMES = {entity_type.casefold(): entity_type for entity_type in EXPORT_TYPES}


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the CSV export command.

    :return: Configured command-line argument parser.
    """
    # Match the import command's option names while using output for the target file.
    parser = argparse.ArgumentParser(
        prog="rugby-export",
        description="Export Rugby Tracker records to a CSV file.",
    )
    parser.add_argument(
        "-t",
        "--type",
        required=True,
        choices=tuple(EXPORT_TYPE_NAMES),
        dest="export_type",
        help="type of records to export",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        type=Path,
        dest="output_path",
        metavar="PATH",
        help="path of the CSV file to write",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run a CSV export using command-line arguments.

    :param argv: Optional arguments excluding the executable name; defaults to process arguments.
    :return: Zero after a successful export, or two when the output cannot be written.
    """
    # Ensure the database is current before reading any records for export.
    arguments = build_parser().parse_args(argv)
    apply_migrations()
    connection = connect()
    try:
        exporter = CsvExportService(connection)
        entity_type = EXPORT_TYPE_NAMES[arguments.export_type]
        content = exporter.export_csv(entity_type)
    finally:
        connection.close()

    # Write only after the database connection closes and report filesystem failures cleanly.
    try:
        arguments.output_path.write_text(content, encoding="utf-8", newline="")
    except OSError as error:
        print(f"Unable to write {arguments.output_path}: {error}")
        return 2
    print(f"Exported {entity_type} to {arguments.output_path}")
    return 0
