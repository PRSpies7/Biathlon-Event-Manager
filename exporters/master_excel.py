from __future__ import annotations

from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment


def build_master_import_xlsx(athletes: list[dict[str, Any]]) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "FOR IMPORT"
    headers = ["Athlete nr", "Athlete Name", "athleteSurname", "runtime", "swimtime"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="left")
        cell.number_format = "@"

    for a in athletes:
        # Export partial results without changing the captured source times.
        if not a.get("run_time") and not a.get("swim_time"):
            continue
        ws.append([
            str(a["athlete_number"]),
            str(a["athlete_name"]),
            str(a["athlete_name"]),
            str(a.get("run_time") or "00:00.00"),
            str(a.get("swim_time") or "00:00.00"),
        ])
        for c in ws[ws.max_row]:
            c.number_format = "@"

    widths = {"A": 14, "B": 34, "C": 34, "D": 16, "E": 16}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output
