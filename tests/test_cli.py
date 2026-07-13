"""Tests for the Rugby Tracker application launcher."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from rugby_tracker import cli


def test_launcher_uses_packaged_application(monkeypatch) -> None:
    """The launcher targets the application beside the installed CLI module.

    :param monkeypatch: Pytest helper used to isolate arguments and Streamlit execution.
    :return: None.
    """
    monkeypatch.setattr(sys, "argv", ["rugby-tracker", "--server.port=8501"])
    monkeypatch.setattr(cli.streamlit_cli, "main", lambda: 0)

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 0
    assert sys.argv == [
        "rugby-tracker",
        "run",
        str(Path(cli.__file__).with_name("app.py")),
        "--server.port=8501",
    ]
