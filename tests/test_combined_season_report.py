from dataclasses import replace
from datetime import date
from openpyxl import load_workbook
from database.season_db import init_season_db
from database.season_repository import store_event, season_snapshot
from exporters.season_combined import build_combined_season_xlsx, report_date
from test_season_results import sample_event


def test_combined_tabs_event_order_awards_and_date(tmp_path):
    db = tmp_path / "season.sqlite"
    init_season_db(db)
    base = sample_event()
    for number in (10,2):
        store_event(db,replace(base,name=f"GN League {number}",event_date=date(2026,9,number)))
    book = load_workbook(build_combined_season_xlsx(season_snapshot(db)))
    assert book.sheetnames == ["Summary","All Results","Primary Schools","High Schools"]
    assert report_date().isoformat() in book["Summary"]["A1"].value
    assert book["Summary"].freeze_panes == "F4"
    rows = list(book["All Results"].values)
    assert rows[1][0] == "GN League 2"
    assert rows[1][-3:] == ("1","2","Junior Victrix")
    assert isinstance(rows[1][13],(int,float))
    assert "Qualified" in [c.value for c in book["High Schools"][1]] or "QUALIFIED" in [c.value for c in book["High Schools"][1]]


def test_victor_bands_exclude_special_needs_and_preserve_ties(tmp_path):
    db = tmp_path / "season.sqlite"
    init_season_db(db)
    event = sample_event()
    result = event.results[0]
    event.results = [replace(result,athlete_number=str(i),athlete_name=f"Athlete {i}",category=category,school="Example Hs")
                     for i,category in enumerate(("U/08 BOYS","U/19 GIRLS","SENIOR MEN","MASTERS 40+ WOMEN","SPECIAL NEEDS GIRLS","U/13 BOYS"),1)]
    event.awards = []
    store_event(db,event)
    book = load_workbook(build_combined_season_xlsx(season_snapshot(db)))
    awards = {r[4]:r[-1] for r in list(book["All Results"].values)[1:]}
    assert awards == {"1":"Junior Victor","2":"Junior Victrix","3":"Senior Victor","4":"Senior Victrix","5":None,"6":"Junior Victor"}


def test_unreadable_published_position_does_not_break_report(tmp_path):
    db = tmp_path / "season.sqlite"
    init_season_db(db)
    event = sample_event()
    event.results[0].position = "unreadable PDF position"
    store_event(db,event)
    book = load_workbook(build_combined_season_xlsx(season_snapshot(db)))
    rows = list(book["All Results"].values)[1:]
    assert next(r[3] for r in rows if r[4] == "00101") is None
    assert next(r[3] for r in rows if r[4] == "102") == 2


def test_clean_format_and_contiguous_filters(tmp_path):
    from openpyxl.utils import get_column_letter
    db = tmp_path / "season.sqlite"
    init_season_db(db)
    store_event(db,sample_event())
    book = load_workbook(build_combined_season_xlsx(season_snapshot(db)))
    for sheet in book:
        header = 3 if sheet.title == "Summary" else 1
        assert sheet.auto_filter.ref == f"A{header}:{get_column_letter(sheet.max_column)}{sheet.max_row}"
        assert not any(r.min_row > header for r in sheet.merged_cells.ranges)
        assert sheet.cell(header,1).font.name == "Calibri"
        assert sheet.cell(header,1).font.sz == 11
        assert sheet.freeze_panes
        assert all(sheet.cell(i,1).value is not None for i in range(header+1,sheet.max_row+1))
    summary = book["Summary"]
    assert summary.max_row == 5  # title, spacing, header, two athlete rows
    assert {summary.row_dimensions[i].height for i in range(4,6)} == {32}
