"""Team-focused analysis calculations and PDF rendering."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from rugby_tracker.standings import RULESETS, calculate_competition


@dataclass(frozen=True)
class TeamMatchResult:
    """One fixture represented from the selected team's perspective."""

    round: str
    match_date: str
    opponent: str
    location: str
    venue: str
    points_for: int | None
    points_against: int | None
    tries_for: int | None
    tries_against: int | None
    result: str

    @property
    def score(self) -> str:
        """Format the selected team's score first.

        :return: A score such as ``24–17``, or ``—`` for an unplayed fixture.
        """
        # Keep fixtures visibly distinct from nil scores.
        if self.points_for is None or self.points_against is None:
            return "—"
        return f"{self.points_for}–{self.points_against}"

    @property
    def context(self) -> str:
        """Format concise opponent, location, score, and date context.

        :return: Human-readable match context for notable results.
        """
        # Prefer a recorded round, while retaining a date for chronological context.
        timing = self.match_date
        if self.round != "—":
            timing = f"{timing}, {self.round}"
        return f"{self.opponent} ({self.location}), {self.score} — {timing}"


@dataclass(frozen=True)
class TeamSummaryReport:
    """Structured calculations shared by the UI and PDF export."""

    team_id: int
    team: str
    country: str
    home_venue: str
    competition: str
    season: str
    played: int
    won: int
    drawn: int
    lost: int
    points_for: int
    points_against: int
    tries_for: int | None
    tries_against: int | None
    home_record: dict[str, int]
    away_record: dict[str, int]
    league: dict[str, Any] | None
    largest_victory: TeamMatchResult | None
    largest_defeat: TeamMatchResult | None
    highest_scoring: TeamMatchResult | None
    lowest_scoring: TeamMatchResult | None
    matches: tuple[TeamMatchResult, ...]

    @property
    def win_percentage(self) -> float:
        """Calculate wins as a percentage of completed matches.

        :return: Win percentage, or zero when no results are recorded.
        """
        # Guard empty seasons rather than dividing by zero.
        return self.won / self.played * 100 if self.played else 0.0


@dataclass(frozen=True)
class CompetitionMatchResult:
    """One completed fixture used by the competition summary."""

    round: str
    match_date: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    home_tries: int | None
    away_tries: int | None

    @property
    def score(self) -> str:
        """Format the result with the home score first.

        :return: Formatted home and away score.
        """
        return f"{self.home_score}–{self.away_score}"

    @property
    def total_points(self) -> int:
        """Return combined match points.

        :return: Total points scored by both teams.
        """
        return self.home_score + self.away_score

    @property
    def total_tries(self) -> int | None:
        """Return combined tries, or ``None`` when try data is incomplete.

        :return: Total tries scored by both teams, when available.
        """
        if self.home_tries is None or self.away_tries is None:
            return None
        return self.home_tries + self.away_tries

    @property
    def winning_margin(self) -> int:
        """Return the absolute score difference, with draws represented by zero.

        :return: Non-negative winning margin.
        """
        return abs(self.home_score - self.away_score)

    @property
    def outcome(self) -> str:
        """Return ``Home win``, ``Away win``, or ``Draw``.

        :return: Match outcome label.
        """
        if self.home_score > self.away_score:
            return "Home win"
        if self.away_score > self.home_score:
            return "Away win"
        return "Draw"

    @property
    def context(self) -> str:
        """Format concise teams, score, date, and round context.

        :return: Human-readable match description.
        """
        timing = self.match_date if self.round == "—" else f"{self.match_date}, {self.round}"
        return f"{self.home_team} {self.score} {self.away_team} — {timing}"


