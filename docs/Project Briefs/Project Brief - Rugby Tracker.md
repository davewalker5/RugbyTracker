# Project Brief: Rugby Tracker

## Overview

The Rugby Tracker is a lightweight desktop application for recording rugby fixtures, results and competition standings.

The primary goal is to provide a simple, self-contained database for tracking competitions such as Premiership Rugby, Premiership Women's Rugby (PWR), the Six Nations and other domestic or international tournaments.

Rather than acting as a live scoring system, the application is intended to support manual entry and historical record keeping, with automatic calculation of league tables from recorded match results.

The project follows the same philosophy as the Fossil Tracker project:

- Simple relational data model
- Local SQLite database
- Streamlit user interface
- Incremental feature development
- Well-structured, understandable code rather than unnecessary complexity

---

# Objectives

The application should:

- Record venues, teams, referees and competitions
- Record individual match results
- Provide simple browsing and editing of stored data
- Summarise fixtures and results for a competition
- Calculate competition tables automatically using competition-specific rules
- Import data from CSV files
- Export calculated league tables

The application is intended for personal use rather than live multi-user operation.

---

# Technology Stack

- Python
- Streamlit
- SQLite
- pytest for unit tests
- yoyo migrations for database migrations

The application should follow the same architectural style as the Fossil Tracker project:

- SQLite database layer
- Data access layer
- Business logic layer
- Streamlit presentation layer

A minimal pyproject.toml has already been added to the project but additional dependencies should be added as needed.

Source code should be implemented under the "src" folder, unit tests under the "tests" folder. SQLite migrations should be stored in the "migrations" folder

---

# Version 0.1.0 — Core Match Database

## Database Location

If the environment variable "RUGBY_TRACKER_DB" is set, that should be used as the full path to the database. Otherwise, the following path should be used relative to the project root:

```
data/rugbytracker.db
```

## Database Entities

### Venues

Store:

- Name
- Town/City (optional)
- Country (optional)

---

### Teams

Store:

- Name
- Men's / Women's flag
- Home venue (foreign key)

---

### Competitions

Store:

- Name
- Season (for example `2025/26`)
- Men's / Women's flag

---

### Referees

Store:

- Name

---

### Matches

Store:

- Competition
- Round (optional)
- Venue
- Referee (optional)
- Date
- Kick-off time (optional)
- Home team
- Away team
- Home tries
- Away tries
- Home score
- Away score

Derived values (not stored):

- Winning team
- Losing team
- Draw

---

## User Interface

Provide CRUD pages for:

- Venues
- Teams
- Competitions
- Referees
- Matches

Provide a **Competition Summary** page that displays:

- Competition information
- Ordered list of rounds
- Fixtures
- Results
- Scores

League tables are **not** part of Version 0.1.0.

---

## Non-functional Requirements

- Empty database on first run
- No seeded reference data
- Foreign key integrity enforced
- Validation of mandatory fields
- Clear validation error messages

---

# Version 0.2.0 — CSV Import

Support CSV import of:

- Teams
- Competitions
- Referees
- Matches

The match import should use entity names rather than numeric IDs.

The following fields should be matched case-insensitively:

- Competition
- Venue
- Referee (optional)
- Home team
- Away team

The import process should:

- Validate every referenced entity
- Report all validation failures
- Refuse to import invalid rows
- Produce a summary of imported records

The import process should be repeatable and avoid creating duplicate entities where practical.

---

# Version 0.3.0 — League Tables

Introduce automatic calculation of competition standings.

Because different competitions use different bonus point systems, introduce a configurable rules mechanism.

Two implementation approaches are acceptable:

1. Fully configurable rules stored in the database.

or

2. Competition rules implemented in code and selected via a ruleset identifier stored against the competition.

The second approach is preferred initially due to its simplicity.

Create rulesets for:

- Premiership Rugby (2025/26)
- Premiership Women's Rugby (2025/26)

---

## League Table Calculation

Automatically calculate:

| Column | Description |
|---------|-------------|
| P | Played |
| W | Won |
| D | Drawn |
| L | Lost |
| PF | Points For |
| PA | Points Against |
| PD | Points Difference |
| TBP | Try Bonus Points |
| LBP | Losing Bonus Points |
| BP | Total Bonus Points |
| Pts | League Points |

The table should be calculated entirely from recorded match results.

No table values should be stored in the database.

---

## Export

Support export of the calculated league table to CSV.

---

# Out of Scope

The following are intentionally excluded from the initial project:

- Live scoring
- Multiple users
- Authentication
- Online synchronisation
- Player statistics
- Individual player records
- Team line-ups
- Yellow cards
- Red cards
- Match event timelines
- Attendance figures
- Weather conditions
- Knockout tournament brackets
- Predictive modelling

These features may be considered for future releases.

---

# Coding Standards

The implementation should follow the same standards used across the Field Notes projects.

- Fully commented public and private methods with:
  - docstring comments
  - Including brief :param comments, where relevant
  - Including brief :return comments, where relevant
- Clear inline comments explaining the logic
- Separation of database, business logic and UI
- Small, readable methods
- Avoid unnecessary abstraction
- Favour clarity over cleverness
