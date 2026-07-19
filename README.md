[![GitHub issues](https://img.shields.io/github/issues/davewalker5/RugbyTracker)](https://github.com/davewalker5/RugbyTracker/issues)
[![Releases](https://img.shields.io/github/v/release/davewalker5/RugbyTracker.svg?include_prereleases)](https://github.com/davewalker5/RugbyTracker/releases)
[![License](https://img.shields.io/badge/License-mit-blue.svg)](https://github.com/davewalker5/RugbyTracker/blob/main/LICENSE)
[![Language](https://img.shields.io/badge/language-python-blue.svg)](https://www.python.org)
[![GitHub code size in bytes](https://img.shields.io/github/languages/code-size/davewalker5/RugbyTracker)](https://github.com/davewalker5/RugbyTracker/)

# Rugby Tracker

## Overview

Rugby Tracker is a desktop application for recording, analysing and exploring professional rugby union competitions.

It combines structured competition data, accurate competition modelling and supporter-focused analysis in a single application. Rather than acting as a live scoring service, Rugby Tracker provides a long-term reference for fixtures, results, league tables and season performance across domestic and international competitions.

Built using Python, Streamlit and SQLite, the application emphasises simple, maintainable design with a well-structured relational data model. Competition rules are modelled explicitly, allowing league tables and statistics to be calculated consistently across different tournaments.

Alongside fixture and results management, Rugby Tracker now includes integrated analysis reports designed to help supporters better understand a team's season without requiring specialist statistical knowledge.

---

## Competition Tracking Features

Rugby Tracker currently provides:

### Competition Database

Maintain structured reference data for:

- Countries
- Venues
- Teams
- Competitions
- Referees

Teams are linked to countries, while venues also reference their host country. This enables more accurate modelling of competitions involving teams with similar names and supports richer reporting.

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

Automatically calculate league standings directly from recorded match results. The tracker calculates:

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

## Supported Competitions

Current rulesets include:

- Premiership Rugby (PREM)
- Premiership Women's Rugby (PWR)
- Men's Six Nations
- Women's Six Nations
- WXV Global Series
- WXV Global Series Challenger
- Nations Championship Southern Series
- Nations Championship Northern Series

Additional competitions are added as their structures and regulations become established.

---

## Analysis Features

### Team Summary

The Analysis section provides supporter-focused reports built directly from the recorded competition data. **Team Summary** explores one team's season, **Team Form** concentrates on its latest completed matches, **Competition Summary** presents a season-wide view, and **Head-to-Head** compares every recorded meeting between two teams.

The report includes:

- Team overview
- Season record
- League performance
- Scoring summary
- Try summary
- Home and away performance
- Biggest wins and defeats
- Highest and lowest scoring matches
- Results breakdown charts
- Points scored and conceded through the season
- Chronological match history

Reports can also be exported as formatted PDF documents for sharing or offline reference.

### Team Form

The Team Form report provides a focused view of a team's recent performance within a selected competition and season. The form window is configurable from one to twenty completed matches and defaults to five.

The report includes:

- Recent wins, draws, losses, scoring, tries and competition points
- An oldest-to-newest form sequence
- A detailed recent-results table with knockout stages identified
- Results breakdown, scoring-form and try-scoring charts
- Home and away form with underlying match counts
- The current uninterrupted streak across the full season
- Comparison between recent form and season performance
- An explainable improving, broadly stable or declining trend assessment

Only completed matches contribute to the report. Competition points use the selected competition's ruleset, while missing try data and seasons shorter than the requested form window are handled gracefully. The complete report, including its charts, can be exported as a formatted PDF document.

### Head-to-Head

The Head-to-Head report includes:

- A single-season or all-seasons comparison
- Overall wins, draws, losses, scoring and try totals
- Records for matches hosted by each team
- Chronological match history
- Results timeline, points comparison and winning-margin charts
- Average scores, biggest victories and highest-scoring match
- One-score matches and matches decided by three points or fewer
- The current winning or drawing streak

Only teams participating in the selected competition are offered, and reports can be exported as formatted PDF documents.

### Competition Summary

The Competition Summary report includes:

- Competition overview and final league table
- Headline scoring, try and result statistics
- Attack and defence team rankings
- Home and away performance
- Scoring and winning-margin distributions
- Round-by-round scoring trends
- Highest-scoring and closest matches

Reports can also be exported as formatted PDF documents for sharing or offline reference.

---

## Data Exchange Features

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

CSV export complements the integrated analysis reports by making the same competition data available for external tools such as spreadsheets, Jupyter notebooks or other analytical workflows.

---

## Read-only deployments

Deployments served from _streamlit.app_ or any of its subdomains automatically run in demonstration read-only mode. Save, delete, and CSV import actions are disabled, while analysis and export features remain available.

Set _RUGBY_TRACKER_READ_ONLY_DOMAINS_ to a comma-separated list to replace the default, for example _streamlit.app,demo.example.com_.

---

## Feedback

To file issues or suggestions, please use the [Issues](https://github.com/davewalker5/RugbyTracker/issues) page for this project on GitHub.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
