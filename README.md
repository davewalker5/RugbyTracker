[![GitHub issues](https://img.shields.io/github/issues/davewalker5/RugbyTracker)](https://github.com/davewalker5/RugbyTracker/issues)
[![Releases](https://img.shields.io/github/v/release/davewalker5/RugbyTracker.svg?include_prereleases)](https://github.com/davewalker5/RugbyTracker/releases)
[![License](https://img.shields.io/badge/License-mit-blue.svg)](https://github.com/davewalker5/RugbyTracker/blob/main/LICENSE)
[![Language](https://img.shields.io/badge/language-python-blue.svg)](https://www.python.org)
[![GitHub code size in bytes](https://img.shields.io/github/languages/code-size/davewalker5/RugbyTracker)](https://github.com/davewalker5/RugbyTracker/)

# Rugby Tracker

## Overview

The Rugby Tracker is a lightweight desktop application for recording rugby fixtures, results and competition standings.

The primary goal is to provide a simple, self-contained database for tracking competitions such as Premiership Rugby, Premiership Women's Rugby (PWR), the Six Nations and other domestic or international tournaments.

Rather than acting as a live scoring system, the application is intended to support manual entry and historical record keeping, with automatic calculation of league tables from recorded match results.

Built using Python, Streamlit and SQLite, the application follows the same design philosophy as the other Field Notes projects: a simple, well-structured desktop application with an understandable relational data model, incremental development and clear, maintainable code.

## Current Features

### Competition Database

Maintain reference data for:

- Countries through CSV import, export, and a maintenance tab
- Venues
- Teams
- Competitions
- Referees

### Match Recording

Record match details including:

- Competition
- Round
- Venue
- Referee
- Date and kick-off time
- Home and away teams
- Tries scored
- Final scores

Rounds may be numeric or descriptive knockout stages such as _Quarter-Final_, _Semi-Final_ and _Final_.

### Automatic League Tables

Automatically calculate league standings directly from recorded match results.

The tracker calculates:

- Played
- Won
- Drawn
- Lost
- Points For
- Points Against
- Points Difference
- Tries For
- Tries Against
- Try Bonus Points
- Losing Bonus Points
- Grand Slam Bonus Points
- Total Bonus Points
- League Points

League tables are calculated dynamically rather than stored in the database.

For the Premiership Rugby and Premiership Women's Rugby rulesets, matches marked _Quarter-Final_, _Semi-Final_ or _Final_ are excluded from the league table. Teams are ranked by league points and then points difference, both descending.

For the Men's and Women's Six Nations rulesets, the tracker validates the six-team, 15-match single round robin and ranks teams by competition points, points difference and tries scored. Once every result is present, it also determines the champion (including a shared title), Grand Slam, Triple Crown and Wooden Spoon.

For the 2026 WXV Global Series and Global Series Challenger rulesets, the tracker supports the published selected-fixture formats and ranks teams by competition points, points difference and tries scored.

For the 2026 Nations Championship Southern and Northern Series, the tracker supports the published cross-hemisphere fixtures and shared match-points rules. Teams are ranked by competition points, wins, points difference and then tries scored.

### Competition Rules

Support for competition-specific points systems, including:

- Premiership Rugby (2025/26)
- Premiership Women's Rugby (2025/26)
- Men's Six Nations
- Women's Six Nations
- WXV Global Series (2026)
- WXV Global Series Challenger (2026)
- Nations Championship Series (2026)

### CSV Import

Import data from CSV files for:

- Countries
- Venues
- Teams
- Referees
- Competitions
- Matches

Match imports automatically resolve related entities using case-insensitive name matching while validating all foreign-key relationships.

Teams and venues reference the countries table. Teams require a country and are uniquely identified by the combination of team name and country. Match CSV files include _home_country_ and _away_country_ alongside the corresponding team names so imports resolve the intended teams unambiguously.

Imports are additive: when a CSV row identifies a venue, team, competition, referee or match that already exists, the row is skipped and the stored record is left unchanged. To change an existing record, edit it in the application rather than re-importing it.

The same data can be exported from the command line:

```bash
rugby-import --type matches --input matches.csv
```

Supported types are _countries_, _competitions_, _venues_, _teams_, _referees_, and _matches_. The convenience wrapper accepts the same values:

```bash
./scripts/import.sh matches matches.csv
```

### CSV Export

Export calculated league tables to CSV for use in spreadsheets or further analysis.

The CSV Export page can also export all competitions, venues, teams, referees, and matches using the same schemas accepted by CSV Import. Export filenames have editable, type-specific defaults.

Exports can be filtered to one competition. A filtered export contains only that competition, its matches, participating teams, appointed referees, match venues, and the participating teams' home venues.

The same data can be exported from the command line:

```bash
rugby-export --type matches --output matches.csv
```

Supported types are _countries_, _competitions_, _venues_, _teams_, _referees_, and _matches_. The convenience wrapper accepts the same values:

```bash
./scripts/export.sh matches matches.csv
```

## Feedback

To file issues or suggestions, please use the [Issues](https://github.com/davewalker5/RugbyTracker/issues) page for this project on GitHub.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