@dataclass(frozen=True)
class CompetitionSummaryReport:
    """Structured competition calculations shared by the UI and PDF export."""

    competition_id: int
    competition: str
    season: str
    team_count: int
    scheduled_matches: int
    league_table: tuple[dict[str, Any], ...]
    table_provisional_notes: tuple[str, ...]
    matches: tuple[CompetitionMatchResult, ...]

    @property
    def completed_matches(self) -> int:
        """Return the number of completed fixtures.

        :return: Count of completed fixtures.
        """
        return len(self.matches)

    @property
    def total_points(self) -> int:
        """Return points scored across completed fixtures.

        :return: Competition-wide points total.
        """
        return sum(match.total_points for match in self.matches)

    @property
    def total_tries(self) -> int | None:
        """Return total tries, or ``None`` when any result lacks try data.

        :return: Competition-wide tries total, when available.
        """
        totals = [match.total_tries for match in self.matches]
        return sum(int(total) for total in totals) if all(total is not None for total in totals) else None

    @property
    def home_wins(self) -> int:
        """Return the number of home wins.

        :return: Home-win count.
        """
        return sum(match.outcome == "Home win" for match in self.matches)

    @property
    def away_wins(self) -> int:
        """Return the number of away wins.

        :return: Away-win count.
        """
        return sum(match.outcome == "Away win" for match in self.matches)

    @property
    def draws(self) -> int:
        """Return the number of drawn matches.

        :return: Draw count.
        """
        return sum(match.outcome == "Draw" for match in self.matches)

    @property
    def average_points(self) -> float:
        """Return average combined points per completed match.

        :return: Average match points.
        """
        return self.total_points / self.completed_matches if self.completed_matches else 0.0

    @property
    def average_tries(self) -> float | None:
        """Return average combined tries per completed match, when available.

        :return: Average match tries, or ``None`` for incomplete try data.
        """
        total = self.total_tries
        return total / self.completed_matches if total is not None and self.completed_matches else None

    @property
    def highest_scoring(self) -> CompetitionMatchResult | None:
        """Return the first highest-scoring match.

        :return: Highest-scoring match, or ``None`` without results.
        """
        return max(self.matches, key=lambda match: match.total_points, default=None)

    @property
    def lowest_scoring(self) -> CompetitionMatchResult | None:
        """Return the first lowest-scoring match.

        :return: Lowest-scoring match, or ``None`` without results.
        """
        return min(self.matches, key=lambda match: match.total_points, default=None)

    @property
    def largest_margin(self) -> CompetitionMatchResult | None:
        """Return the first match with the largest winning margin.

        :return: Largest-margin match, or ``None`` without results.
        """
        return max(self.matches, key=lambda match: match.winning_margin, default=None)


def _location_record(matches: list[TeamMatchResult], location: str) -> dict[str, int]:
    """Aggregate completed matches for one stored home/away designation.

    :param matches: Team-perspective fixtures and results.
    :param location: ``Home`` or ``Away`` designation to include.
    :return: Played, result, and scoring totals for that location.
    """
    # Unplayed fixtures remain in the match list but never affect performance totals.
    completed = [match for match in matches if match.location == location and match.result != "—"]
    points_for = sum(int(match.points_for or 0) for match in completed)
    points_against = sum(int(match.points_against or 0) for match in completed)
    return {
        "played": len(completed),
        "won": sum(match.result == "W" for match in completed),
        "drawn": sum(match.result == "D" for match in completed),
        "lost": sum(match.result == "L" for match in completed),
        "points_for": points_for,
        "points_against": points_against,
        "points_difference": points_for - points_against,
    }


