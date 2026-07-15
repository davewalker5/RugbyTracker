"""Streamlit presentation layer for Rugby Tracker."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

import pandas as pd
import streamlit as st
from pandas.io.formats.style import Styler

from rugby_tracker.database import apply_migrations, connect
from rugby_tracker.exports import EXPORT_TYPES, CsvExportService
from rugby_tracker.imports import IMPORT_TYPES, CsvImportService, ImportReport
from rugby_tracker.services import GENDERS, RugbyService, ValidationError
from rugby_tracker.standings import RULESETS


WIN_BACKGROUND = "#d9ead3"
LOSS_BACKGROUND = "#f4cccc"
DRAW_BACKGROUND = "#fff2cc"
MEN_AND_WOMEN = "Men and Women"
GENDER_FILTERS = (MEN_AND_WOMEN, *GENDERS)


def _filter_by_gender(
    records: list[dict[str, Any]], selected_gender: str
) -> list[dict[str, Any]]:
    """Filter gendered records while supporting an inclusive default.

    :param records: Team or competition rows containing a ``gender`` value.
    :param selected_gender: ``All``, ``Men``, or ``Women``.
    :return: Every record for ``All`` or records matching the selected gender.
    """
    if selected_gender == MEN_AND_WOMEN:
        return records
    return [row for row in records if row.get("gender") == selected_gender]


def _style_match_results(table: pd.DataFrame, matches: list[dict[str, Any]]) -> Styler:
    """Colour the team cells in completed fixtures according to the result.

    :param table: Display-ready table with home/away team and country columns.
    :param matches: Match records corresponding positionally to the table rows.
    :return: Styled table with winner, loser, and draw backgrounds applied.
    """
    styled = table.style
    side_columns = {
        "Home": ["Home", "Home Country"],
        "Away": ["Away", "Away Country"],
    }
    for index, match in enumerate(matches):
        home_score = match["home_score"]
        away_score = match["away_score"]
        if home_score is None or away_score is None:
            continue
        if home_score == away_score:
            styled.set_properties(
                subset=pd.IndexSlice[[index], side_columns["Home"] + side_columns["Away"]],
                **{"background-color": DRAW_BACKGROUND},
            )
            continue
        winner = "Home" if home_score > away_score else "Away"
        loser = "Away" if winner == "Home" else "Home"
        styled.set_properties(
            subset=pd.IndexSlice[[index], side_columns[winner]],
            **{"background-color": WIN_BACKGROUND},
        )
        styled.set_properties(
            subset=pd.IndexSlice[[index], side_columns[loser]],
            **{"background-color": LOSS_BACKGROUND},
        )
    return styled


def _options(records: list[dict[str, Any]], label: Callable[[dict[str, Any]], str] | None = None) -> dict[int, str]:
    """Convert entity rows to identifier and display-label options.

    :param records: Entity rows containing at least ``id`` and ``name``.
    :param label: Optional formatter used to produce each display label.
    :return: Mapping of entity identifiers to display labels.
    """
    formatter = label or (lambda row: row["name"])
    return {row["id"]: formatter(row) for row in records}


def _select(
    label: str,
    options: dict[int, str],
    value: int | None = None,
    optional: bool = False,
    placeholder: str | None = None,
    key: str | None = None,
) -> int | None:
    """Render an entity selection widget.

    :param label: User-facing widget label.
    :param options: Mapping of entity identifiers to display labels.
    :param value: Identifier selected initially, when present.
    :param optional: Whether the placeholder should identify the field as optional.
    :param placeholder: Optional placeholder override for the empty state.
    :param key: Optional stable Streamlit widget key.
    :return: The selected identifier, or ``None`` while no option is selected.
    """
    keys = list(options)
    index = keys.index(value) if value is not None and value in keys else None
    empty_label = placeholder or f"Select {label.rstrip(' *').lower()}"
    if optional and placeholder is None:
        empty_label += " (optional)"
    return st.selectbox(
        label,
        keys,
        index=index,
        format_func=lambda key: "—" if key is None else options[key],
        placeholder=empty_label,
        key=key,
    )


def _selected_record(
    records: list[dict[str, Any]], selected_rows: list[int]
) -> dict[str, Any] | None:
    """Resolve a single table-row selection to its source record.

    :param records: Source records in the same order as the displayed table.
    :param selected_rows: Positional row indexes selected in the table.
    :return: The selected record, or ``None`` when the selection is empty or stale.
    """
    if not selected_rows:
        return None
    index = selected_rows[0]
    return records[index] if 0 <= index < len(records) else None


def _finish_action(connection: Any, message: str) -> None:
    """Commit a UI action, queue a notice, and refresh the page.

    :param connection: Active database connection to commit.
    :param message: Success notice to display after refreshing.
    :return: None.
    """
    connection.commit()
    st.session_state["notice"] = message
    st.rerun()


def _show_notice() -> None:
    """Display and remove the queued success notice, when present.

    :return: None.
    """
    if notice := st.session_state.pop("notice", None):
        st.success(notice)


def _form_actions(can_delete: bool) -> tuple[bool, bool, bool]:
    """Render aligned Save, Delete, and Clear form buttons.

    :param can_delete: Whether an existing record is selected and may be deleted.
    :return: Flags indicating whether Save, Delete, or Clear was submitted.
    """
    save_column, delete_column, clear_column = st.columns(3)
    with save_column:
        save_clicked = st.form_submit_button("Save", type="primary", width="stretch")
    with delete_column:
        delete_clicked = st.form_submit_button(
            "Delete", disabled=not can_delete, width="stretch"
        )
    with clear_column:
        clear_clicked = st.form_submit_button("Clear", width="stretch")
    return save_clicked, delete_clicked, clear_clicked


def _entity_page(
    title: str,
    singular: str,
    records: list[dict[str, Any]],
    fields: Callable[[dict[str, Any] | None], dict[str, Any]] | None,
    save: Callable[..., int],
    delete: Callable[[int], None],
    columns: dict[str, str],
    connection: Any,
    gender_filter_key: str | None = None,
) -> None:
    """Render a reusable list and CRUD form for a reference entity.

    :param title: Plural page heading.
    :param singular: Singular entity name used in form labels and messages.
    :param records: Existing entity rows to display and edit.
    :param fields: Form builder returning values to save.
    :param save: Callback that creates or updates an entity.
    :param delete: Callback that deletes an entity by identifier.
    :param columns: Mapping of record keys to table headings.
    :param connection: Active database connection for commits.
    :param gender_filter_key: Optional widget key enabling the gender table filter.
    :return: None.
    """
    st.header(title)
    if gender_filter_key is not None:
        # Keep filtering outside the edit form so changing it immediately refreshes the table.
        selected_gender = st.selectbox(
            "Gender",
            GENDER_FILTERS,
            index=0,
            key=gender_filter_key,
        )
        records = _filter_by_gender(records, selected_gender)
    selected = None
    table_key = f"{singular}_table"
    if records:
        if st.session_state.pop(f"reset_{table_key}", False):
            st.session_state[table_key] = {"selection": {"rows": []}}
        event = st.dataframe(
            [{heading: row.get(key) for key, heading in columns.items()} for row in records],
            width="stretch",
            hide_index=True,
            key=table_key,
            on_select="rerun",
            selection_mode="single-row",
        )
        selected = _selected_record(records, event.selection.rows)
        st.caption("Select a table row to edit it, or use the blank form to add a new record.")
    else:
        st.info(f"No {title.lower()} have been recorded yet.")

    st.subheader(f"Add or edit {singular}")
    form_record = selected["id"] if selected else "new"
    with st.form(f"{singular}_form_{form_record}", clear_on_submit=True):
        values = fields(selected) if fields else {}
        save_clicked, delete_clicked, clear_clicked = _form_actions(selected is not None)
        if clear_clicked:
            st.session_state[f"reset_{table_key}"] = True
            st.rerun()
        try:
            if save_clicked:
                save(entity_id=selected["id"] if selected else None, **values)
                _finish_action(connection, f"{singular.title()} saved.")
            if delete_clicked and selected:
                st.session_state[f"reset_{table_key}"] = True
                delete(selected["id"])
                _finish_action(connection, f"{singular.title()} deleted.")
        except (ValidationError, LookupError) as error:
            st.error(str(error))


def venues_page(service: RugbyService, connection: Any) -> None:
    """Render the venue CRUD page.

    :param service: Business service used for venue operations.
    :param connection: Active database connection for commits.
    :return: None.
    """
    records, countries = service.list_venues(), service.list_countries()
    country_options = _options(countries)

    def fields(row: dict[str, Any] | None) -> dict[str, Any]:
        """Render venue fields and collect their values.

        :param row: Existing venue row, or ``None`` for a new venue.
        :return: Values entered in the venue form.
        """
        return {
            "name": st.text_input("Name *", value=row["name"] if row else ""),
            "town_city": st.text_input("Town/City", value=(row["town_city"] or "") if row else ""),
            "country_id": _select(
                "Country", country_options, row["country_id"] if row else None,
                optional=True,
            ),
        }

    _entity_page("Venues", "venue", records, fields, service.save_venue,
                 lambda entity_id: service.delete("venue", entity_id),
                 {"name": "Name", "town_city": "Town/City", "country": "Country"}, connection)


def teams_page(service: RugbyService, connection: Any) -> None:
    """Render the team CRUD page.

    :param service: Business service used for team operations.
    :param connection: Active database connection for commits.
    :return: None.
    """
    records, venues = service.list_teams(), service.list_venues()
    countries = service.list_countries()
    venue_options = _options(venues)
    country_options = _options(countries)
    venue_names = {row["id"]: row["name"] for row in venues}
    if not venues or not countries:
        st.header("Teams")
        missing = "countries and venues" if not countries and not venues else (
            "countries" if not countries else "a venue"
        )
        st.warning(f"Import {missing} before adding a team.")
        return

    def fields(row: dict[str, Any] | None) -> dict[str, Any]:
        """Render team fields and collect their values.

        :param row: Existing team row, or ``None`` for a new team.
        :return: Values entered in the team form.
        """
        return {
            "name": st.text_input("Name *", value=row["name"] if row else ""),
            "country_id": _select(
                "Country *", country_options, row["country_id"] if row else None
            ),
            "gender": st.selectbox(
                "Category *",
                GENDERS,
                index=GENDERS.index(row["gender"]) if row else None,
                placeholder="Select a category",
            ),
            "home_venue_id": _select("Home venue *", venue_options, row["home_venue_id"] if row else None),
        }

    display_rows = [{**row, "home_venue": venue_names.get(row["home_venue_id"], "")} for row in records]
    _entity_page("Teams", "team", display_rows, fields, service.save_team,
                 lambda entity_id: service.delete("team", entity_id),
                 {
                     "name": "Name", "country": "Country", "gender": "Category",
                     "home_venue": "Home venue",
                 }, connection, gender_filter_key="teams_gender_filter")


def competitions_page(service: RugbyService, connection: Any) -> None:
    """Render the competition CRUD page.

    :param service: Business service used for competition operations.
    :param connection: Active database connection for commits.
    :return: None.
    """
    records = service.list_competitions()
    ruleset_options = ["", *RULESETS]

    def fields(row: dict[str, Any] | None) -> dict[str, Any]:
        """Render competition fields and collect their values.

        :param row: Existing competition row, or ``None`` for a new competition.
        :return: Values entered in the competition form.
        """
        return {
            "name": st.text_input("Name *", value=row["name"] if row else ""),
            "season": st.text_input("Season *", value=row["season"] if row else "", placeholder="2025/26"),
            "gender": st.selectbox(
                "Category *",
                GENDERS,
                index=GENDERS.index(row["gender"]) if row else None,
                placeholder="Select a category",
            ),
            "ruleset": st.selectbox(
                "League-table ruleset",
                ruleset_options,
                index=(
                    ruleset_options.index(row["ruleset"] or "")
                    if row and (row["ruleset"] or "") in ruleset_options else None
                ),
                format_func=lambda value: "No league table" if value == "" else RULESETS[value].label,
                placeholder="Select a league-table ruleset (optional)",
            ),
        }

    display_rows = [
        {
            **row,
            "ruleset_label": RULESETS[row["ruleset"]].label if row.get("ruleset") in RULESETS else "—",
        }
        for row in records
    ]
    _entity_page("Competitions", "competition", display_rows,
                 fields, service.save_competition,
                 lambda entity_id: service.delete("competition", entity_id),
                 {"name": "Name", "season": "Season", "gender": "Category", "ruleset_label": "Ruleset"},
                 connection, gender_filter_key="competitions_gender_filter")


def referees_page(service: RugbyService, connection: Any) -> None:
    """Render the referee CRUD page.

    :param service: Business service used for referee operations.
    :param connection: Active database connection for commits.
    :return: None.
    """
    records = service.list_referees()

    def fields(row: dict[str, Any] | None) -> dict[str, Any]:
        """Render the referee name field and collect its value.

        :param row: Existing referee row, or ``None`` for a new referee.
        :return: Values entered in the referee form.
        """
        return {"name": st.text_input("Name *", value=row["name"] if row else "")}

    _entity_page("Referees", "referee", records, fields, service.save_referee,
                 lambda entity_id: service.delete("referee", entity_id), {"name": "Name"}, connection)


def countries_page(service: RugbyService, connection: Any) -> None:
    """Render the country CRUD page.

    :param service: Business service used for country operations.
    :param connection: Active database connection for commits.
    :return: None.
    """
    records = service.list_countries()

    def fields(row: dict[str, Any] | None) -> dict[str, Any]:
        """Render the country name field and collect its value.

        :param row: Existing country row, or ``None`` for a new country.
        :return: Values entered in the country form.
        """
        return {"name": st.text_input("Name *", value=row["name"] if row else "")}

    _entity_page(
        "Countries", "country", records, fields, service.save_country,
        lambda entity_id: service.delete("country", entity_id), {"name": "Name"},
        connection,
    )


def matches_page(service: RugbyService, connection: Any) -> None:
    """Render the match CRUD page for fixtures and results.

    :param service: Business service used for match operations.
    :param connection: Active database connection for commits.
    :return: None.
    """
    competitions, venues = service.list_competitions(), service.list_venues()
    teams, referees = service.list_teams(), service.list_referees()
    st.header("Matches")
    # Venues are optional because international fixtures can be announced before
    # their ground is confirmed; competitions and two teams remain prerequisites.
    missing = [name for name, records in (("competition", competitions), ("two teams", teams if len(teams) >= 2 else [])) if not records]
    if missing:
        st.warning("Before adding a match, add " + ", ".join(missing) + ".")
        return
    selected_competition_id = _select(
        "Competition",
        _options(competitions, lambda row: f"{row['name']} — {row['season']}"),
        key="matches_competition_filter",
    )
    if selected_competition_id is None:
        st.info("Select a competition to view its matches.")
        return
    matches = service.list_matches(int(selected_competition_id))
    selected = None
    table_key = f"matches_table_{selected_competition_id}"
    if matches:
        # Keep venue beside the round so the fixture context is visible before
        # the competing teams, with a fallback for grounds still to be confirmed.
        table = pd.DataFrame([{
            "Date": row["match_date"], "Competition": f"{row['competition_name']} {row['competition_season']}",
            "Round": row["round"] or "—", "Venue": row["venue_name"] or "TBC",
            "Home": row["home_team_name"],
            "Home Country": row["home_team_country"],
            "Away": row["away_team_name"],
            "Away Country": row["away_team_country"],
            "Score": "Fixture" if row["home_score"] is None else f"{row['home_score']}–{row['away_score']}",
            "Tries": "Fixture" if row["home_tries"] is None else f"{row['home_tries']}–{row['away_tries']}",
        } for row in matches])
        if st.session_state.pop(f"reset_{table_key}", False):
            st.session_state[table_key] = {"selection": {"rows": []}}
        event = st.dataframe(
            _style_match_results(table, matches),
            width="stretch",
            hide_index=True,
            key=table_key,
            on_select="rerun",
            selection_mode="single-row",
        )
        selected = _selected_record(matches, event.selection.rows)
        st.caption("Select a match row to edit it, or use the blank form to add a new match.")
    else:
        st.info("No matches have been recorded yet.")

    st.subheader("Add or edit match")
    form_record = selected["id"] if selected else "new"
    with st.form(f"match_form_{form_record}", clear_on_submit=True):
        competition_id = _select(
            "Competition *",
            _options(competitions, lambda row: f"{row['name']} — {row['season']}"),
            selected["competition_id"] if selected else None,
        )
        round_name = st.text_input(
            "Round",
            value=(selected["round"] or "") if selected else "",
            placeholder="e.g. 1, Quarter-Final, Semi-Final, or Final",
        )
        match_date = st.date_input("Date *", value=date.fromisoformat(selected["match_date"]) if selected else date.today())
        kickoff = st.text_input("Kick-off time", value=(selected["kickoff_time"] or "") if selected else "", placeholder="15:00")
        venue_id = _select(
            "Venue",
            _options(venues),
            selected["venue_id"] if selected else None,
            optional=True,
        )
        referee_id = _select("Referee", _options(referees), selected["referee_id"] if selected else None, optional=True)
        left, right = st.columns(2)
        with left:
            home_team_id = _select(
                "Home team *",
                _options(teams, lambda row: f"{row['name']} — {row['country']}"),
                selected["home_team_id"] if selected else None,
            )
            home_tries = st.text_input("Home tries", value=str(selected["home_tries"]) if selected and selected["home_tries"] is not None else "")
            home_score = st.text_input("Home score", value=str(selected["home_score"]) if selected and selected["home_score"] is not None else "")
        with right:
            away_team_id = _select(
                "Away team *",
                _options(teams, lambda row: f"{row['name']} — {row['country']}"),
                selected["away_team_id"] if selected else None,
            )
            away_tries = st.text_input("Away tries", value=str(selected["away_tries"]) if selected and selected["away_tries"] is not None else "")
            away_score = st.text_input("Away score", value=str(selected["away_score"]) if selected and selected["away_score"] is not None else "")
        st.caption("Leave all four try and score fields blank to save a future fixture.")
        save_clicked, delete_clicked, clear_clicked = _form_actions(selected is not None)
        if clear_clicked:
            st.session_state[f"reset_{table_key}"] = True
            st.rerun()
        try:
            if save_clicked:
                service.save_match(
                    entity_id=selected["id"] if selected else None, competition_id=competition_id,
                    round=round_name, venue_id=venue_id, referee_id=referee_id, match_date=match_date,
                    kickoff_time=kickoff, home_team_id=home_team_id, away_team_id=away_team_id,
                    home_tries=home_tries, away_tries=away_tries, home_score=home_score, away_score=away_score,
                )
                _finish_action(connection, "Match saved.")
            if delete_clicked and selected:
                st.session_state[f"reset_{table_key}"] = True
                service.delete("match", selected["id"])
                _finish_action(connection, "Match deleted.")
        except (ValidationError, LookupError) as error:
            st.error(str(error))


def league_table_page(service: RugbyService) -> None:
    """Render and offer CSV export for a calculated competition table.

    :param service: Business service used to calculate and export standings.
    :return: None.
    """
    st.header("League Table")
    competitions = service.list_competitions()
    if not competitions:
        st.info("Add a competition to calculate a league table.")
        return
    competition_id = _select(
        "Competition",
        _options(competitions, lambda row: f"{row['name']} — {row['season']}"),
        key="league_competition_filter",
    )
    if competition_id is None:
        st.info("Select a competition to calculate its league table.")
        return
    try:
        result = service.league_table(int(competition_id))
    except ValidationError as error:
        st.warning(str(error))
        return
    competition = result["competition"]
    st.subheader(f"{competition['name']} — {competition['season']}")
    st.caption(result["ruleset"].label)
    if result["table"]:
        st.dataframe(result["table"], width="stretch", hide_index=True)
    else:
        st.info("No teams appear in this competition's fixtures yet.")
    awarded = {
        award: teams for award, teams in result["awards"].items() if teams
    }
    if result["complete"] and awarded:
        st.subheader("Competition awards")
        for award, teams in awarded.items():
            st.markdown(f"**{award}:** {', '.join(teams)}")
    filename_name = "_".join(str(competition["name"]).lower().split())
    filename_season = str(competition["season"]).replace("/", "-")
    st.download_button(
        "Download league table CSV",
        service.league_table_csv(int(competition_id)),
        file_name=f"{filename_name}_{filename_season}_table.csv",
        mime="text/csv",
        disabled=not result["table"],
    )


def _show_import_report(report: ImportReport) -> None:
    """Render counts and validation failures from a CSV import.

    :param report: Completed CSV import report to display.
    :return: None.
    """
    imported, skipped, invalid = st.columns(3)
    imported.metric("Imported", report.imported)
    skipped.metric("Duplicates skipped", report.skipped)
    invalid.metric("Invalid rows", report.invalid)
    if report.issues:
        st.error("Some rows were not imported. Correct the errors below and import the file again.")
        st.dataframe(report.error_rows(), width="stretch", hide_index=True)
    elif report.total_rows == 0:
        st.warning("The CSV did not contain any data rows.")
    else:
        st.success("CSV import completed without validation errors.")


def import_page(connection: Any) -> None:
    """Render CSV templates, upload controls, and import results.

    :param connection: Active database connection used by the importer.
    :return: None.
    """
    st.header("CSV Import")
    st.write(
        "Import countries, venues, teams, competitions, referees, fixtures, and results. "
        "Names are matched without regard to capitalisation. Invalid rows are reported and refused."
    )
    entity_type = st.selectbox(
        "Record type",
        IMPORT_TYPES,
        index=None,
        placeholder="Select an import type",
    )
    if entity_type is None:
        st.info("Select an import type to download a template or import a CSV file.")
        return
    importer = CsvImportService(connection)
    st.download_button(
        "Download CSV template",
        importer.template(entity_type),
        file_name=f"rugby_tracker_{entity_type.lower()}.csv",
        mime="text/csv",
    )
    if entity_type == "Teams":
        st.caption(
            "Countries and home venues must already exist and are matched using the "
            "country and home_venue columns."
        )
    elif entity_type == "Venues":
        st.caption(
            "A supplied country must already exist and is matched using the country column."
        )
    elif entity_type == "Matches":
        st.caption(
            "Competitions are matched by name and season. Venues, referees, and teams must "
            "already exist. Round may be a number or text such as Quarter-Final, Semi-Final, "
            "or Final. Referee, round, kick-off, and all result fields may be blank."
        )
    uploaded = st.file_uploader("CSV file", type=("csv",), key=f"csv_{entity_type}")
    if st.button("Import CSV", type="primary", disabled=uploaded is None):
        assert uploaded is not None
        report = importer.import_csv(entity_type, uploaded.getvalue())
        connection.commit()
        _show_import_report(report)


def _export_validation_error(entity_type: str | None, file_stem: str | None) -> str | None:
    """Validate the fields required to download a CSV export.

    :param entity_type: Selected export record type, when supplied.
    :param file_stem: User-editable filename stem, when supplied.
    :return: A user-facing validation message, or ``None`` when valid.
    """
    # Report both omissions together so one click gives the user complete guidance.
    missing: list[str] = []
    if entity_type is None:
        missing.append("an export type")
    if not str(file_stem or "").strip():
        missing.append("a file stem")
    return f"Specify {' and '.join(missing)} before downloading." if missing else None


def _reset_export_file_stem() -> None:
    """Reset the export filename whenever the selected record type changes.

    :return: None.
    """
    # The callback deliberately overwrites user edits on every type change, as
    # each export type has a predictable default filename.
    entity_type = st.session_state.get("csv_export_type")
    st.session_state["csv_export_file_stem"] = (
        str(entity_type).casefold() if entity_type else ""
    )


def export_page(connection: Any) -> None:
    """Render selection, filename, and download controls for CSV exports.

    :param connection: Active database connection used by the exporter.
    :return: None.
    """
    # Keep the control layout parallel with CSV Import for familiarity.
    st.header("CSV Export")
    st.write(
        "Export countries, competitions, venues, teams, referees, fixtures, and results as CSV."
    )
    competitions = RugbyService(connection).list_competitions()
    entity_type = st.selectbox(
        "Record type",
        EXPORT_TYPES,
        index=None,
        placeholder="Select an export type",
        key="csv_export_type",
        on_change=_reset_export_file_stem,
    )
    competition_filter = st.selectbox(
        "Competition",
        ["All", *[int(row["id"]) for row in competitions]],
        index=0,
        format_func=lambda value: (
            "All" if value == "All" else next(
                f"{row['name']} — {row['season']}"
                for row in competitions if int(row["id"]) == value
            )
        ),
        key="csv_export_competition",
    )
    file_stem = st.text_input("File stem", key="csv_export_file_stem")
    validation_error = _export_validation_error(entity_type, file_stem)
    if validation_error:
        # A regular button can report invalid fields without initiating a browser
        # download; Streamlit's download control cannot cancel an invalid click.
        if st.button("Download", type="primary"):
            st.warning(validation_error)
    else:
        # Only render the browser download control after both required values pass.
        assert entity_type is not None
        competition_id = None if competition_filter == "All" else int(competition_filter)
        data = CsvExportService(connection).export_csv(entity_type, competition_id)
        st.download_button(
            "Download",
            data,
            file_name=f"{file_stem.strip()}.csv",
            mime="text/csv",
            type="primary",
        )


def main() -> None:
    """Configure and render the Rugby Tracker Streamlit application.

    :return: None.
    """
    st.set_page_config(page_title="Rugby Tracker", page_icon="🏉", layout="wide")
    apply_migrations()
    st.title("🏉 Rugby Tracker")
    st.markdown(
        """
        <style>
        div[role="radiogroup"] {
            gap: 0;
            border-bottom: 1px solid rgba(128, 128, 128, 0.35);
            margin-bottom: 1.25rem;
        }
        div[role="radiogroup"] > label {
            padding: 0.55rem 0.9rem 0.65rem;
            border-radius: 0.45rem 0.45rem 0 0;
        }
        div[role="radiogroup"] > label[data-selected="true"] {
            background: rgba(128, 128, 128, 0.13);
            border-bottom: 3px solid #ff4b4b;
            margin-bottom: -1px;
        }
        label[data-testid="stRadioOption"] > div > div > div:first-child {
            display: none;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    page = st.radio(
        "Navigate",
        (
            "League Table", "Matches", "Competitions", "Teams", "Venues", "Referees",
            "Countries",
            "CSV Import", "CSV Export",
        ),
        horizontal=True,
        label_visibility="collapsed",
    )
    _show_notice()
    connection = connect()
    try:
        service = RugbyService(connection)
        pages = {
            "League Table": lambda: league_table_page(service),
            "Matches": lambda: matches_page(service, connection),
            "CSV Import": lambda: import_page(connection),
            "CSV Export": lambda: export_page(connection),
            "Competitions": lambda: competitions_page(service, connection),
            "Teams": lambda: teams_page(service, connection),
            "Venues": lambda: venues_page(service, connection),
            "Referees": lambda: referees_page(service, connection),
            "Countries": lambda: countries_page(service, connection),
        }
        pages[page]()
    finally:
        connection.close()


if __name__ == "__main__":
    main()
