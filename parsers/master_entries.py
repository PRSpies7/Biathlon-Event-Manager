from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import openpyxl

from .master_entries_pdf import parse_master_entries_pdf

HEAT_RE = re.compile(r"^Heat\s*(\d+)\s*-\s*(.*)$", re.IGNORECASE)


def _as_int(value):
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def parse_master_entries(path_or_file) -> dict[str, Any]:
    """Parse an Excel or PDF Master Entries source into the canonical structure."""
    if isinstance(path_or_file, (str, Path)):
        suffix = Path(path_or_file).suffix.lower()
    else:
        suffix = Path(getattr(path_or_file, "name", "")).suffix.lower()
    if suffix == ".pdf":
        return parse_master_entries_pdf(path_or_file)

    wb = openpyxl.load_workbook(path_or_file, read_only=True, data_only=True)
    if not wb.sheetnames:
        raise ValueError("Workbook contains no worksheets.")
    ws = wb[wb.sheetnames[0]]

    discipline = None
    current_heat = None
    records: list[dict[str, Any]] = []
    source_order = 0

    for row_num, row in enumerate(ws.iter_rows(values_only=True), start=1):
        a = row[0] if len(row) > 0 else None
        b = row[1] if len(row) > 1 else None
        c = row[2] if len(row) > 2 else None
        d = row[3] if len(row) > 3 else None
        s = str(a).strip() if a is not None else ""

        if s.lower() == "running heats":
            discipline = "running"
            current_heat = None
            continue
        if s.lower() == "swimming heats":
            discipline = "swimming"
            current_heat = None
            continue
        m = HEAT_RE.match(s)
        if m:
            current_heat = int(m.group(1))
            continue

        # Ignore repeated headers and blank/separator rows.
        if s == "#" or not s or discipline not in {"running", "swimming"}:
            continue

        athlete_number = _as_int(a)
        lane = _as_int(d)
        if athlete_number is None or b is None or c is None or current_heat is None:
            continue

        source_order += 1
        records.append(
            {
                "source_order": source_order,
                "discipline": discipline,
                "heat": current_heat,
                "athlete_number": str(athlete_number),
                "athlete_name": str(b).strip(),
                "group_name": str(c).strip(),
                "lane": lane,
                "row": row_num,
            }
        )

    if not records:
        raise ValueError("No athlete records were found in the Master Entries workbook.")

    # Build the canonical athlete list from the running roster ordering.
    run_records = [r for r in records if r["discipline"] == "running"]
    swim_records = [r for r in records if r["discipline"] == "swimming"]

    by_athlete: dict[str, dict[str, Any]] = {}
    for rec in run_records:
        aid = rec["athlete_number"]
        if aid in by_athlete:
            raise ValueError(f"Duplicate athlete number in running entries: {aid}")
        by_athlete[aid] = {
            "sort_order": len(by_athlete) + 1,
            "athlete_number": aid,
            "athlete_name": rec["athlete_name"],
            "group_name": rec["group_name"],
            "running_heat": rec["heat"],
            "running_lane": rec["lane"],
            "swimming_heat": None,
            "swimming_lane": None,
        }

    missing_from_run = []
    for rec in swim_records:
        aid = rec["athlete_number"]
        if aid not in by_athlete:
            # Keep swimming-only entrants because TimeDrops needs them, but flag them later.
            by_athlete[aid] = {
                "sort_order": len(by_athlete) + 1,
                "athlete_number": aid,
                "athlete_name": rec["athlete_name"],
                "group_name": rec["group_name"],
                "running_heat": None,
                "running_lane": None,
                "swimming_heat": rec["heat"],
                "swimming_lane": rec["lane"],
            }
            missing_from_run.append(aid)
            continue
        existing = by_athlete[aid]
        if existing["swimming_heat"] is not None:
            raise ValueError(f"Duplicate athlete number in swimming entries: {aid}")
        existing["swimming_heat"] = rec["heat"]
        existing["swimming_lane"] = rec["lane"]

    return {
        "source_type": "xlsx",
        "athletes": list(by_athlete.values()),
        "running_records": run_records,
        "swimming_records": swim_records,
        "running_heats": sorted({r["heat"] for r in run_records}),
        "swimming_heats": sorted({r["heat"] for r in swim_records}),
        "swimming_only_athletes": missing_from_run,
    }
