# Rugby Tracker

Rugby Tracker v0.2.0 is a local Streamlit application for recording rugby venues, teams, competitions, referees, fixtures, and results. It stores data in SQLite, presents competition fixtures and results grouped by round, and imports records from CSV files.

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

The initial schema is managed by yoyo in `migrations/`. League tables are intentionally reserved for a later version.

## CSV import

Open **CSV Import**, choose a record type, and download its template. CSV headings are case-insensitive and may use spaces, hyphens, or underscores. Match competitions are resolved using both name and season without regard to capitalisation; other match references and team home venues are resolved by name.

The importer validates every row, imports valid rows, refuses invalid rows, reports every validation failure, and skips practical duplicates. Import reference data in this order when starting with an empty database:

1. Import venues.
2. Import teams, competitions, and referees.
3. Import matches.

Imports can also be run from the command line:

```bash
venv/bin/rugby-import --type venues --input data/templates/venues.csv
venv/bin/rugby-import -t teams -i data/templates/teams.csv
```

Supported types are `venues`, `teams`, `competitions`, `referees`, and `matches`. The command uses `RUGBY_TRACKER_DB` when set, otherwise it imports into `data/rugbytracker.db`. It exits with status 1 when any rows are invalid and status 2 when the input file cannot be read.
