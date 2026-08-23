from __future__ import annotations

from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment


def build_run_positions_xlsx(athletes: list[dict[str, Any]], run_groups: list[dict[str, Any]]) -> BytesIO:
    """Build a single, print-friendly XLSX containing all persisted Phase 2 mappings."""
    group_labels = {
        g["group_key"]: " + ".join(str(n) for n in g.get("heat_numbers", []))
        for g in run_groups
    }
    rows = []
    for a in athletes:
        group_key = a.get("run_group_key")
        if not group_key:
            continue
        rows.append([
            f"Heat {group_labels.get(group_key, group_key)}",
            str(a.get("athlete_number", "")),
            str(a.get("group_name") or ""),
            str(a.get("athlete_name", "")),
            "" if a.get("run_position") is None else a.get("run_position"),
        ])

    rows.sort(key=lambda r: (
        tuple(int(x.strip()) for x in r[0].replace("Heat ", "").split("+") if x.strip()),
        int(r[4]) if isinstance(r[4], int) else 9999,
        r[1],
    ))

    wb = Workbook()
    ws = wb.active
    ws.title = "Run Positions"
    headers = ["Heat", "Athlete Number", "Age Group", "Athlete Name", "Run Position"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="left")
    for row in rows:
        ws.append(row)
    widths = {"A": 18, "B": 18, "C": 16, "D": 34, "E": 16}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output
