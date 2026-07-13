# Version 0.2.0



---

# Version 0.1.0

The initial release of the Rugby Tracker establishes the core database and user interface for recording rugby competitions and match results.

Version 0.1.0 provides a simple desktop application built with Streamlit and SQLite for maintaining a personal rugby database, recording fixtures and scores, and browsing competitions.

## New Features

### Core reference data

Support has been added for maintaining:

- Venues
- Teams
- Competitions
- Referees

### Match recording

Matches can now be recorded with:

- Competition
- Round
- Venue
- Referee
- Date and kick-off time
- Home and away teams
- Tries scored
- Final scores

### Competition summary

A competition summary page provides an overview of:

- Fixtures
- Results
- Scores
- Matches grouped by round

This release focuses on recording and browsing competition data rather than calculating league standings.

## Technical

- Python implementation
- Streamlit user interface
- SQLite database backend
- Normalised relational database schema
- CRUD interfaces for all primary entities
- Validation of required fields and foreign-key relationships

## Notes

This release establishes the core data model on which future functionality will build.

Planned future releases will add:

- CSV import
- Automatic league table calculation
- Competition-specific points systems
- CSV export of calculated tables