from io import BytesIO
import openpyxl
import pytest

from parsers.season_records import record_category_key, parse_record_benchmarks
from services.season_reports import record_comparison_rows


@pytest.mark.parametrize("left,right", [
    ("Girls Under 11", "U/11 FEMALE"), ("BOYS U-09", "Under 9 Male"),
    ("Women Junior", "JNR WOMEN"), ("Senior Male", "SENIORS MEN"),
    ("Women Masters 40+", "MASTER 40 FEMALE"), ("U 13 (Girls)", "GIRLS U/13"),
])
def test_equivalent_record_categories(left, right):
    assert record_category_key(left) == record_category_key(right)


def test_categories_do_not_cross_age_or_sex():
    assert len({record_category_key(c) for c in ("Girls Under 11", "Boys Under 11", "Girls Under 13")}) == 3


def test_only_age_group_and_points_are_required():
    workbook = openpyxl.Workbook()
    workbook.active.append(["Age group", "Record points"])
    workbook.active.append(["Girls Under 11", 2000])
    stream = BytesIO()
    workbook.save(stream)
    records = parse_record_benchmarks(stream)
    assert records[0]["athlete_number"] == ""
    result = {"category": "U/11 FEMALE", "athlete_number": "123", "athlete_name": "Example",
              "event_name": "League 1", "event_date": "2026-08-25", "total_points": "2000",
              "run_time": "", "swim_time": "", "school": "Example Ps"}
    snapshot = {"records": records, "athletes": [], "results": [result]}
    assert record_comparison_rows(snapshot)[0]["Record comparison"] == "Equalled"
    result["total_points"] = "2001"
    assert record_comparison_rows(snapshot)[0]["Record comparison"] == "Exceeded"
    result["category"] = "U/11 BOYS"
    assert not record_comparison_rows(snapshot)


def test_record_preview_compares_before_save(tmp_path, monkeypatch):
    from test_season_results_ui import app_test
    from test_season_results import sample_event
    from database.season_repository import store_event, season_snapshot
    from parsers.season_records import validate_record_benchmarks
    app = app_test(tmp_path, monkeypatch)
    app.radio(key="app_module").set_value("Season Results Database").run()
    db = tmp_path / "data" / "season_results.sqlite"
    store_event(db, sample_event())
    app.session_state.season_records_preview = {"source": "records.xlsx", "records": validate_record_benchmarks([
        {"category": "Girls Under 11", "total_points": "2000"}])}
    app.radio(key="season_view").set_value("Reports").run()
    assert not app.exception
    assert any("Record comparison" in d.value.columns for d in app.dataframe)
    assert not any("Supply current category records to enable" in i.value for i in app.info)
    assert not season_snapshot(db)["records"]
    app.button(key="season_records_save").click().run()
    assert not app.exception
    assert season_snapshot(db)["records"][0]["athlete_number"] == ""
