from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from database.season_db import init_season_db
from database.season_repository import store_event, season_snapshot
from exporters.selection_reports import (build_athlete_selection_xlsx, build_school_selection_xlsx,
    build_ranked_athletes_xlsx, build_affiliation_xlsx)
from test_season_results import sample_event


def test_focused_reports_have_only_distinct_tabs_and_filters(tmp_path):
    db = tmp_path / "season.sqlite"
    init_season_db(db)
    store_event(db,sample_event())
    snapshot = season_snapshot(db)
    for builder,tabs in (
        (build_athlete_selection_xlsx,["Athlete Qualification"]),
        (build_school_selection_xlsx,["Primary Schools","High Schools","School Athlete Scores"]),
        (build_ranked_athletes_xlsx,["Ranked Athletes","Event Details"]),
        (build_affiliation_xlsx,["Affiliated Athletes","Affiliation Follow-up"]),
    ):
        book = load_workbook(builder(snapshot))
        assert book.sheetnames == tabs
        for sheet in book:
            assert sheet.auto_filter.ref == f"A1:{get_column_letter(sheet.max_column)}{sheet.max_row}"
            assert sheet.freeze_panes == "C2"
            assert not sheet.merged_cells.ranges
            assert sheet.cell(1,1).font.name == "Calibri"
            assert sheet.cell(1,1).font.sz == 11
    book = load_workbook(build_athlete_selection_xlsx(snapshot))
    headers = [c.value for c in book.active[1]]
    assert "Qualified" in headers and "Missing to qualify" in headers
    assert book.active.max_row == 3
    assert "Event id" not in [c.value for c in load_workbook(build_ranked_athletes_xlsx(snapshot))["Event Details"][1]]


def test_empty_reports_still_have_filterable_headers():
    snapshot = {"athletes":[],"events":[],"results":[],"awards":[],"records":[]}
    for builder in (build_athlete_selection_xlsx,build_school_selection_xlsx,build_ranked_athletes_xlsx,build_affiliation_xlsx):
        book = load_workbook(builder(snapshot))
        assert all(s.max_row == 1 and s.auto_filter.ref for s in book)
