from __future__ import annotations

import pytest

from rugby_tracker.database import apply_migrations, connect
from rugby_tracker.import_cli import build_parser, main


def test_parser_accepts_short_and_long_options(tmp_path):
    csv_file = tmp_path / "venues.csv"
    short = build_parser().parse_args(("-t", "venues", "-i", str(csv_file)))
    long = build_parser().parse_args(("--type", "teams", "--input", str(csv_file)))
    countries = build_parser().parse_args(("--type", "countries", "--input", str(csv_file)))
    assert short.import_type == "venues"
    assert short.input_path == csv_file
    assert long.import_type == "teams"
    assert countries.import_type == "countries"


def test_cli_imports_valid_csv(monkeypatch, tmp_path, capsys):
    database = tmp_path / "cli.db"
    csv_file = tmp_path / "venues.csv"
    csv_file.write_text("name,town_city,country\nThe Rec,Bath,England\n", encoding="utf-8")
    monkeypatch.setenv("RUGBY_TRACKER_DB", str(database))
    apply_migrations(database)
    connection = connect(database)
    connection.execute("INSERT INTO countries(name) VALUES ('England')")
    connection.commit()
    connection.close()

    result = main(("-t", "venues", "-i", str(csv_file)))

    assert result == 0
    assert "Imported: 1" in capsys.readouterr().out
    connection = connect(database)
    assert connection.execute("SELECT name FROM venues").fetchone()["name"] == "The Rec"
    connection.close()


def test_cli_commits_valid_rows_and_returns_one_for_invalid_rows(monkeypatch, tmp_path, capsys):
    database = tmp_path / "mixed.db"
    csv_file = tmp_path / "competitions.csv"
    csv_file.write_text(
        "name,season,gender\nSix Nations,2026,Men\n,2026,Unknown\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RUGBY_TRACKER_DB", str(database))

    result = main(("--type", "competitions", "--input", str(csv_file)))

    output = capsys.readouterr().out
    assert result == 1
    assert "Imported: 1" in output
    assert "Invalid rows: 1" in output
    assert "Row 3:" in output
    connection = connect(database)
    assert connection.execute("SELECT count(*) FROM competitions").fetchone()[0] == 1
    connection.close()


def test_cli_returns_two_for_unreadable_input(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("RUGBY_TRACKER_DB", str(tmp_path / "unused.db"))
    result = main(("-t", "venues", "-i", str(tmp_path / "missing.csv")))
    assert result == 2
    assert "Unable to read" in capsys.readouterr().out


def test_parser_rejects_unknown_import_type(tmp_path):
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(("-t", "players", "-i", str(tmp_path / "players.csv")))
    assert error.value.code == 2
