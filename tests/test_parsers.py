from pathlib import Path
import io
import json

from openpyxl import Workbook

from parsers.master_entries import parse_master_entries
from parsers.run_results_excel import parse_run_results_excel
from parsers.swim_results import parse_swim_results
from exporters.results_xml import build_results_xml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def test_master_parser():
    x = parse_master_entries(DATA / "Master Entries Excel.xlsx")
    assert len(x["athletes"]) == 136
    assert x["running_heats"] == list(range(1, 14))
    assert x["swimming_heats"] == list(range(1, 19))
    assert x["athletes"][0]["athlete_number"] == "3235"


def test_run_parser():
    x = parse_run_results_excel(DATA / "Run Results LG4.xlsx")
    assert x["imported_heat_numbers"] == [1,2,3,4,5,6,7,8,9,10,11,13]
    heat1 = next(b for b in x["blocks"] if b["heat_numbers"] == (1,))
    assert heat1["results"][0] == {"position": 1, "run_time": "01:18.14", "row": 5}


def test_swim_parser_and_revision():
    x = parse_swim_results(DATA / "Swim TXT file.txt")
    assert x["athlete_results"]["7276"]["swim_time"] == "00:41.68"
    assert x["athlete_results"]["6702"]["swim_time"] == "03:55.05"
    assert x["revisions"]


def test_xml_shape():
    payload = [{"athlete_number":"1011","athlete_name":"John Doe","run_time":"04:12.50","swim_time":"01:05.20"}]
    xml = build_results_xml(payload).decode("utf-8")
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
    assert '<results xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">' in xml
    assert '<athleteNo>1011</athleteNo>' in xml


def test_run_parser_recognizes_combined_heat_labels():
    wb = Workbook()
    ws = wb.active
    ws.title = "Run times"
    ws.append(["Heat 11 and 12"])
    ws.append(["Lap", "Time"])
    ws.append([1, "01:20.10"])
    ws.append([2, "01:21.20"])
    payload = io.BytesIO()
    wb.save(payload)
    payload.seek(0)

    parsed = parse_run_results_excel(payload)
    assert parsed["imported_heat_numbers"] == [11, 12]
    assert parsed["blocks"][0]["heat_numbers"] == (11, 12)
    assert len(parsed["blocks"][0]["results"]) == 2