def build_team_summary(
    competition: dict[str, Any], team: dict[str, Any], matches: list[dict[str, Any]]
) -> TeamSummaryReport:
    """Calculate a complete team summary from enriched database rows.

    :param competition: Selected competition record.
    :param team: Selected enriched team record.
    :param matches: Enriched matches for the selected competition.
    :return: Structured team summary ready for presentation or export.
    """
    # Convert every participating fixture into the selected team's perspective.
    team_id = int(team["id"])
    team_matches: list[TeamMatchResult] = []
    for match in matches:
        is_home = int(match["home_team_id"]) == team_id
        if not is_home and int(match["away_team_id"]) != team_id:
            continue
        points_for = match["home_score"] if is_home else match["away_score"]
        points_against = match["away_score"] if is_home else match["home_score"]
        tries_for = match["home_tries"] if is_home else match["away_tries"]
        tries_against = match["away_tries"] if is_home else match["home_tries"]
        result = "—"
        if points_for is not None and points_against is not None:
            result = "W" if points_for > points_against else "L" if points_for < points_against else "D"
        team_matches.append(TeamMatchResult(
            round=str(match.get("round") or "—"),
            match_date=str(match["match_date"]),
            opponent=str(match["away_team_name"] if is_home else match["home_team_name"]),
            location="Home" if is_home else "Away",
            venue=str(match.get("venue_name") or "Not recorded"),
            points_for=int(points_for) if points_for is not None else None,
            points_against=int(points_against) if points_against is not None else None,
            tries_for=int(tries_for) if tries_for is not None else None,
            tries_against=int(tries_against) if tries_against is not None else None,
            result=result,
        ))

    # Base all performance calculations only on completed results.
    completed = [match for match in team_matches if match.result != "—"]
    victories = [match for match in completed if match.result == "W"]
    defeats = [match for match in completed if match.result == "L"]
    tries_complete = all(
        match.tries_for is not None and match.tries_against is not None for match in completed
    )
    league = None
    ruleset = competition.get("ruleset")
    if ruleset in RULESETS:
        # Reuse the application's ruleset logic, including knockout-round exclusions.
        calculation = calculate_competition(matches, str(ruleset))
        row = next((row for row in calculation["table"] if row["Team"] == team["name"]), None)
        if row is not None:
            champions = calculation["awards"].get("Champion", ())
            league = {
                "position": row["Pos"],
                "competition_points": row["Pts"],
                "points_difference": row["PD"],
                "champion": team["name"] in champions,
            }

    # Deterministic tie-breaking preserves chronological database order.
    margin = lambda match: int(match.points_for or 0) - int(match.points_against or 0)
    combined = lambda match: int(match.points_for or 0) + int(match.points_against or 0)
    return TeamSummaryReport(
        team_id=team_id,
        team=str(team["name"]),
        country=str(team.get("country") or "Not recorded"),
        home_venue=str(team.get("home_venue") or "Not recorded"),
        competition=str(competition["name"]),
        season=str(competition["season"]),
        played=len(completed),
        won=sum(match.result == "W" for match in completed),
        drawn=sum(match.result == "D" for match in completed),
        lost=sum(match.result == "L" for match in completed),
        points_for=sum(int(match.points_for or 0) for match in completed),
        points_against=sum(int(match.points_against or 0) for match in completed),
        tries_for=sum(int(match.tries_for or 0) for match in completed) if tries_complete else None,
        tries_against=sum(int(match.tries_against or 0) for match in completed) if tries_complete else None,
        home_record=_location_record(team_matches, "Home"),
        away_record=_location_record(team_matches, "Away"),
        league=league,
        largest_victory=max(victories, key=margin, default=None),
        largest_defeat=min(defeats, key=margin, default=None),
        highest_scoring=max(completed, key=combined, default=None),
        lowest_scoring=min(completed, key=combined, default=None),
        matches=tuple(team_matches),
    )


