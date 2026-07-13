"""Command-line interface for Rugby Tracker CSV imports."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from rugby_tracker.database import apply_migrations, connect
from rugby_tracker.imports import CsvImportService, ImportReport


IMPORT_TYPE_NAMES = {
    "venues": "Venues",
    "teams": "Teams",
    "competitions": "Competitions",
    "referees": "Referees",
    "matches": "Matches",
}


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the CSV import command.

    :return: Configured command-line argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="rugby-import",
        description="Import Rugby Tracker records from a CSV file.",
    )
    parser.add_argument(
        "-t",
        "--type",
        required=True,
        choices=tuple(IMPORT_TYPE_NAMES),
        dest="import_type",
        help="type of records to import",
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        type=Path,
        dest="input_path",
        metavar="PATH",
        help="path to the CSV file",
    )
    return parser


def print_report(report: ImportReport) -> None:
    """Print an import summary and any row-level validation failures.

    :param report: Completed CSV import report to display.
    :return: None.
    """
    print(f"Imported: {report.imported}")
    print(f"Duplicates skipped: {report.skipped}")
    print(f"Invalid rows: {report.invalid}")
    for issue in report.issues:
        print(f"Row {issue.row}: {'; '.join(issue.messages)}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run a CSV import using command-line arguments.

    :param argv: Optional arguments excluding the executable name; defaults to process arguments.
    :return: Zero on a valid import, one for row validation failures, or two for an unreadable input file.
    """
    arguments = build_parser().parse_args(argv)
    try:
        content = arguments.input_path.read_bytes()
    except OSError as error:
        print(f"Unable to read {arguments.input_path}: {error}")
        return 2

    apply_migrations()
    connection = connect()
    try:
        importer = CsvImportService(connection)
        report = importer.import_csv(IMPORT_TYPE_NAMES[arguments.import_type], content)
        connection.commit()
    finally:
        connection.close()
    print_report(report)
    return 1 if report.issues else 0
