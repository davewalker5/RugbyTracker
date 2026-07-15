"""Streamlit presentation layer for Rugby Tracker."""

from __future__ import annotations

from datetime import date
from html import escape
from typing import Any, Callable

import pandas as pd
import streamlit as st
from pandas.io.formats.style import Styler

from rugby_tracker.analysis import (
    CompetitionSummaryReport,
    HeadToHeadReport,
    TeamSummaryReport,
    competition_round_summary,
    competition_summary_filename,
    competition_team_rankings,
    head_to_head_filename,
    head_to_head_host_record,
    render_competition_summary_pdf,
    render_head_to_head_pdf,
    render_team_summary_pdf,
    team_summary_filename,
)
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


def _clear_analysis_season() -> None:
    """Clear dependent Analysis selections after a competition change.

    :return: None.
    """
    # Earlier selector changes must never leave a stale report visible.
    st.session_state.pop("analysis_season", None)
    st.session_state.pop("analysis_team", None)


def _clear_analysis_team() -> None:
    """Clear the selected team after a season change.

    :return: None.
    """
    # Teams are scoped to a specific competition-season record.
    st.session_state.pop("analysis_team", None)


def _clear_competition_analysis_season() -> None:
    """Clear the Competition Summary season after its competition changes.

    :return: None.
    """
    st.session_state.pop("competition_analysis_season", None)


def _clear_head_to_head_selections() -> None:
    """Clear dependent Head-to-Head selectors after competition changes.

    :return: None.
    """
    for key in ("head_to_head_season", "head_to_head_team_a", "head_to_head_team_b"):
        st.session_state.pop(key, None)