def build_competition_summary(
    competition: dict[str, Any], matches: list[dict[str, Any]]
) -> CompetitionSummaryReport:
    """Calculate a competition-wide summary from enriched fixture rows.

    :param competition: Selected competition-season record.
    :param matches: Enriched scheduled and completed fixtures.
    :return: Structured competition summary ready for presentation or export.
    """
    ruleset = competition.get("ruleset")
    if ruleset not in RULESETS:
        raise ValueError("Select a league-table ruleset for this competition first.")

    team_ids = {
        int(team_id)
        for match in matches
        for team_id in (match["home_team_id"], match["away_team_id"])
    }
    completed: list[CompetitionMatchResult] = []
    for match in matches:
        if match["home_score"] is None or match["away_score"] is None:
            continue
        completed.append(CompetitionMatchResult(
            round=str(match.get("round") or "—"),
            match_date=str(match["match_date"]),
            home_team=str(match["home_team_name"]),
            away_team=str(match["away_team_name"]),
            home_score=int(match["home_score"]),
            away_score=int(match["away_score"]),
            home_tries=int(match["home_tries"]) if match["home_tries"] is not None else None,
            away_tries=int(match["away_tries"]) if match["away_tries"] is not None else None,
        ))

    calculation = calculate_competition(matches, str(ruleset))
    return CompetitionSummaryReport(
        competition_id=int(competition["id"]),
        competition=str(competition["name"]),
        season=str(competition["season"]),
        team_count=len(team_ids),
        scheduled_matches=len(matches),
        league_table=tuple(calculation["table"]),
        table_provisional_notes=tuple(calculation["validation_errors"]),
        matches=tuple(completed),
    )


def competition_team_rankings(report: CompetitionSummaryReport) -> list[dict[str, Any]]:
    """Return the leading team or teams for each supporter-focused measure.

    :param report: Calculated competition summary.
    :return: Ranking labels, leaders, and values.
    """
    specifications = (
        ("Most competition points", "Pts", max),
        ("Most points scored", "PF", max),
        ("Best defence", "PA", min),
        ("Most tries scored", "TF", max),
        ("Fewest tries conceded", "TA", min),
    )
    rankings: list[dict[str, Any]] = []
    for category, field, selector in specifications:
        if not report.league_table:
            continue
        value = selector(int(row[field]) for row in report.league_table)
        leaders = sorted(
            (str(row["Team"]) for row in report.league_table if int(row[field]) == value),
            key=str.casefold,
        )
        rankings.append({"Category": category, "Leader": ", ".join(leaders), "Value": value})
    return rankings


def competition_round_summary(report: CompetitionSummaryReport) -> list[dict[str, Any]]:
    """Aggregate completed fixtures by their first chronological round occurrence.

    :param report: Calculated competition summary.
    :return: Ordered round-level match, try, and point totals.
    """
    rounds: dict[str, dict[str, Any]] = {}
    for match in report.matches:
        row = rounds.setdefault(match.round, {
            "Round": match.round, "Matches": 0, "Total tries": 0,
            "Total points": 0, "try_data_complete": True,
        })
        row["Matches"] += 1
        row["Total points"] += match.total_points
        if match.total_tries is None:
            row["try_data_complete"] = False
        else:
            row["Total tries"] += match.total_tries
    return [{
        "Round": row["Round"],
        "Matches": row["Matches"],
        "Total tries": row["Total tries"] if row["try_data_complete"] else None,
        "Total points": row["Total points"],
        "Average points": row["Total points"] / row["Matches"],
    } for row in rounds.values()]


def competition_summary_filename(report: CompetitionSummaryReport) -> str:
    """Create a predictable filesystem-safe Competition Summary PDF filename.

    :param report: Competition summary whose identity belongs in the filename.
    :return: Normalised filename ending in ``.pdf``.
    """
    parts = [report.competition, report.season]
    slug = "_".join(re.sub(r"[^a-z0-9]+", "-", part.casefold()).strip("-") for part in parts)
    return f"competition-summary_{slug}.pdf"


def team_summary_filename(report: TeamSummaryReport) -> str:
    """Create a predictable filesystem-safe PDF filename.

    :param report: Team summary whose identity belongs in the filename.
    :return: Normalised filename ending in ``.pdf``.
    """
    # Collapse punctuation and whitespace into readable hyphen separators.
    parts = [report.team, report.competition, report.season]
    slug = "_".join(re.sub(r"[^a-z0-9]+", "-", part.casefold()).strip("-") for part in parts)
    return f"team-summary_{slug}.pdf"


