"""Command-line launcher for the Streamlit application."""

from __future__ import annotations

import sys

from streamlit.web import cli as streamlit_cli

from .config import PROJECT_ROOT


def main() -> None:
    app = PROJECT_ROOT / "streamlit_app.py"
    sys.argv = [sys.argv[0], "run", str(app), *sys.argv[1:]]
    raise SystemExit(streamlit_cli.main())
