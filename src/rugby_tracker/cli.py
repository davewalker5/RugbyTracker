"""Command-line launcher for the Streamlit application."""

from __future__ import annotations

import sys
from pathlib import Path

from streamlit.web import cli as streamlit_cli


def main() -> None:
    """Launch the Rugby Tracker application through Streamlit.

    :return: None. The function exits with Streamlit's process status.
    """
    app = Path(__file__).with_name("app.py")
    sys.argv = [sys.argv[0], "run", str(app), *sys.argv[1:]]
    raise SystemExit(streamlit_cli.main())