def render_team_summary_pdf(report: TeamSummaryReport) -> bytes:
    """Render a team summary as a paginated A4 PDF.

    :param report: Structured report to render.
    :return: Complete PDF document bytes.
    """
    # Build the PDF entirely from report data so it remains independent of Streamlit.
    output = io.BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], alignment=TA_CENTER, textColor=colors.HexColor("#17365d")))
    document = SimpleDocTemplate(output, pagesize=A4, rightMargin=14 * mm, leftMargin=14 * mm, topMargin=15 * mm, bottomMargin=15 * mm)
    story: list[Any] = [
        Paragraph("Team Summary", styles["ReportTitle"]),
        Paragraph(f"{report.team} · {report.competition} · {report.season}", styles["Heading2"]),
        Paragraph(f"Generated {date.today().strftime('%d %B %Y')}", styles["Normal"]),
        Spacer(1, 5 * mm),
    ]

    def section(title: str, rows: list[list[Any]]) -> None:
        """Append a compact labelled table section.

        :param title: Section heading.
        :param rows: Two-dimensional display values.
        :return: None.
        """
        # Keep short sections together and repeat headings for longer tables.
        table = Table(rows, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9eaf7")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        content = [Paragraph(title, styles["Heading2"]), table, Spacer(1, 4 * mm)]
        story.extend([KeepTogether(content)] if len(rows) <= 8 else content)

    section("Team overview", [["Team", "Competition", "Season", "Country", "Home venue", "Matches"], [report.team, report.competition, report.season, report.country, report.home_venue, report.played]])
    section("Season record", [["Played", "Won", "Drawn", "Lost", "Win %"], [report.played, report.won, report.drawn, report.lost, f"{report.win_percentage:.1f}%"]])
    if report.league:
        section("League performance", [["Position", "Competition points", "Points difference", "Champion"], [report.league["position"], report.league["competition_points"], report.league["points_difference"], "Yes" if report.league["champion"] else "No"]])
    section("Scoring and tries", [["Points for", "Points against", "Difference", "Avg for", "Avg against", "Tries for", "Tries against"], [report.points_for, report.points_against, report.points_for - report.points_against, f"{report.points_for / report.played:.1f}" if report.played else "0.0", f"{report.points_against / report.played:.1f}" if report.played else "0.0", report.tries_for if report.tries_for is not None else "Unavailable", report.tries_against if report.tries_against is not None else "Unavailable"]])
    section("Home and away", [["Location", "P", "W", "D", "L", "PF", "PA", "PD"], *[[label, record["played"], record["won"], record["drawn"], record["lost"], record["points_for"], record["points_against"], record["points_difference"]] for label, record in (("Home", report.home_record), ("Away", report.away_record))]])
    section("Biggest results", [["Measure", "Match"], ["Largest victory", report.largest_victory.context if report.largest_victory else "No qualifying result"], ["Largest defeat", report.largest_defeat.context if report.largest_defeat else "No qualifying result"], ["Highest-scoring match", report.highest_scoring.context if report.highest_scoring else "No completed match"], ["Lowest-scoring match", report.lowest_scoring.context if report.lowest_scoring else "No completed match"]])
    story.extend([PageBreak(), Paragraph("Visualisations", styles["Heading2"])])
    results_chart = Drawing(170 * mm, 55 * mm)
    results_chart.add(String(0, 48 * mm, "Results breakdown", fontName="Helvetica-Bold", fontSize=11))
    bars = VerticalBarChart()
    bars.x, bars.y, bars.width, bars.height = 15 * mm, 8 * mm, 130 * mm, 35 * mm
    bars.data = [[report.won, report.drawn, report.lost]]
    bars.categoryAxis.categoryNames = ["Wins", "Draws", "Losses"]
    bars.valueAxis.valueMin = 0
    bars.valueAxis.valueMax = max(report.won, report.drawn, report.lost, 1)
    bars.valueAxis.valueStep = 1
    bars.bars[0].fillColor = colors.HexColor("#4472c4")
    results_chart.add(bars)
    story.extend([results_chart, Spacer(1, 4 * mm)])
    completed = [match for match in report.matches if match.result != "—"]
    if completed:
        # Plot match sequence to keep long and inconsistent round labels readable.
        points_chart = Drawing(170 * mm, 78 * mm)
        points_chart.add(String(0, 71 * mm, "Points by match", fontName="Helvetica-Bold", fontSize=11))
        lines = HorizontalLineChart()
        lines.x, lines.y, lines.width, lines.height = 15 * mm, 30 * mm, 140 * mm, 34 * mm
        lines.data = [
            [int(match.points_for or 0) for match in completed],
            [int(match.points_against or 0) for match in completed],
        ]
        lines.categoryAxis.categoryNames = [str(index) for index in range(1, len(completed) + 1)]
        lines.lines[0].strokeColor = colors.HexColor("#4472c4")
        lines.lines[1].strokeColor = colors.HexColor("#c55a11")
        points_chart.add(lines)
        points_chart.add(String(
            85 * mm, 20 * mm, "Match sequence", fontSize=8, textAnchor="middle"
        ))
        legend = Legend()
        legend.x, legend.y = 48 * mm, 9 * mm
        legend.boxAnchor = "w"
        legend.dx = 5 * mm
        legend.dy = 2.5 * mm
        legend.deltax = 42 * mm
        legend.fontName = "Helvetica"
        legend.fontSize = 8
        legend.colorNamePairs = [
            (colors.HexColor("#4472c4"), "Points scored"),
            (colors.HexColor("#c55a11"), "Points conceded"),
        ]
        points_chart.add(legend)
        story.extend([points_chart, Spacer(1, 4 * mm)])
    section("Points by match", [["Date", "Opponent", "For", "Against"], *[[match.match_date, match.opponent, match.points_for, match.points_against] for match in completed]])
    section("Match results", [["Round", "Date", "Opponent", "H/A", "Venue", "PF", "PA", "Score", "Result"], *[[match.round, match.match_date, match.opponent, match.location[0], match.venue, match.points_for if match.points_for is not None else "—", match.points_against if match.points_against is not None else "—", match.score, match.result] for match in report.matches]])

    def add_page_number(canvas: Any, doc: Any) -> None:
        """Draw the current page number in the footer.

        :param canvas: ReportLab canvas for the current page.
        :param doc: Active ReportLab document template.
        :return: None.
        """
        # Place numbering outside the main content frame.
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[0] - 14 * mm, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    return output.getvalue()


def render_competition_summary_pdf(report: CompetitionSummaryReport) -> bytes:
    """Render a competition summary as a paginated A4 PDF.

    :param report: Structured report to render.
    :return: Complete PDF document bytes.
    """
    output = io.BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="CompetitionReportTitle", parent=styles["Title"], alignment=TA_CENTER,
        textColor=colors.HexColor("#17365d"),
    ))
    document = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=14 * mm, leftMargin=14 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
    )
    story: list[Any] = [
        Paragraph("Competition Summary", styles["CompetitionReportTitle"]),
        Paragraph(f"{report.competition} · {report.season}", styles["Heading2"]),
        Paragraph(f"Generated {date.today().strftime('%d %B %Y')}", styles["Normal"]),
        Spacer(1, 5 * mm),
    ]

    def section(title: str, rows: list[list[Any]], keep: bool = True) -> None:
        """Append a consistently styled table section.

        :param title: Section heading.
        :param rows: Two-dimensional display values.
        :param keep: Whether to keep short content together on one page.
        :return: None.
        """
        table = Table(rows, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9eaf7")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ]))
        content = [Paragraph(title, styles["Heading2"]), table, Spacer(1, 4 * mm)]
        story.extend([KeepTogether(content)] if keep and len(rows) <= 8 else content)

    total_tries = report.total_tries if report.total_tries is not None else "Unavailable"
    section("Competition overview", [
        ["Competition", "Season", "Teams", "Completed", "Scheduled", "Total tries", "Total points"],
        [report.competition, report.season, report.team_count, report.completed_matches,
         report.scheduled_matches, total_tries, report.total_points],
    ])
    section("Competition statistics", [
        ["Average points", "Average tries", "Home wins", "Away wins", "Draws"],
        [f"{report.average_points:.1f}", f"{report.average_tries:.1f}" if report.average_tries is not None else "Unavailable",
         report.home_wins, report.away_wins, report.draws],
    ])
    section("Final league table", [
        ["Pos", "Team", "P", "W", "D", "L", "PF", "PA", "PD", "Pts"],
        *[[row[key] for key in ("Pos", "Team", "P", "W", "D", "L", "PF", "PA", "PD", "Pts")]
          for row in report.league_table],
    ], keep=False)
    section("Team rankings", [
        ["Category", "Leader", "Value"],
        *[[row["Category"], row["Leader"], row["Value"]] for row in competition_team_rankings(report)],
    ])

    story.extend([PageBreak(), Paragraph("Match patterns", styles["Heading2"])])
    if report.completed_matches:
        outcome_chart = Drawing(170 * mm, 55 * mm)
        outcome_chart.add(String(0, 48 * mm, "Home and away performance", fontName="Helvetica-Bold", fontSize=11))
        bars = VerticalBarChart()
        bars.x, bars.y, bars.width, bars.height = 15 * mm, 8 * mm, 130 * mm, 35 * mm
        bars.data = [[report.home_wins, report.away_wins, report.draws]]
        bars.categoryAxis.categoryNames = ["Home wins", "Away wins", "Draws"]
        bars.valueAxis.valueMin = 0
        bars.valueAxis.valueMax = max(report.home_wins, report.away_wins, report.draws, 1)
        bars.valueAxis.valueStep = 1
        bars.bars[0].fillColor = colors.HexColor("#4472c4")
        outcome_chart.add(bars)
        story.extend([outcome_chart, Spacer(1, 4 * mm)])

    rounds = competition_round_summary(report)
    if rounds:
        round_chart = Drawing(170 * mm, 72 * mm)
        round_chart.add(String(0, 65 * mm, "Average points by round", fontName="Helvetica-Bold", fontSize=11))
        lines = HorizontalLineChart()
        lines.x, lines.y, lines.width, lines.height = 15 * mm, 22 * mm, 140 * mm, 35 * mm
        lines.data = [[row["Average points"] for row in rounds]]
        lines.categoryAxis.categoryNames = [str(row["Round"]) for row in rounds]
        lines.lines[0].strokeColor = colors.HexColor("#4472c4")
        round_chart.add(lines)
        story.extend([round_chart, Spacer(1, 4 * mm)])
    section("Results by round", [
        ["Round", "Matches", "Total tries", "Total points", "Average points"],
        *[[row["Round"], row["Matches"], row["Total tries"] if row["Total tries"] is not None else "Unavailable",
           row["Total points"], f"{row['Average points']:.1f}"] for row in rounds],
    ], keep=False)

    ordered_high = sorted(report.matches, key=lambda match: (-match.total_points, match.match_date))[:10]
    ordered_close = sorted(report.matches, key=lambda match: (match.winning_margin, match.match_date))[:10]
    story.extend([PageBreak()])
    section("Highest-scoring matches", [
        ["Date", "Round", "Home", "Away", "Score", "Total"],
        *[[match.match_date, match.round, match.home_team, match.away_team, match.score, match.total_points]
          for match in ordered_high],
    ], keep=False)
    section("Closest matches", [
        ["Date", "Home", "Away", "Score", "Margin"],
        *[[match.match_date, match.home_team, match.away_team, match.score, match.winning_margin]
          for match in ordered_close],
    ], keep=False)

    def add_page_number(canvas: Any, doc: Any) -> None:
        """Draw the current page number in the footer.

        :param canvas: ReportLab canvas for the current page.
        :param doc: Active ReportLab document template.
        :return: None.
        """
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[0] - 14 * mm, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    return output.getvalue()
