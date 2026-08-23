from pathlib import Path

from database.db import init_db
from database.repository import create_event, get_athletes, replace_athletes, save_run_positions
from parsers.master_entries import parse_master_entries
from parsers.run_results_excel import parse_run_results_excel
from parsers.swim_results import parse_swim_results
from services.results_service import process_run_results, process_swim_results
from validation.validators import normalize_time

BASE = Path(__file__).resolve().parents[1]


def test_v12_time_normalization_variants():
    assert normalize_time("01.01.20") == "01:01.20"
    assert normalize_time("01,01,20") == "01:01.20"
    assert normalize_time("01;01;20") == "01:01.20"
    assert normalize_time("1:05.20") == "01:05.20"


def test_v12_run_processing_is_heat_aware_and_persists(tmp_path):
    parsed = parse_master_entries(BASE / "data" / "Master Entries Excel.xlsx")
    db = tmp_path / "event.sqlite"
    init_db(db)
    event_id = create_event(str(db), "Test", "GN", "2026-08-14", "LCM", 8)
    replace_athletes(str(db), event_id, parsed["athletes"])

    athletes = get_athletes(str(db), event_id)
    # Create the Phase 2 mapping required for every heat in the supplied run file.
    for heat in parsed["running_heats"]:
        group = [a for a in athletes if a.get("running_heat") == heat]
        save_run_positions(str(db), event_id, [heat], {a["athlete_number"]: i + 1 for i, a in enumerate(group)})

    run_data = parse_run_results_excel(BASE / "data" / "Run Results LG4.xlsx")
    result = process_run_results(str(db), event_id, run_data)

    assert result["saved"] is True
    assert result["matched_count"] > 0
    assert any("missing heat section(s): 12" in w for w in result["warnings"])

    persisted = get_athletes(str(db), event_id)
    assert sum(bool(a.get("run_time")) for a in persisted) == result["matched_count"]


def test_v12_swim_processing_is_independent(tmp_path):
    parsed = parse_master_entries(BASE / "data" / "Master Entries Excel.xlsx")
    db = tmp_path / "event.sqlite"
    init_db(db)
    event_id = create_event(str(db), "Test", "GN", "2026-08-14", "LCM", 8)
    replace_athletes(str(db), event_id, parsed["athletes"])

    swim_data = parse_swim_results(BASE / "data" / "Swim TXT file.txt")
    result = process_swim_results(str(db), event_id, swim_data)

    assert result["saved"] is True
    assert result["matched_count"] > 0
    persisted = get_athletes(str(db), event_id)
    assert sum(bool(a.get("swim_time")) for a in persisted) == result["matched_count"]


def test_v12_combined_run_heat_group_persists_all_results(tmp_path):
    db = tmp_path / "combined.sqlite"
    init_db(db)
    event_id = create_event(str(db), "Test", "GN", "2026-08-14", "LCM", 8)
    replace_athletes(str(db), event_id, [
        {"sort_order": 1, "athlete_number": "1101", "athlete_name": "A", "group_name": "U/19 MEN", "running_heat": 11, "running_lane": 1, "swimming_heat": 1, "swimming_lane": 1},
        {"sort_order": 2, "athlete_number": "1201", "athlete_name": "B", "group_name": "U/19 MEN", "running_heat": 12, "running_lane": 2, "swimming_heat": 1, "swimming_lane": 2},
    ])
    save_run_positions(str(db), event_id, [11, 12], {"1101": 1, "1201": 2})

    run_data = {
        "blocks": [{
            "label": "Heat 11 and 12",
            "heat_numbers": (11, 12),
            "results": [
                {"position": 1, "run_time": "01:20.10"},
                {"position": 2, "run_time": "01:21.20"},
            ],
        }],
        "imported_heat_numbers": [11, 12],
    }
    result = process_run_results(str(db), event_id, run_data)
    assert result["matched_count"] == 2
    persisted = {a["athlete_number"]: a for a in get_athletes(str(db), event_id)}
    assert persisted["1101"]["run_time"] == "01:20.10"
    assert persisted["1201"]["run_time"] == "01:21.20"
    assert any("Combined run heat label(s) detected" in w for w in result["warnings"])
