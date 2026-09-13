"""Build the SwimCloud meet-program JSON structure consumed by Time Drops Live.

This is a compatibility format, not arbitrary application JSON. Its round trip is
Phase 1 source data → SwimCloud-style meet-program JSON → Time Drops Live → results
export → Phase 3 result import. Changes to IDs, normalized swimmer names, truncation,
global heat/race numbering, or lane mappings can therefore break Phase 3 matching.
"""

from __future__ import annotations

import copy
import json
import re
import unicodedata
from services.competition import category_key, gender_for_group
from typing import Any

from .timedrops_teams import interprovincial_team_id, interprovincial_teams


TIMEDROPS_UTC_OFFSET = "+02:00"


AGE_GROUP_RANGES = {
    "U/08": (6, 7),
    "U/09": (8, 8),
    "U/11": (9, 10),
    "U/13": (11, 12),
    "U/15": (13, 14),
    "U/17": (15, 16),
    "U/19": (17, 18),
    "JNR": (19, 26),
    "SENIOR": (27, 39),
    "MASTERS 40+": (40, 49),
    "MASTERS 50+": (50, 59),
    "MASTERS 60+": (60, 69),
    "MASTERS 70+": (70, 79),
    "MASTERS 80+": (80, 99),
}


def _timedrops_swimmer_name(value: object, athlete_number: object) -> str:
    """Embed the athlete ID as Phase 3 fallback while keeping the label <=30 chars.

    Time Drops may not reliably preserve its native swimmer ID through the full
    round trip. The ``Name (ID)`` redundancy (for example, ``Elke Vorster (7409)``)
    supports deterministic result matching; only the name portion may be shortened,
    never the athlete-number suffix.
    """
    suffix = f" ({athlete_number})"
    available_name_length = max(0, 30 - len(suffix))
    # TimeDrops consumes this generated JSON, not the SQLite master name.  Use
    # Unicode decomposition so ordinary accented characters become ASCII while
    # preserving the existing AFL removal and the mandatory numeric suffix.
    name = unicodedata.normalize("NFKD", str(value).replace("(AFL)", ""))
    name = name.encode("ascii", "ignore").decode("ascii").strip()
    return f"{name[:available_name_length]}{suffix}"


def infer_gender(group: str | None) -> str:
    """Return the gender code already represented by the imported group label."""
    return gender_for_group(group)


def age_group_key(group: str | None) -> str | None:
    """Apply Biathlon domain age categories used in SwimCloud event metadata."""
    return category_key(group)


def age_range_for_group(group: str | None) -> tuple[int, int] | None:
    key = age_group_key(group)
    return AGE_GROUP_RANGES.get(key) if key else None


def event_for_group(group: str | None) -> int | None:
    """Map the existing biathlon age category to its 25m/50m/100m event."""
    key = age_group_key(group)
    if key == "U/08":
        return 1
    if key in {"U/09", "U/11", "U/13", "MASTERS 60+", "MASTERS 70+", "MASTERS 80+", "SPECIAL NEEDS"}:
        return 2
    if key in {"U/15", "U/17", "U/19", "JNR", "SENIOR", "MASTERS 40+", "MASTERS 50+"}:
        return 3
    return None


def _event_gender(rows: list[dict[str, Any]]) -> str:
    """Return machine-facing F/M/X, independently of human event-label terms."""
    genders = {row.get("gender") or infer_gender(row.get("group_name")) for row in rows}
    genders.discard("")
    if genders == {"F"}:
        return "F"
    if genders == {"M"}:
        return "M"
    if genders == {"F", "M"}:
        return "X"
    return ""


def _event_term(event_gender: str, rows: list[dict[str, Any]]) -> str:
    """Choose the human-facing Girls/Boys/Ladies/Men/Mixed label terminology."""
    if event_gender == "X":
        return "Mixed"

    keys = {age_group_key(row.get("group_name")) for row in rows}
    keys.discard(None)
    has_adult_group = any(key and not key.startswith("U/") for key in keys)
    if not has_adult_group:
        has_adult_group = any(
            re.search(r"\b(ADULT|OPEN)\b", str(row.get("group_name") or ""), re.IGNORECASE)
            for row in rows
        )

    if event_gender == "F":
        return "Ladies" if has_adult_group else "Girls"
    if event_gender == "M":
        return "Men" if has_adult_group else "Boys"
    return ""


def _event_template(reference: dict[str, Any], number: int) -> dict[str, Any]:
    templates = reference.get("meetEvents") or []
    if len(templates) >= number:
        return copy.deepcopy(templates[number - 1])
    return {}


