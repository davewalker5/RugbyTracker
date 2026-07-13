"""Command-line launcher for the Streamlit application."""

from __future__ import annotations

import sys

from streamlit.web import cli as streamlit_cli

from .config import PROJECT_ROOT


def main() -> None:
    """Launch the Rugby Tracker application through Streamlit.

    :return: None. The function exits with Streamlit's process status.
    """
    app = PROJECT_ROOT / "streamlit_app.py"
    sys.argv = [sys.argv[0], "run", str(app), *sys.argv[1:]]
    raise SystemExit(streamlit_cli.main())
