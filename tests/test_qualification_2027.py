from copy import deepcopy
import pytest
from openpyxl import load_workbook
from database.season_db import init_season_db
from services.season_reports import qualification_rows, compact_qualification_requirements
from exporters.season_combined import build_combined_season_xlsx
from test_season_reports import add_events
from services.school_reports import school_attendance


@pytest.mark.parametrize("category,leagues,ip,expected",[
    ("U/08 GIRLS",3,1,"Yes"),("U/19 BOYS",3,1,"Yes"),
    ("U/11 GIRLS",2,2,"Yes"),("U/19 BOYS",1,3,"Yes"),
    ("U/09 BOYS",4,0,"No"),("U/13 GIRLS",2,1,"No"),("JNR WOMEN",2,1,"Yes"),
    ("SENIORS MEN",1,2,"Yes"),("MASTERS 80+ WOMEN",2,1,"Yes"),
])
def test_2027_total_events_allow_extra_ip_or_champs(tmp_path,category,leagues,ip,expected):
    db = tmp_path/"season.sqlite"; init_season_db(db)
    snapshot = add_events(db,category,leagues,ip)
    snapshot["season_year"] = 2027
    for r in snapshot["results"]: r["season_year"] = 2027
    q = qualification_rows(snapshot)[0]
    assert q["Qualified"] == expected
    if expected == "No":
        assert "completed event" in q["Missing to qualify"] if ip else "interprovincial" in q["Missing to qualify"]
    book = load_workbook(build_combined_season_xlsx(snapshot))
    header = [c.value for c in book["Summary"][3]]
    assert header[-2:] == ["Qualification Status","Qualification requirements"]
    row = list(book["Summary"].values)[3]
    assert row[-2] == ("Qualified" if expected == "Yes" else "Not qualified")
    assert row[-1] == compact_qualification_requirements(q["Missing to qualify"])
    assert book["Summary"].column_dimensions[book["Summary"].cell(3,len(header)-1).column_letter].width == 19


def test_championship_does_not_also_count_as_league(tmp_path):
    db = tmp_path/"season.sqlite"; init_season_db(db)
    snapshot = add_events(db,"U/11 GIRLS",leagues=3,interprovincials=1)
    snapshot["season_year"] = 2027
    for r in snapshot["results"]: r["season_year"] = 2027
    # Exact requested case: two leagues, one championship, one IP.
    snapshot["results"][0]["event_name"] = "GN Championships"
    assert qualification_rows(snapshot)[0]["Qualified"] == "Yes"
    snapshot["results"][-1]["event_name"] = "GN Championships"
    assert qualification_rows(snapshot)[0]["Qualified"] == "Yes"
    # Reclassifying one league as a championship leaves only two leagues.
    snapshot["results"][0]["event_name"] = "GN Championships"
    q = qualification_rows(snapshot)[0]
    assert q["Qualified"] == "Yes"
    assert q["Missing to qualify"] == "None"
    assert school_attendance(snapshot["results"])[2] == ""
    # One championship cannot fill two places: only three distinct meets fail.
    fewer = deepcopy(snapshot)
    fewer["results"] = fewer["results"][:3]
    assert qualification_rows(fewer)[0]["Qualified"] == "No"
    historical = deepcopy(snapshot)
    historical["season_year"] = 2026
    for r in historical["results"]: r["season_year"] = 2026
    assert qualification_rows(historical)[0]["Qualified"] == "Yes"


def test_2027_preserves_special_needs_and_score_requirements(tmp_path):
    db = tmp_path/"season.sqlite"; init_season_db(db)
    snapshot = add_events(db,"SPECIAL NEEDS MALE",leagues=2,interprovincials=2)
    snapshot["season_year"] = 2027
    assert qualification_rows(snapshot)[0]["Qualified"] == "Yes"
    for r in snapshot["results"]: r["total_points"] = "1800"
    q = qualification_rows(snapshot)[0]
    assert q["Qualified"] == "No"
    assert "1890" in q["Missing to qualify"]