def _clear_head_to_head_teams() -> None:
    """Clear selected teams after the Head-to-Head season changes.

    :return: None.
    """
    st.session_state.pop("head_to_head_team_a", None)
    st.session_state.pop("head_to_head_team_b", None)


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
    on_change: Callable[[], None] | None = None,
) -> int | None:
    """Render an entity selection widget.

    :param label: User-facing widget label.
    :param options: Mapping of entity identifiers to display labels.
    :param value: Identifier selected initially, when present.
    :param optional: Whether the placeholder should identify the field as optional.
    :param placeholder: Optional placeholder override for the empty state.
    :param key: Optional stable Streamlit widget key.
    :param on_change: Optional callback invoked when the selection changes.
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
        on_change=on_change,
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


def _metric_cards(values: list[tuple[str, str | int | float]]) -> None:
    """Render notebook-style metrics as rounded, responsive cards.

    :param values: Ordered label and display-value pairs.
    :return: None.
    """
    # Escape calculated and database-backed text before placing it in HTML.
    cards = "".join(
        "<div class='team-summary-card'>"
        f"<div class='team-summary-card-label'>{escape(str(label))}</div>"
        f"<div class='team-summary-card-value'>{escape(str(value))}</div>"
        "</div>"
        for label, value in values
    )
    st.markdown(
        """
        <style>
        .team-summary-card-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            margin: 0.25rem 0 1rem;
        }
        .team-summary-card {
            flex: 1 1 120px;
            min-width: 120px;
            padding: 12px 16px;
            border: 1px solid rgba(128, 128, 128, 0.35);
            border-radius: 8px;
            background: rgba(128, 128, 128, 0.035);
        }
        .team-summary-card-label {
            color: rgba(128, 128, 128, 0.95);
            font-size: 0.82rem;
            line-height: 1.25;
        }
        .team-summary-card-value {
            margin-top: 0.2rem;
            font-size: 1.25rem;
            font-weight: 700;
            line-height: 1.3;
        }
        </style>
        """
        f"<div class='team-summary-card-row'>{cards}</div>",
        unsafe_allow_html=True,
    )


def _render_competition_summary(report: CompetitionSummaryReport) -> None:
    """Render a structured competition summary in Streamlit.

    :param report: Calculated report shared with the PDF renderer.
    :return: None.
    """
    st.header(f"{report.competition} — {report.season}")
    st.download_button(
        "Download PDF",
        render_competition_summary_pdf(report),
        file_name=competition_summary_filename(report),
        mime="application/pdf",
        type="primary",
        key="competition_summary_pdf",
    )

    st.subheader("Competition overview")
    _metric_cards([
        ("Teams", report.team_count),
        ("Completed matches", report.completed_matches),
        ("Scheduled matches", report.scheduled_matches),
        ("Total tries", report.total_tries if report.total_tries is not None else "Unavailable"),
        ("Total points", report.total_points),
    ])

    st.subheader("Final league table")
    table_columns = ("Pos", "Team", "P", "W", "D", "L", "PF", "PA", "PD", "Pts")
    st.dataframe(pd.DataFrame([
        {column: row[column] for column in table_columns} for row in report.league_table
    ]), hide_index=True, width="stretch")
    if report.table_provisional_notes:
        st.caption("Table is provisional: " + "; ".join(report.table_provisional_notes))

    st.subheader("Competition statistics")
    _metric_cards([
        ("Average points", f"{report.average_points:.1f}"),
        ("Average tries", f"{report.average_tries:.1f}" if report.average_tries is not None else "Unavailable"),
        ("Home wins", report.home_wins),
        ("Away wins", report.away_wins),
        ("Draws", report.draws),
    ])
    highlights = (
        ("Highest-scoring match", report.highest_scoring, "total_points"),
        ("Lowest-scoring match", report.lowest_scoring, "total_points"),
        ("Largest winning margin", report.largest_margin, "winning_margin"),
    )
    st.dataframe(pd.DataFrame([{
        "Highlight": label,
        "Match": match.context if match else "No completed match",
        "Points / margin": getattr(match, measure) if match else None,
    } for label, match, measure in highlights]), hide_index=True, width="stretch")

    st.subheader("Team rankings")
    st.dataframe(pd.DataFrame(competition_team_rankings(report)), hide_index=True, width="stretch")

    st.subheader("Home and away performance")
    denominator = report.completed_matches or 1
    outcomes = pd.DataFrame({"Percentage": [
        report.home_wins / denominator * 100,
        report.away_wins / denominator * 100,
        report.draws / denominator * 100,
    ]}, index=["Home wins", "Away wins", "Draws"])
    _metric_cards([(label, f"{value:.1f}%") for label, value in outcomes["Percentage"].items()])
    st.bar_chart(outcomes, y_label="Percentage of completed matches")

    st.subheader("Scoring distribution and winning margins")
    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.markdown("**Points scored per match**")
        scoring = pd.Series([match.total_points for match in report.matches]).value_counts().sort_index()
        st.bar_chart(scoring.rename("Matches"), x_label="Total match points", y_label="Matches")
    with chart_right:
        st.markdown("**Winning margins**")
        margins = pd.Series([match.winning_margin for match in report.matches]).value_counts().sort_index()
        st.bar_chart(margins.rename("Matches"), x_label="Points (draws = 0)", y_label="Matches")

    st.subheader("Results by round")
    rounds = competition_round_summary(report)
    round_table = pd.DataFrame(rounds)
    if not round_table.empty:
        round_table["Average points"] = round_table["Average points"].map(lambda value: round(value, 1))
        st.dataframe(round_table, hide_index=True, width="stretch")
        st.line_chart(
            round_table.set_index("Round")[["Average points"]],
            y_label="Average points per match",
        )
    else:
        st.info("No completed matches to summarise by round.")

    st.subheader("Highest-scoring matches")
    highest = sorted(report.matches, key=lambda match: (-match.total_points, match.match_date))[:10]
    st.dataframe(pd.DataFrame([{
        "Date": match.match_date, "Round": match.round, "Home": match.home_team,
        "Away": match.away_team, "Score": match.score, "Total points": match.total_points,
    } for match in highest]), hide_index=True, width="stretch")

    st.subheader("Closest matches")
    closest = sorted(report.matches, key=lambda match: (match.winning_margin, match.match_date))[:10]
    st.dataframe(pd.DataFrame([{
        "Date": match.match_date, "Home": match.home_team, "Away": match.away_team,
        "Score": match.score, "Winning margin": match.winning_margin,
    } for match in closest]), hide_index=True, width="stretch")


def _render_head_to_head(report: HeadToHeadReport) -> None:
    """Render a structured Head-to-Head report in Streamlit.

    :param report: Calculated report shared with the PDF renderer.
    :return: None.
    """
    st.header(f"{report.team_a} v {report.team_b}")
    st.caption(f"{report.competition} · {report.season}")
    st.download_button(
        "Download PDF", render_head_to_head_pdf(report),
        file_name=head_to_head_filename(report), mime="application/pdf",
        type="primary", key="head_to_head_pdf",
    )

    st.subheader("Fixture summary")
    _metric_cards([
        ("Competition", report.competition), ("Season", report.season),
        ("Team A", report.team_a), ("Team B", report.team_b),
        ("Meetings", report.meetings),
    ])

    st.subheader("Overall head-to-head record")
    tries_a = report.team_a_tries if report.team_a_tries is not None else "Unavailable"
    tries_b = report.team_b_tries if report.team_b_tries is not None else "Unavailable"
    st.dataframe(pd.DataFrame({
        "Statistic": ["Wins", "Draws", "Losses", "Win percentage", "Points scored", "Points conceded", "Tries scored", "Tries conceded"],
        report.team_a: [str(report.team_a_wins), str(report.draws), str(report.team_b_wins),
                        f"{report.team_a_wins / report.meetings:.1%}", str(report.team_a_points),
                        str(report.team_b_points), str(tries_a), str(tries_b)],
        report.team_b: [str(report.team_b_wins), str(report.draws), str(report.team_a_wins),
                        f"{report.team_b_wins / report.meetings:.1%}", str(report.team_b_points),
                        str(report.team_a_points), str(tries_b), str(tries_a)],
    }), hide_index=True, width="stretch")

    st.subheader("Home and away record")
    host_rows = [head_to_head_host_record(report, team) for team in (report.team_a, report.team_b)]
    for row in host_rows:
        row["Average points scored"] = round(row["Average points scored"], 1)
        row["Average points conceded"] = round(row["Average points conceded"], 1)
    st.dataframe(pd.DataFrame(host_rows), hide_index=True, width="stretch")

    st.subheader("Match history")
    history = pd.DataFrame([{
        "Date": match.match_date, "Competition": match.competition,
        "Season": match.season, "Round": match.round, "Venue": match.venue,
        "Home": match.home_team, "Away": match.away_team, "Score": match.score,
        "Winner": report.team_a if match.winner == "A" else report.team_b if match.winner == "B" else "Draw",
    } for match in report.matches])
    st.dataframe(history, hide_index=True, width="stretch")

    st.subheader("Results timeline")
    timeline = pd.DataFrame({
        report.team_a: [1 if match.winner == "A" else 0 for match in report.matches],
        "Draw": [1 if match.winner == "Draw" else 0 for match in report.matches],
        report.team_b: [1 if match.winner == "B" else 0 for match in report.matches],
    }, index=[match.match_date for match in report.matches])
    st.bar_chart(timeline, y_label="Outcome")

    st.subheader("Points comparison")
    points = pd.DataFrame({
        report.team_a: [match.team_a_points for match in report.matches],
        report.team_b: [match.team_b_points for match in report.matches],
    }, index=[match.match_date for match in report.matches])
    st.line_chart(points, y_label="Points")

    st.subheader("Winning margin")
    margins = pd.DataFrame({
        "Margin": [match.margin for match in report.matches]
    }, index=[match.match_date for match in report.matches])
    st.bar_chart(margins, y_label=f"Positive = {report.team_a}; negative = {report.team_b}")

    st.subheader("Average scores")
    _metric_cards([
        (f"{report.team_a} average", f"{report.team_a_points / report.meetings:.1f}"),
        (f"{report.team_b} average", f"{report.team_b_points / report.meetings:.1f}"),
        ("Average combined score", f"{(report.team_a_points + report.team_b_points) / report.meetings:.1f}"),
    ])

    def context(match: Any) -> str:
        """Format a notable meeting for the results table.

        :param match: Qualifying match, when one exists.
        :return: Concise match description.
        """
        if match is None:
            return "No qualifying result"
        return f"{match.match_date} · {match.competition} {match.season} · {match.venue} · {match.home_team} {match.score} {match.away_team}"

    st.subheader("Notable matches")
    st.dataframe(pd.DataFrame([
        {"Highlight": f"Largest {report.team_a} victory", "Match": context(report.largest_team_a_victory)},
        {"Highlight": f"Largest {report.team_b} victory", "Match": context(report.largest_team_b_victory)},
        {"Highlight": "Highest-scoring match", "Match": context(report.highest_scoring)},
    ]), hide_index=True, width="stretch")

    st.subheader("Closest matches")
    if report.closest_matches:
        st.dataframe(pd.DataFrame([{
            "Date": match.match_date, "Home": match.home_team, "Away": match.away_team,
            "Score": match.score, "Margin": abs(match.margin),
            "Three points or fewer": abs(match.margin) <= 3,
        } for match in report.closest_matches]), hide_index=True, width="stretch")
    else:
        st.info("No meetings were decided by one score (seven points) or fewer.")
    st.subheader("Current streak")
    st.write(f"**{report.current_streak}**")


def _render_team_summary(report: TeamSummaryReport) -> None:
    """Render a structured team summary in Streamlit.

    :param report: Calculated report shared with the PDF renderer.
    :return: None.
    """
    # Lead with identity and a ready-to-save standalone report.
    st.header(f"{report.team} — {report.competition} {report.season}")
    st.download_button(
        "Download PDF",
        render_team_summary_pdf(report),
        file_name=team_summary_filename(report),
        mime="application/pdf",
        type="primary",
    )
    st.subheader("Team overview")
    st.write(
        f"**Country:** {report.country}  \n"
        f"**Home venue:** {report.home_venue}  \n"
        f"**Matches played:** {report.played}"
    )

    st.subheader("Season record")
    _metric_cards([
        ("Played", report.played), ("Won", report.won), ("Drawn", report.drawn),
        ("Lost", report.lost), ("Win percentage", f"{report.win_percentage:.1f}%"),
    ])
    if report.league:
        st.subheader("League performance")
        _metric_cards([
            ("Position", report.league["position"]),
            ("Competition points", report.league["competition_points"]),
            ("Points difference", report.league["points_difference"]),
            ("Champion", "Yes" if report.league["champion"] else "No"),
        ])
    else:
        st.info("League standings do not apply or are not configured for this competition.")

    st.subheader("Scoring summary")
    _metric_cards([
        ("Points scored", report.points_for),
        ("Points conceded", report.points_against),
        ("Points difference", report.points_for - report.points_against),
        ("Average scored", f"{report.points_for / report.played:.1f}" if report.played else "0.0"),
        ("Average conceded", f"{report.points_against / report.played:.1f}" if report.played else "0.0"),
    ])
    st.subheader("Try summary")
    if report.tries_for is None or report.tries_against is None:
        st.info("Try totals are unavailable because one or more completed matches lack try data.")
    else:
        _metric_cards([
            ("Tries scored", report.tries_for),
            ("Tries conceded", report.tries_against),
            ("Average scored", f"{report.tries_for / report.played:.1f}" if report.played else "0.0"),
            ("Average conceded", f"{report.tries_against / report.played:.1f}" if report.played else "0.0"),
        ])

    st.subheader("Home and away record")
    st.dataframe(pd.DataFrame([
        {"Location": label, "P": record["played"], "W": record["won"],
         "D": record["drawn"], "L": record["lost"], "PF": record["points_for"],
         "PA": record["points_against"], "PD": record["points_difference"]}
        for label, record in (("Home", report.home_record), ("Away", report.away_record))
    ]), hide_index=True, width="stretch")

    st.subheader("Biggest results")
    notable = [
        ("Largest victory / biggest winning margin", report.largest_victory),
        ("Largest defeat / biggest losing margin", report.largest_defeat),
        ("Highest-scoring match", report.highest_scoring),
        ("Lowest-scoring match", report.lowest_scoring),
    ]
    st.dataframe(pd.DataFrame([
        {"Measure": label, "Match": match.context if match else "No qualifying result"}
        for label, match in notable
    ]), hide_index=True, width="stretch")

    # Charts include text labels and legends so colour is never the only cue.
    st.subheader("Visualisations")
    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.markdown("**Results breakdown**")
        st.bar_chart(pd.DataFrame({"Matches": [report.won, report.drawn, report.lost]}, index=["Wins", "Draws", "Losses"]))
    completed = [match for match in report.matches if match.result != "—"]
    with chart_right:
        st.markdown("**Points by match**")
        if completed:
            points = pd.DataFrame({
                "Points scored": [match.points_for for match in completed],
                "Points conceded": [match.points_against for match in completed],
            }, index=[f"{match.match_date} · {match.opponent}" for match in completed])
            st.line_chart(points)
        else:
            st.info("No completed matches to plot.")

    st.subheader("Match results")
    st.dataframe(pd.DataFrame([{
        "Round": match.round, "Date": match.match_date, "Opponent": match.opponent,
        "Home/Away": match.location, "Venue": match.venue,
        "Points scored": match.points_for, "Points conceded": match.points_against,
        "Score": match.score, "Result": match.result,
    } for match in report.matches]), hide_index=True, width="stretch")


def analysis_page(service: RugbyService) -> None:
    """Render the supporter-focused analysis reports.

    :param service: Business service used to query and calculate reports.
    :return: None.
    """
    st.header("Analysis")
    competition_summary_tab, head_to_head_tab, team_summary_tab = st.tabs(
        ("Competition Summary", "Head-to-Head", "Team Summary")
    )
    competitions = service.list_competitions()

    with competition_summary_tab:
        names = sorted({str(row["name"]) for row in competitions}, key=str.casefold)
        selected_name = st.selectbox(
            "Competition", names, index=None, placeholder="Select a competition",
            key="competition_analysis_competition",
            on_change=_clear_competition_analysis_season,
        )
        seasons = sorted(
            {str(row["season"]) for row in competitions if row["name"] == selected_name},
            reverse=True,
        )
        selected_season = st.selectbox(
            "Year", seasons, index=0 if len(seasons) == 1 else None,
            placeholder="Select a year", disabled=selected_name is None,
            key="competition_analysis_season",
        )
        selected_competition = next((
            row for row in competitions
            if row["name"] == selected_name and str(row["season"]) == selected_season
        ), None)
        if selected_competition:
            try:
                _render_competition_summary(
                    service.competition_summary(int(selected_competition["id"]))
                )
            except ValidationError as error:
                st.warning(str(error))
        elif not competitions:
            st.info("Add a competition and its matches to generate a competition summary.")
        else:
            st.info("Select a competition and year to generate the report.")

    with head_to_head_tab:
        names = sorted({str(row["name"]) for row in competitions}, key=str.casefold)
        selected_name = st.selectbox(
            "Competition", names, index=None, placeholder="Select a competition",
            key="head_to_head_competition", on_change=_clear_head_to_head_selections,
        )
        competition_seasons = sorted(
            [row for row in competitions if row["name"] == selected_name],
            key=lambda row: str(row["season"]), reverse=True,
        )
        season_options = [str(row["season"]) for row in competition_seasons]
        if len(season_options) > 1:
            season_options.insert(0, "All Seasons")
        selected_season = st.selectbox(
            "Year", season_options, index=0 if len(season_options) == 1 else None,
            placeholder="Select a year or All Seasons", disabled=selected_name is None,
            key="head_to_head_season", on_change=_clear_head_to_head_teams,
        )
        selected_competitions = (
            competition_seasons if selected_season == "All Seasons" else
            [row for row in competition_seasons if str(row["season"]) == selected_season]
        )
        selected_ids = [int(row["id"]) for row in selected_competitions]
        matches = [
            match for competition_id in selected_ids
            for match in service.list_matches(competition_id)
        ]
        participating_ids = {
            int(team_id) for match in matches
            for team_id in (match["home_team_id"], match["away_team_id"])
        }
        teams = sorted(
            [row for row in service.list_teams() if int(row["id"]) in participating_ids],
            key=lambda row: str(row["name"]).casefold(),
        )
        team_options = {int(row["id"]): str(row["name"]) for row in teams}
        selectors_enabled = bool(selected_ids)
        if selectors_enabled:
            # Keep the selectors independent so changing either team preserves the
            # other selection and immediately refreshes the report.
            team_a = _select(
                "Team A", team_options, placeholder="Select Team A",
                key="head_to_head_team_a",
            )
            team_b = _select(
                "Team B", team_options, placeholder="Select Team B",
                key="head_to_head_team_b",
            )
        else:
            st.selectbox("Team A", [], index=None, placeholder="Select Team A", disabled=True, key="head_to_head_team_a_disabled")
            st.selectbox("Team B", [], index=None, placeholder="Select Team B", disabled=True, key="head_to_head_team_b_disabled")
            team_a = team_b = None
        if team_a is not None and team_a == team_b:
            st.info("Select two different teams to generate the report.")
        elif selected_ids and team_a is not None and team_b is not None:
            try:
                _render_head_to_head(service.head_to_head(selected_ids, int(team_a), int(team_b)))
            except ValidationError as error:
                st.warning(str(error))
        elif not competitions:
            st.info("Add a competition and its matches to generate a Head-to-Head report.")
        else:
            st.info("Select a competition, year, and two teams to generate the report.")

    with team_summary_tab:
        names = sorted({str(row["name"]) for row in competitions}, key=str.casefold)
        selected_name = st.selectbox(
            "Competition", names, index=None, placeholder="Select a competition",
            key="analysis_competition", on_change=_clear_analysis_season,
        )
        seasons = sorted(
            {str(row["season"]) for row in competitions if row["name"] == selected_name},
            reverse=True,
        )
        season_index = 0 if len(seasons) == 1 else None
        selected_season = st.selectbox(
            "Year", seasons, index=season_index, placeholder="Select a year",
            disabled=selected_name is None, key="analysis_season",
            on_change=_clear_analysis_team,
        )
        selected_competition = next((
            row for row in competitions
            if row["name"] == selected_name and str(row["season"]) == selected_season
        ), None)
        matches = service.list_matches(int(selected_competition["id"])) if selected_competition else []
        participating_ids = {
            int(team_id) for match in matches
            for team_id in (match["home_team_id"], match["away_team_id"])
        }
        teams = sorted(
            [row for row in service.list_teams() if int(row["id"]) in participating_ids],
            key=lambda row: str(row["name"]).casefold(),
        )
        team_options = {int(row["id"]): str(row["name"]) for row in teams}
        selected_team = _select(
            "Team", team_options, placeholder="Select a team", key="analysis_team"
        ) if selected_competition else st.selectbox(
            "Team", [], index=None, placeholder="Select a team", disabled=True,
            key="analysis_team_disabled",
        )
        if selected_competition and selected_team is not None:
            # Only a fully resolved selector chain can generate or export a report.
            report = service.team_summary(int(selected_competition["id"]), int(selected_team))
            _render_team_summary(report)
        elif not competitions:
            st.info("Add a competition and its matches to generate a team summary.")
        else:
            st.info("Select a competition, year, and team to generate the report.")


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
            "Analysis", "League Table", "Matches", "Competitions", "Teams", "Venues", "Referees",
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
            "Analysis": lambda: analysis_page(service),
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
