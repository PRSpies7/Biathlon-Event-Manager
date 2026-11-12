from copy import deepcopy
import pytest
from openpyxl import load_workbook
from services.school_reports import qualified_schools_report
from exporters.selection_reports import build_school_selection_xlsx
from exporters.season_combined import build_combined_season_xlsx
from test_school_reports import school_snapshot


def export_snapshot(school,ages):
    s = school_snapshot(school,ages)
    s.update(awards=[],records=[])
    for a in s["athletes"]:
        a.update(province="GN",team="GN",events_attended=4)
    for r in s["results"]:
        r.update(position="1",running_points="1000",swimming_points="1000",bonus_points="0",province="GN",team="GN",annotations="")
    return s


@pytest.mark.parametrize("school,ages,sheet",[
    ("Example Hs",(15,17,19,15,17,19),"High Schools"),
    ("Example Ps",(9,11,13,15,11,13),"Primary Schools"),
])
@pytest.mark.parametrize("missing",[False,True])
def test_school_status_colours_in_both_downloads(school,ages,sheet,missing):
    s = export_snapshot(school,ages)
    if missing:
        s["results"] = [r for r in s["results"] if r["athlete_id"] != 6]
    for builder in (build_combined_season_xlsx,build_school_selection_xlsx):
        book = load_workbook(builder(s))
        ws = book[sheet]
        headers = {str(c.value).lower():c.column for c in ws[1]}
        assert list(headers)[-3:] == ["team athletes","highest scores","all school athletes"]
        assert book.sheetnames.index("Primary Schools") < book.sheetnames.index("High Schools")
        assert "Athlete" not in str(ws.cell(2,headers["missing events"]).value)
        assert "Athlete" not in str(ws.cell(2,headers["qualification requirements"]).value)
        assert "Athlete" in ws.cell(2,headers["team athletes"]).value
        assert "2,450.00" in ws.cell(2,headers["highest scores"]).value
        for name in ("qualified","full team"):
            cell = ws.cell(2,headers[name])
            assert cell.value == ("No" if missing else "Yes")
            assert cell.fill.fgColor.rgb[-6:] == ("FFC7CE" if missing else "C6EFCE")
            assert cell.font.color.rgb[-6:] == ("9C0006" if missing else "006100")
            assert cell.font.sz == 11
        assert ws.auto_filter.ref == ws.dimensions


def test_high_school_requirements_identify_missing_age_and_extra():
    s = school_snapshot("Example Hs",(15,17,15))
    row = qualified_schools_report(s)[0][0]
    assert "U/19: athlete needed" in row["Qualification requirements"]
    assert "Extra 2: athlete needed" in row["Qualification requirements"]
    assert "Extra 3: athlete needed" in row["Qualification requirements"]
    assert "Extra 1 (U/15" in row["Missing Events"]


def test_school_points_use_best_once_per_selected_athlete():
    s = school_snapshot("Example Hs",(15,17,19,15,17,19))
    expected = sum(max(float(r["total_points"]) for r in s["results"] if r["athlete_id"] == i) for i in range(1,7))
    # Repeated source rows cannot add another school contribution.
    s["results"].extend(deepcopy(s["results"][:4]))
    summary,_,details = qualified_schools_report(s)
    selected = [r for r in details if r["Selected"] == "Yes"]
    assert summary[0]["Total school points"] == expected
    assert len(selected) == len({r["Athlete number"] for r in selected}) == 6
    assert sum(r["School contribution points"] for r in selected) == expected


def test_all_school_athletes_includes_non_team_ages_and_excludes_incomplete():
    s = school_snapshot("Example Ps",(9,11,13,15,11,13,8,8,8))
    # Athlete 7 completed some events but has a higher invalid DNF score.
    for r in s["results"]:
        if r["athlete_id"] == 7 and r["event_id"] == 1:
            r.update(status="DNF",total_points="9999")
        if r["athlete_id"] == 8:
            r.update(status="DNF",total_points="9999")
        if r["athlete_id"] == 9:
            r.update(swim_time="00:00.00",total_points="9999")
    rows,_,_ = qualified_schools_report(s)
    text = rows[0]["All school athletes"]
    assert len(text.splitlines()) == 7
    assert text.count("Athlete 7 (#007)") == 1
    assert "U/8 GIRLS: Athlete 7 (#007) — 1,850.00" in text
    assert "Athlete 8" not in text and "Athlete 9" not in text and "9,999" not in text
    assert "Athlete 7" not in rows[0]["Team athletes"]
    assert rows[0]["Total school points"] == qualified_schools_report(school_snapshot())[0][0]["Total school points"]
