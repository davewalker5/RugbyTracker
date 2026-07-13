# Rugby Tracker

Rugby Tracker v0.1.0 is a local Streamlit application for recording rugby venues, teams, competitions, referees, fixtures, and results. It stores data in SQLite and presents competition fixtures and results grouped by round.

## Run locally

Python 3.13 or later is required.

```bash
./scripts/make-venv.sh
venv/bin/rugby-tracker
```

The database is created empty at `data/rugbytracker.db` on first run. Set `RUGBY_TRACKER_DB` to use another full database path.

## Tests

```bash
./scripts/run-tests.sh
```

The initial schema is managed by yoyo in `migrations/`. CSV imports and league tables are intentionally reserved for later versions.
