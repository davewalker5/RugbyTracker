# Version 0.3.0

Version 0.3.0 introduces automatic league table calculation, allowing the Rugby Tracker to derive competition standings directly from recorded match results.

Competition tables are calculated dynamically rather than being stored in the database, ensuring that standings always reflect the current set of recorded fixtures and scores.

The release also introduces support for competition-specific rules, providing a foundation for handling the differing bonus point systems used by rugby competitions.

## New Features

### Automatic League Table Calculation

League standings are now calculated automatically from recorded match results.

The following statistics are calculated for every team:

- Played (P)
- Won (W)
- Drawn (D)
- Lost (L)
- Points For (PF)
- Points Against (PA)
- Points Difference (PD)
- Try Bonus Points (TBP)
- Losing Bonus Points (LBP)
- Total Bonus Points (BP)
- League Points (Pts)

Tables are generated on demand, ensuring they always remain consistent with the recorded results.

### Competition Rules

Support has been added for competition-specific league rules.

The initial release includes rulesets for:

- Premiership Rugby (2025/26)
- Premiership Women's Rugby (2025/26)

This framework allows additional competitions to be supported in future releases while keeping the calculation logic separate from the underlying data.

### CSV Export

Calculated league tables can now be exported to CSV for use in spreadsheets, reports or further analysis.

## Technical

- Dynamic league table calculation
- Competition-specific scoring rules
- Automatic calculation of bonus points
- CSV export of calculated standings
- Separation of competition rules from the core table calculation logic

## Notes

Version 0.3.0 completes the core functionality originally planned for the Rugby Tracker.

The application now supports the complete workflow:

1. Record reference data
2. Import competitions and fixtures from CSV
3. Record match results
4. Automatically calculate league tables
5. Export standings for further analysis

Future development may extend the tracker to support additional competition formats, knockout stages, player statistics and richer match information.

---

# Version 0.2.0

Version 0.2.0 introduces CSV import support, making it straightforward to populate the Rugby Tracker with existing competition data.

Rather than manually entering every venue, team and fixture, data can now be imported from CSV files, allowing complete competitions to be loaded into the database quickly while maintaining referential integrity.

## New Features

### CSV Import

Support has been added for importing:

- Venues
- Teams
- Referees
- Competitions
- Matches

### Intelligent Entity Mapping

Match imports reference related entities by name rather than database ID. During import, the application automatically performs case-insensitive matching for:

- Competition
- Venue
- Referee
- Home team
- Away team

This allows CSV files to remain readable and portable while avoiding the need to know internal database identifiers.

### Import Validation

CSV imports are fully validated before data is written to the database. Validation includes:

- Verification that referenced entities exist
- Detection of invalid or missing references
- Clear error reporting for failed imports

This helps preserve database integrity while providing useful feedback when source data requires correction.

## Technical

- CSV import framework for all primary entities
- Case-insensitive entity matching
- Validation of foreign-key relationships during import
- Import summary reporting
- Improved workflow for populating new databases

## Notes

With CSV import now available, the Rugby Tracker can be populated efficiently from externally maintained fixture lists and competition data.

The next planned release will introduce automatic league table calculation, including support for competition-specific bonus point rules and CSV export of calculated standings.

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