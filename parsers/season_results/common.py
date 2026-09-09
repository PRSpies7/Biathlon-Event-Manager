"""Shared normalization for layout adapters. All scores remain source values."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
import re

from .models import Award, CHAMPIONSHIP, INTERPROVINCIAL, LEAGUE, NormalizedEvent, Result, is_gn_championship

AFL_RE = re.compile(r"\(\s*AFL\s*\*?\s*\)", re.I)
PB_RE = re.compile(r"\(\s*PB\s*\)|\bPB\b", re.I)
DATE_RE = re.compile(r"\b(?:20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]20\d{2})\b")
STATUSES = {"DNF", "DNS", "DQ", "DSQ", "NS", "NT", "TO"}
HEADERS = {
    "#": "athlete_number", "athlete number": "athlete_number", "athlete nr": "athlete_number",
    "athlete": "athlete_name", "athlete name": "athlete_name", "position": "position", "pos": "position",
    "run time": "run_time", "running time": "run_time", "run points": "running_points",
    "running points": "running_points", "rp": "running_points", "swim time": "swim_time",
    "swimming time": "swim_time", "swim points": "swimming_points", "swimming points": "swimming_points",
    "sp": "swimming_points", "bp": "bonus_points", "bonus points": "bonus_points",
    "total points": "total_points", "school": "school", "province": "province", "team": "team",
    "status": "status",
}


def text(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def clean_value(value) -> str:
    if isinstance(value, (time, timedelta)):
        seconds = (value.hour * 3600 + value.minute * 60 + value.second + value.microsecond / 1_000_000
                   if isinstance(value, time) else value.total_seconds())
        # Excel represents times as numbers; keep milliseconds without rounding scores.
        millis = round(seconds * 1000)
        minutes, rem = divmod(millis, 60000)
        sec, ms = divmod(rem, 1000)
        fraction = f"{ms:03d}".rstrip("0").ljust(2, "0")
        return f"{minutes:02d}:{sec:02d}.{fraction}"
    return text(PB_RE.sub("", text(value)))


def athlete_number(value) -> str:
    s = text(value)
    # Do not discard leading zeroes from identifiers supplied as text.
    return s[:-2] if re.fullmatch(r"\d+\.0", s) else s


def clean_name(value, league: bool) -> tuple[str, bool, str, str]:
    value = clean_value(value)
    affiliated = bool(AFL_RE.search(value))
    value = AFL_RE.sub("", value)
    annotations = re.findall(r"\(([^()]*)\)", value)
    school = "; ".join(a.strip() for a in annotations if a.upper().strip() not in STATUSES) if league else ""
    other = "; ".join(a.strip() for a in annotations if not league or a.upper().strip() in STATUSES)
    name = text(re.sub(r"\([^()]*\)", "", value))
    # Join words split at an existing hyphen by PDF wrapping.
    return re.sub(r"-\s+", "-", name), affiliated, school, other


def recognize_metadata(lines: list, filename: str, layout_type: str = "") -> NormalizedEvent:
    strings = [text(v) for v in lines if text(v)]
    event_date = next((v.date() if isinstance(v, datetime) else v for v in lines
                       if isinstance(v, (date, datetime))), None)
    for s in strings:
        match = DATE_RE.search(s)
        if match:
            parts = re.split(r"[-/]", match.group())
            y, m, d = parts if len(parts[0]) == 4 else reversed(parts)
            try:
                event_date = date(int(y), int(m), int(d))
            except ValueError as exc:
                raise ValueError("The document contains an unreadable event date.") from exc
            break
    title = next((s for s in strings if re.search(r"league\s*\d+|inter[ -]?provincial|championship|\bchamps\b", s, re.I)), "")
    if not title:
        title = next((s for s in strings if s not in {"Competition Name", "Competition Date"}
                      and not DATE_RE.search(s) and not s.startswith("Reports")), "")
    title = text(DATE_RE.sub("", title)).strip(" -")
    detected = (CHAMPIONSHIP if is_gn_championship(title)
                else INTERPROVINCIAL if re.search(r"inter[ -]?provincial", title, re.I)
                else LEAGUE if re.search(r"league\s*\d+", title, re.I) else "")
    notes = []
    if not detected:
        notes.append("The title does not identify a supported competition. Confirm the event name and competition type; this layout supports league, interprovincial and Gauteng North Championship imports.")
    elif detected != CHAMPIONSHIP and layout_type and layout_type != detected:
        notes.append("The title and table layout differ. Confirm the competition type.")
        detected = ""
    if not event_date:
        notes.append("No event date was found in the document. Enter the published event date.")
    return NormalizedEvent(title, event_date, detected, filename, notes=notes)


def header_mapping(row) -> dict[int, str] | None:
    mapped = {i: HEADERS[text(v).casefold()] for i, v in enumerate(row) if text(v).casefold() in HEADERS}
    if "athlete_number" not in mapped.values() or "athlete_name" not in mapped.values():
        return None
    if "position" not in mapped.values():
        mapped[0] = "position"
    return mapped


def award_type(value: str) -> str | None:
    match = re.fullmatch(r"Top\s*(?:3\s*)?(Runners?|Swimmers?|(?:Overall\s*)?Athletes?)", value, re.I)
    if not match:
        return None
    group = match.group(1).casefold()
    return "Runner" if group.startswith("runner") else "Swimmer" if group.startswith("swimmer") else "Overall Athlete"


def category_name(value: str) -> str | None:
    value = re.split(r"National Record:|Provincial Record:", value, flags=re.I)[0].strip(" -")
    return value if re.match(r"^(U\s*/?\s*\d+|MASTERS?\b|SENIORS?\b|JNR\b|JUNIORS?\b|SPECIAL NEEDS\b)", value, re.I) else None


def normalize_rows(event: NormalizedEvent, rows: list[list], league: bool) -> NormalizedEvent:
    mapping = None
    category = ""
    award = None
    for index, row in enumerate(rows, 1):
        new_mapping = header_mapping(row)
        if new_mapping:
            mapping = new_mapping
            continue
        first = text(row[0]) if row else ""
        heading = text(" ".join(text(v) for v in row))
        kind = award_type(heading)
        if kind:
            award, category = kind, ""
            continue
        group = category_name(heading)
        if group:
            category, award = group, None
            continue
        if first.casefold() == "all results":
            award = None
            continue
        if not mapping or not (category or award):
            continue
        fields = {key: row[i] if i < len(row) else None for i, key in mapping.items()}
        number = athlete_number(fields.get("athlete_number"))
        if not number:
            if first or text(fields.get("athlete_name")):
                raise ValueError(f"Result row {index} is missing an athlete number. Import stopped; no name matching was attempted.")
            continue
        name, affiliated, school, annotations = clean_name(fields.get("athlete_name"), league)
        if not name:
            raise ValueError(f"Athlete {number} is missing a name.")
        if award:
            try:
                placing = int(text(fields["position"]))
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Unreadable award placing for athlete {number}.") from exc
            event.awards.append(Award(number, name, award, placing, affiliated))
            continue
        required = {"run_time", "running_points", "swim_time", "swimming_points", "bonus_points", "total_points"}
        if not required.issubset(fields):
            raise ValueError("Category result table is missing expected result columns.")
        values = {k: clean_value(v) for k, v in fields.items() if k not in {"athlete_name", "athlete_number"}}
        status = values.get("status", "") or "; ".join(dict.fromkeys(v.upper() for v in values.values() if v.upper() in STATUSES))
        # Recognize format errors without checking whether points/times are correct.
        for key in ("running_points", "swimming_points", "bonus_points", "total_points"):
            value = values[key]
            if value and value.upper() not in STATUSES and value != "-":
                try:
                    if not Decimal(value).is_finite():
                        raise InvalidOperation
                except InvalidOperation as exc:
                    raise ValueError(f"Unreadable {key.replace('_', ' ')} for athlete {number}: {value}") from exc
        values["school"] = values.get("school") or school
        values["status"] = status
        event.results.append(Result(number, name, category, affiliated=affiliated, annotations=annotations, **values))
    if not event.results:
        raise ValueError("No category results were found. Use a finalized results file with athlete numbers.")
    return event
