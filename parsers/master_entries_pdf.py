from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pdfplumber

HEAT_RE = re.compile(r"\bHeat\s+(\d+)\s*-", re.IGNORECASE)
DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-_](\d{2})[-_](\d{2})(?!\d)")


def _clean_group(text: str) -> str:
    """Normalize PDF group labels to the same group representation as Excel."""
    text = re.sub(r"\s*\(\d+\s*m\)\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*\(AFL\)\s*", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _group_words_by_line(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    lines: dict[float, list[dict[str, Any]]] = {}
    for word in words:
        key = round(float(word["top"]), 1)
        lines.setdefault(key, []).append(word)
    return [sorted(items, key=lambda item: float(item["x0"])) for _, items in sorted(lines.items())]


def parse_master_entries_pdf(path_or_file) -> dict[str, Any]:
    """Parse the standard Meet Program PDF into the canonical Master Entries structure.

    The PDF contains separate Running Heats and Swimming Heats sections. The parser
    uses the PDF's column positions rather than relying on spaces in extracted text,
    which keeps athlete names and group names intact when either contains spaces.
    """
    records: list[dict[str, Any]] = []
    discipline = "running"
    current_heat: int | None = None
    source_order = 0

    try:
        pdf = pdfplumber.open(path_or_file)
    except Exception as exc:
        raise ValueError(f"Could not open the PDF: {exc}") from exc

    with pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=1, y_tolerance=2) or ""
            if re.search(r"^\s*Swimming Heats\s*$", text, re.IGNORECASE | re.MULTILINE):
                discipline = "swimming"
                current_heat = None

            words = page.extract_words(x_tolerance=1, y_tolerance=2, keep_blank_chars=False)
            for line_words in _group_words_by_line(words):
                if not line_words:
                    continue

                line_text = " ".join(str(w["text"]) for w in line_words)
                heat_match = HEAT_RE.search(line_text)
                if heat_match:
                    current_heat = int(heat_match.group(1))
                    continue

                if discipline not in {"running", "swimming"} or current_heat is None:
                    continue

                first = str(line_words[0]["text"])
                if not re.fullmatch(r"\d{3,6}", first):
                    continue

                # The PDF uses fixed visual columns. Athlete names start around x=93,
                # group labels around x=200+, and the lane column is >300.
                lane_candidates = [
                    word for word in line_words[1:]
                    if re.fullmatch(r"\d{1,2}", str(word["text"]))
                    and float(word["x0"]) > 300
                ]
                if not lane_candidates:
                    continue
                lane_word = lane_candidates[0]
                lane = int(str(lane_word["text"]))

                name_words = [
                    str(word["text"])
                    for word in line_words[1:]
                    if 70 <= float(word["x0"]) < 200
                ]
                group_words = [
                    str(word["text"])
                    for word in line_words[1:]
                    if 180 <= float(word["x0"]) < float(lane_word["x0"])
                ]

                athlete_name = " ".join(name_words).strip()
                group_name = _clean_group(" ".join(group_words))
                if not athlete_name or not group_name:
                    continue

                source_order += 1
                records.append(
                    {
                        "source_order": source_order,
                        "discipline": discipline,
                        "heat": current_heat,
                        "athlete_number": first,
                        "athlete_name": athlete_name,
                        "group_name": group_name,
                        "lane": lane,
                    }
                )

    if not records:
        raise ValueError("No athlete records were found in the Meet Program PDF.")

    run_records = [r for r in records if r["discipline"] == "running"]
    swim_records = [r for r in records if r["discipline"] == "swimming"]
    if not run_records:
        raise ValueError("The PDF does not contain a Running Heats section with athlete records.")
    if not swim_records:
        raise ValueError("The PDF does not contain a Swimming Heats section with athlete records.")

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

    swimming_only: list[str] = []
    for rec in swim_records:
        aid = rec["athlete_number"]
        if aid not in by_athlete:
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
            swimming_only.append(aid)
            continue
        existing = by_athlete[aid]
        if existing["swimming_heat"] is not None:
            raise ValueError(f"Duplicate athlete number in swimming entries: {aid}")
        existing["swimming_heat"] = rec["heat"]
        existing["swimming_lane"] = rec["lane"]

    return {
        "source_type": "pdf",
        "athletes": list(by_athlete.values()),
        "running_records": run_records,
        "swimming_records": swim_records,
        "running_heats": sorted({r["heat"] for r in run_records}),
        "swimming_heats": sorted({r["heat"] for r in swim_records}),
        "swimming_only_athletes": swimming_only,
    }


def infer_pdf_event_defaults(filename: str) -> dict[str, Any]:
    """Infer the minimum event settings needed for PDF-only initialization.

    The supplied Meet Program format does not contain explicit host, course, or
    TimeDrops timezone fields. The application therefore uses its established
    Phase 1 defaults for those values and extracts the meet date/name when the
    filename provides them.
    """
    stem = Path(filename).stem
    date_match = DATE_RE.search(stem)
    start_date = (
        f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
        if date_match
        else None
    )
    meet_name = re.sub(r"[_-]?Heats[_-]?20\d{2}[-_]\d{2}[-_]\d{2}$", "", stem, flags=re.IGNORECASE)
    meet_name = meet_name.replace("_", " ").strip() or "Biathlon Event"
    return {
        "meet_name": meet_name,
        "host_team": "Gauteng North Biathlon",
        "start_date": start_date,
        "course": "LCM",
        "timezone": "+02:00",
    }
