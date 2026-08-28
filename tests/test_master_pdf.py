from pathlib import Path

from parsers.master_entries import parse_master_entries
from parsers.master_entries_pdf import infer_pdf_event_defaults

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PDF = ROOT / "tests" / "fixtures" / "sample_meet_program.pdf"


def test_pdf_master_parser_matches_excel_roster():
    excel = parse_master_entries(DATA / "Master Entries Excel.xlsx")
    pdf = parse_master_entries(PDF)

    assert pdf["source_type"] == "pdf"
    assert len(pdf["athletes"]) == len(excel["athletes"]) == 136
    assert pdf["running_heats"] == list(range(1, 14))
    assert pdf["swimming_heats"] == list(range(1, 19))

    excel_by_id = {a["athlete_number"]: a for a in excel["athletes"]}
    pdf_by_id = {a["athlete_number"]: a for a in pdf["athletes"]}
    assert set(pdf_by_id) == set(excel_by_id)

    for aid, expected in excel_by_id.items():
        actual = pdf_by_id[aid]
        for field in (
            "athlete_name", "group_name", "running_heat", "running_lane",
            "swimming_heat", "swimming_lane",
        ):
            assert actual[field] == expected[field], (aid, field, actual[field], expected[field])


def test_pdf_defaults():
    defaults = infer_pdf_event_defaults("GN LEAGUE 4_Heats_2025-11-04.pdf")
    assert defaults["meet_name"] == "GN LEAGUE 4"
    assert defaults["start_date"] == "2025-11-04"
    assert defaults["course"] == "SCM"
    assert defaults["timezone"] == "+02:00"