def _build_event(
    reference: dict[str, Any],
    number: int,
    distance: int,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    event = _event_template(reference, number)
    event.update(
        {
            "eventNumber": str(number),
            "eventStrokeCode": 1,
            "eventStroke": "FREE",
            "eventIsRelay": False,
            "eventRelaylegs": 1,
            "eventDistance": distance,
            "eventGender": "",
            "eventMinAge": 0,
            "eventMaxAge": 0,
            "eventDescription": "",
            "eventShortLabel": "",
            "eventFullLabel": "",
            "eventStartTime": "",
        }
    )

    if not rows:
        return event

    event_gender = _event_gender(rows)
    ranges = [age_range for row in rows if (age_range := age_range_for_group(row.get("group_name")))]
    term = _event_term(event_gender, rows)
    description = f"{term} Open {distance}m Freestyle" if term else ""

    event["eventGender"] = event_gender
    if ranges:
        event["eventMinAge"] = min(minimum for minimum, _ in ranges)
        event["eventMaxAge"] = max(maximum for _, maximum in ranges)
    event["eventDescription"] = description
    event["eventShortLabel"] = f"{term} {distance} Free" if term else ""
    event["eventFullLabel"] = description
    return event


def _swimmer_age(athlete: dict[str, Any]) -> int:
    """Use an exact source age when present, otherwise the group's lower boundary."""
    for key in ("swimmer_age", "athlete_age", "age"):
        value = athlete.get(key)
        if value not in (None, ""):
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    age_range = age_range_for_group(athlete.get("group_name"))
    return age_range[0] if age_range else 0


def _team_abbreviation(short_name: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", short_name)
    if len(words) > 1:
        return "".join(word[0] for word in words).upper()[:8]
    return words[0][:3].upper() if words else ""


def _build_team(reference: dict[str, Any], host_team: str) -> dict[str, Any]:
    reference_teams = reference.get("meetTeams") or []
    team = copy.deepcopy(reference_teams[0]) if reference_teams else {}
    reference_full_name = str(team.get("teamFullName") or "").strip()
    if reference_full_name.casefold() == host_team.casefold() and team.get("teamShortName"):
        short_name = str(team["teamShortName"]).strip()
    else:
        short_name = host_team[:40]
    team.update(
        {
            "teamId": "1",
            "teamAbbreviation": "",
            "teamShortName": short_name,
            "teamFullName": host_team,
            "teamMascot": team.get("teamMascot"),
        }
    )
    return team


def _id_sort_key(athlete: dict[str, Any]) -> tuple[int, int | str]:
    athlete_id = str(athlete.get("athlete_number") or "")
    return (0, int(athlete_id)) if athlete_id.isdigit() else (1, athlete_id)


def generate_timedrops_json(
    reference: dict[str, Any],
    athletes: list[dict[str, Any]],
    *,
    meet_name: str,
    host_team: str,
    start_date: str,
    course: str,
    pool_lanes: int,
    timezone_offset: str = TIMEDROPS_UTC_OFFSET,
    meet_type: str = "Local",
) -> dict[str, Any]:
    """Generate a SwimCloud-compatible meet program from swimming assignments only.

    Canonical athlete records also contain running assignments, but Running Heats
    must never leak into this swimming meet program.
    """
    if meet_type not in {"Local", "Interprovincial", "National"}:
        raise ValueError("Meet type must be Local, Interprovincial or National.")

    data = copy.deepcopy(reference)
    data["meetName"] = meet_name
    data["meetHostTeamName"] = host_team
    data["meetStartDate"] = start_date
    data["meetEndDate"] = None
    data["meetProgramVersion"] = reference.get("meetProgramVersion", 1)
    data["meetProgramDateTime"] = reference.get("meetProgramDateTime")

    # The canonical athlete records have independent running and swimming
    # assignments. Only athletes with a swimming heat participate here.
    swimmers = [athlete for athlete in athletes if athlete.get("swimming_heat") is not None]
    provincial_teams = meet_type == "Interprovincial" or (meet_type == "National" and any(a.get("province") for a in swimmers))
    swimmer_team_ids = {
        str(athlete["athlete_number"]): (
            interprovincial_team_id(athlete) if provincial_teams else "1"
        )
        for athlete in swimmers
    }
    swimming_heats: dict[int, list[dict[str, Any]]] = {}
    for athlete in swimmers:
        swimming_heats.setdefault(int(athlete["swimming_heat"]), []).append(athlete)

    # A few established source heats include an age-unspecified category (for
    # example Special Needs) alongside a mapped category. Preserve those lanes
    # by assigning the whole heat to its single known distance event.
    heat_event: dict[int, int] = {}
    for heat, rows in swimming_heats.items():
        events = {{25:1,50:2,100:3}.get(row.get("swim_distance"),event_for_group(row.get("group_name"))) for row in rows}
        events.discard(None)
        if not events:
            raise ValueError(f"Could not map swimming Heat {heat} to a TimeDrops event.")
        if len(events) > 1:
            raise ValueError(
                f"Swimming Heat {heat} contains groups that map to different TimeDrops events: {sorted(events)}"
            )
        heat_event[heat] = int(next(iter(events)))

    event_rows = {
        event_number: [
            row
            for heat, rows in swimming_heats.items()
            if heat_event[heat] == event_number
            for row in rows
        ]
        for event_number in (1, 2, 3)
    }
    data["meetEvents"] = [
        _build_event(reference, 1, 25, event_rows[1]),
        _build_event(reference, 2, 50, event_rows[2]),
        _build_event(reference, 3, 100, event_rows[3]),
    ]

    totals = {number: sum(1 for event in heat_event.values() if event == number) for number in (1, 2, 3)}
    reference_sessions = reference.get("meetSessions") or [{}]
    base_session = copy.deepcopy(reference_sessions[0])
    base_session["sessionNumber"] = 1
    base_session["sessionId"] = "1"
    base_session["sessionName"] = "Session 1"
    base_session["sessionBeginAt"] = f"{start_date}T00:00:00{timezone_offset}"
    base_session["sessionEndAt"] = None
    base_session["sessionIsCurrent"] = True
    base_session["sessionPool"] = {
        "poolNumberOfLanes": int(pool_lanes),
        "poolCourse": course,
        "poolFirstLaneNumber": 1,
    }

    reference_races = base_session.get("sessionRaces") or [{}]
    race_source = reference_races[0]
    reference_lanes = race_source.get("raceLanes") or [{}]
    lane_source = reference_lanes[0]
    races = []
    for heat in sorted(swimming_heats):
        event_number = heat_event[heat]
        race = copy.deepcopy(race_source)
        race["raceEventNumber"] = str(event_number)
        # The working Time Drops flow deliberately uses the application's continuous,
        # meet-wide heat sequence for race/heat numbers. Do not convert this to
        # conventional per-event numbering without verifying Time Drops compatibility.
        race["raceNumber"] = heat
        race["raceHeatType"] = "F"
        race["raceHeatNumber"] = heat
        race["raceTotalHeats"] = totals[event_number]
        lanes = []
        for athlete in sorted(
            swimming_heats[heat],
            key=lambda row: (row.get("swimming_lane") is None, row.get("swimming_lane") or 999),
        ):
            lane = copy.deepcopy(lane_source)
            lane["laneNumber"] = int(athlete["swimming_lane"])
            lane["isEmpty"] = False
            lane["laneEventNumber"] = str(event_number)
            lane["laneSeedTime"] = 0
            lane["laneSwimmerId"] = str(athlete["athlete_number"])
            lane["laneTeamId"] = swimmer_team_ids[str(athlete["athlete_number"])]
            lanes.append(lane)
        race["raceLanes"] = lanes
        races.append(race)
    base_session["sessionRaces"] = races
    data["meetSessions"] = [base_session]

    data["meetTeams"] = (
        interprovincial_teams()
        if provincial_teams
        else [_build_team(reference, host_team)]
    )

    reference_swimmers = reference.get("meetSwimmers") or [{}]
    swimmer_source = reference_swimmers[0]
    output_swimmers = []
    seen: set[str] = set()
    for athlete in sorted(swimmers, key=_id_sort_key):
        athlete_id = str(athlete["athlete_number"])
        if athlete_id in seen:
            continue
        seen.add(athlete_id)
        swimmer = copy.deepcopy(swimmer_source)
        swimmer["swimmerId"] = athlete_id
        swimmer["swimmerName"] = _timedrops_swimmer_name(athlete["athlete_name"], athlete_id)
        swimmer["swimmerGender"] = athlete.get("gender") or infer_gender(athlete.get("group_name"))
        swimmer["swimmerAge"] = _swimmer_age(athlete)
        swimmer["swimmerTeamId"] = swimmer_team_ids[athlete_id]
        output_swimmers.append(swimmer)
    data["meetSwimmers"] = output_swimmers

    return data


def dumps_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=4, ensure_ascii=False) + "\n"
