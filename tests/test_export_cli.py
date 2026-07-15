from __future__ import annotations

import csv

import pytest

from rugby_tracker.database import apply_migrations, connect
from rugby_tracker.export_cli import build_parser, main
from rugby_tracker.services import RugbyService


def test_parser_accepts_short_and_long_options(tmp_path):
    """Accept both concise and descriptive export arguments.

    :param tmp_path: Temporary directory used for output paths.
    :return: None.
    """
    # Parse both supported forms to keep the export CLI aligned with import.
    csv_file = tmp_path / "records.csv"
    short = build_parser().parse_args(("-t", "venues", "-o", str(csv_file)))
    long = build_parser().parse_args(
        ("--type", "matches", "--output", str(csv_file))
    )
    countries = build_parser().parse_args(
        ("--type", "countries", "--output", str(csv_file))
    )

    assert short.export_type == "venues"
    assert short.output_path == csv_file
    assert long.export_type == "matches"
    assert countries.export_type == "countries"


def test_cli_exports_records_to_the_requested_path(monkeypatch, tmp_path, capsys):
    """Export stored records to an import-compatible CSV file.

    :param monkeypatch: Pytest helper used to configure the application database.
    :param tmp_path: Temporary directory used for the database and output.
    :param capsys: Pytest helper used to capture command output.
    :return: None.
    """
    # Seed the configured database before invoking the command like an end user.
    database = tmp_path / "cli.db"
    output = tmp_path / "venues.csv"
    monkeypatch.setenv("RUGBY_TRACKER_DB", str(database))
    apply_migrations(database)
    connection = connect(database)
    service = RugbyService(connection)
    england = service.save_country(name="England")
    service.save_venue(name="The Rec", town_city="Bath", country_id=england)
    connection.commit()
    connection.close()

    result = main(("--type", "venues", "--output", str(output)))

    assert result == 0
    assert f"Exported Venues to {output}" in capsys.readouterr().out
    with output.open(newline="", encoding="utf-8") as export_file:
        assert list(csv.DictReader(export_file)) == [
            {"name": "The Rec", "town_city": "Bath", "country": "England"}
        ]


def test_cli_writes_headers_when_no_records_exist(monkeypatch, tmp_path):
    """Create a valid header-only export for an empty database table.

    :param monkeypatch: Pytest helper used to configure the application database.
    :param tmp_path: Temporary directory used for the database and output.
    :return: None.
    """
    # A new database should still produce a useful, import-compatible CSV file.
    monkeypatch.setenv("RUGBY_TRACKER_DB", str(tmp_path / "empty.db"))
    output = tmp_path / "referees.csv"

    assert main(("-t", "referees", "-o", str(output))) == 0
    assert output.read_text(encoding="utf-8") == "name\n"


def test_cli_returns_two_when_output_cannot_be_written(
    monkeypatch, tmp_path, capsys
):
    """Return a clear failure when the requested path is not writable as a file.

    :param monkeypatch: Pytest helper used to configure the application database.
    :param tmp_path: Temporary directory used for the database and invalid output.
    :param capsys: Pytest helper used to capture command output.
    :return: None.
    """
    # Passing a directory exercises a portable write failure without permissions tricks.
    monkeypatch.setenv("RUGBY_TRACKER_DB", str(tmp_path / "error.db"))

    assert main(("-t", "teams", "-o", str(tmp_path))) == 2
    assert "Unable to write" in capsys.readouterr().out


def test_parser_rejects_unknown_export_type(tmp_path):
    """Reject unsupported record types before accessing the database.

    :param tmp_path: Temporary directory used for the output path.
    :return: None.
    """
    # Argparse should provide its normal usage error for an unsupported choice.
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(
            ("-t", "players", "-o", str(tmp_path / "players.csv"))
        )

    assert error.value.code == 2
