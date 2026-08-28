from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

HEADER_RE = re.compile(r"^Event\s+#(\d+)\s+Heat\s+(\d+)\s+Race\s+(\d+)", re.IGNORECASE)
ROW_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(.*?)\s+(NS|(?:\d+:)?\d{1,2}:\d{2}\.\d{2}|\d+\.\d{2})(?:\s+.*)?$",
    re.IGNORECASE,
)
ATHLETE_ID_RE = re.compile(r"\((\d+)\)\s*$")


def _normalise_time(value: str) -> str | None:
    value = value.strip()
    if value in {"0.00", "00:00.00", "0:00.00"}:
        return None
    if re.fullmatch(r"\d+\.\d{2}", value):
        return "00:" + value
    if re.fullmatch(r"\d+:\d{2}\.\d{2}", value):
        return "0" + value
    return value


def parse_swim_results(path_or_file) -> dict[str, Any]:
    if hasattr(path_or_file, "read"):
        raw = path_or_file.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
    else:
        with open(path_or_file, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
    lines = raw.splitlines()

    sections: list[dict[str, Any]] = []
    current = None
    pending_revision = False
    for line_no, line in enumerate(lines, start=1):
        if "REVISED FROM EARLIER" in line.upper():
            pending_revision = True
            continue
        m = HEADER_RE.match(line.strip())
        if m:
            if current is not None:
                sections.append(current)
            current = {
                "event": int(m.group(1)),
                "heat": int(m.group(2)),
                "race": int(m.group(3)),
                "start_line": line_no,
                "revision": pending_revision,
                "records": [],
            }
            pending_revision = False
            continue
        if current is None:
            continue
        m = ROW_RE.match(line)
        if not m:
            continue
        lane = int(m.group(1))
        place = int(m.group(2))
        name = m.group(3).strip()
        raw_time = m.group(4)
        # No Start is a status, not a missing or invalid swim result. Do not
        # include it in the result list, reconciliation count, or matching.
        if name.casefold() == "ns" or raw_time.upper() == "NS":
            continue
        id_match = ATHLETE_ID_RE.search(name)
        athlete_number = id_match.group(1) if id_match else None
        clean_name = ATHLETE_ID_RE.sub("", name).strip() if id_match else name
        current["records"].append(
            {
                "lane": lane,
                "place": place,
                "athlete_name": clean_name,
                "athlete_number": athlete_number,
                "swim_time": _normalise_time(raw_time),
                "raw_time": raw_time,
                "line": line_no,
            }
        )

    if current is not None:
        sections.append(current)

    # Key by event/heat/race; later sections replace earlier ones.
    selected: OrderedDict[tuple[int, int, int], dict[str, Any]] = OrderedDict()
    revisions: list[dict[str, Any]] = []
    for sec in sections:
        key = (sec["event"], sec["heat"], sec["race"])
        if key in selected:
            revisions.append({"key": key, "previous_line": selected[key]["start_line"], "replacement_line": sec["start_line"], "revision_flagged": sec["revision"]})
        selected[key] = sec

    # Convert selected sections to athlete-centric results. Later/revised sections win.
    athlete_results: dict[str, dict[str, Any]] = {}
    result_records: list[dict[str, Any]] = []
    for sec in selected.values():
        for record in sec["records"]:
            aid = record["athlete_number"]
            result = {
                **record,
                "event": sec["event"],
                "heat": sec["heat"],
                "race": sec["race"],
            }
            result_records.append(result)
            if aid:
                athlete_results[aid] = result

    return {
        "sections": list(selected.values()),
        "revisions": revisions,
        "athlete_results": athlete_results,
        "result_records": result_records,
        "source_result_count": len(result_records),
        "raw_section_count": len(sections),
    }
