from __future__ import annotations

import re
from collections import Counter
from typing import Any

TIME_RE = re.compile(r"^(?:\d{1,2}):\d{2}\.\d{2}$")


def normalize_time(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text in {"0", "0.00", "00:00.00", "0:00.00", "00.00"}:
        return None

    # Normalize common manual punctuation/spacing variants to separators.
    cleaned = text.replace(";", ":").replace(",", ":")
    cleaned = re.sub(r"\s+", ":", cleaned)

    # Accept MM:SS.ss, M:SS.ss, MM.SS.ss, MM,SS,ss, etc.
    if ":" in cleaned:
        parts = [p for p in re.split(r":+", cleaned) if p != ""]
    else:
        parts = [p for p in re.split(r"\.", cleaned) if p != ""]
        # 01.01.20 means MM.SS.hh, whereas 01.20 means MM.hh is not a valid
        # final time for this application.
        if len(parts) == 3:
            pass
        else:
            return None

    if len(parts) == 2:
        minutes, seconds_part = parts
        if "." not in seconds_part:
            return None
        sec, frac = seconds_part.split(".", 1)
    elif len(parts) == 3:
        minutes, sec, frac = parts
    else:
        return None

    if not minutes.isdigit() or not sec.isdigit() or not frac.isdigit() or len(frac) != 2:
        return None
    m = int(minutes)
    s = int(sec)
    if s >= 60:
        return None
    return f"{m:02d}:{s:02d}.{frac}"


def validate_master(athletes: list[dict[str, Any]]) -> list[str]:
    issues = []
    ids = [str(a.get("athlete_number", "")).strip() for a in athletes]
    blanks = [i for i, x in enumerate(ids, 1) if not x]
    if blanks: issues.append(f"{len(blanks)} athlete records have a blank athlete number.")
    dup = [aid for aid, c in Counter(ids).items() if aid and c > 1]
    if dup: issues.append(f"Duplicate athlete numbers: {', '.join(sorted(dup))}")
    missing_names = sum(1 for a in athletes if not str(a.get("athlete_name", "")).strip())
    if missing_names: issues.append(f"{missing_names} athlete records have a blank athlete name.")
    return issues


def validate_positions(selected_athletes: list[dict[str, Any]], positions: dict[str, int | None]) -> list[str]:
    issues = []
    vals = [p for p in positions.values() if p is not None]
    dup = [str(p) for p, c in Counter(vals).items() if c > 1]
    if dup: issues.append(f"Duplicate position numbers: {', '.join(dup)}")
    if any((p is not None and p < 1) for p in vals): issues.append("Position numbers must be positive integers.")
    return issues


def validate_times(athletes: list[dict[str, Any]], require_complete: bool = False) -> list[str]:
    issues = []
    if require_complete:
        for a in athletes:
            if not a.get("run_time") or not a.get("swim_time"):
                issues.append(f"Athlete {a.get('athlete_number')} is missing a runtime or swimtime.")
    for a in athletes:
        for field in ("run_time", "swim_time"):
            value = a.get(field)
            if value and not TIME_RE.match(str(value)):
                issues.append(f"Athlete {a.get('athlete_number')} has invalid {field}: {value}")
    return issues
