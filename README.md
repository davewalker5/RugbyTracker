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

### Competition Summary

Browse competitions and view:

- Fixtures
- Results
- Scores
- Matches grouped by round

### CSV Import

Import data from CSV files for:

- Venues
- Teams
- Referees
- Competitions
- Matches

Match imports automatically resolve related entities using case-insensitive name matching while validating all foreign-key relationships.

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
- Try Bonus Points
- Losing Bonus Points
- Total Bonus Points
- League Points

League tables are calculated dynamically rather than stored in the database.

For the Premiership Rugby and Premiership Women's Rugby rulesets, matches marked _Quarter-Final_, _Semi-Final_ or _Final_ are excluded from the league table. Teams are ranked by league points and then points difference, both descending.

### Competition Rules

Support for competition-specific points systems, including:

- Premiership Rugby (2025/26)
- Premiership Women's Rugby (2025/26)

### Export

Export calculated league tables to CSV for use in spreadsheets or further analysis.

## Feedback

To file issues or suggestions, please use the [Issues](https://github.com/davewalker5/RugbyTracker/issues) page for this project on GitHub.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
