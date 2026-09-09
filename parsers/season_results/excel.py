from __future__ import annotations

import openpyxl

from .common import header_mapping, normalize_rows, recognize_metadata
from .models import INTERPROVINCIAL, LEAGUE


def parse_excel(source, filename):
    workbook = openpyxl.load_workbook(source, data_only=True, read_only=True)
    try:
        # One event per file; repeated category headings are preserved across sheets.
        rows = [list(row) for sheet in workbook.worksheets for row in sheet.iter_rows(values_only=True)
                if any(v is not None for v in row)]
    finally:
        workbook.close()
    first_header = next((i for i, row in enumerate(rows) if header_mapping(row)), None)
    if first_header is None:
        raise ValueError("No published results table was found in the workbook.")
    mapping = header_mapping(rows[first_header])
    league = "team" not in mapping.values() and "province" not in mapping.values()
    event = recognize_metadata([v for row in rows[:first_header] for v in row], filename,
                               LEAGUE if league else INTERPROVINCIAL)
    return normalize_rows(event, rows[first_header:], league)
