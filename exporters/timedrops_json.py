from __future__ import annotations

import copy
import json
import unicodedata
from datetime import date
from typing import Any


def _timedrops_swimmer_name(value: object, athlete_number: object) -> str:
    """Build TimeDrops' conventional ``Name (ID)`` label within 30 characters."""
    suffix = f" ({athlete_number})"
    available_name_length = max(0, 30 - len(suffix))
    # TimeDrops consumes this generated JSON, not the SQLite master name.  Use
    # Unicode decomposition so ordinary accented characters become ASCII while
    # preserving the existing AFL removal and the mandatory numeric suffix.
    name = unicodedata.normalize("NFKD", str(value).replace("(AFL)", ""))
    name = name.encode("ascii", "ignore").decode("ascii").strip()
    return f"{name[:available_name_length]}{suffix}"


def infer_gender(group: str | None) -> str:
    g = (group or "").upper()
    if "GIRLS" in g or "WOMEN" in g or "FEMALE" in g:
        return "F"
    if "BOYS" in g or "MEN" in g or "MALE" in g:
        return "M"
    return ""


def event_for_group(group: str) -> int | None:
    g = (group or "").upper()
    event1 = ["U/08"]
    event2 = ["U/09", "U/11", "U/13", "MASTERS 60", "MASTERS 70", "MASTERS 80"]
    event3 = ["U/15", "U/17", "U/19", "JNR", "JUNIOR", "SENIOR", "MASTERS 40", "MASTERS 50"]
    if any(x in g for x in event1):
        return 1
    if any(x in g for x in event2):
        return 2
    if any(x in g for x in event3):
        return 3
    return None


def _build_event_template(reference: dict[str, Any], number: int, distance: int) -> dict[str, Any]:
    obj = copy.deepcopy(reference["meetEvents"][number - 1])
    obj["eventNumber"] = str(number)
    obj["eventStrokeCode"] = 1
    obj["eventStroke"] = "FREE"
    obj["eventIsRelay"] = False
    obj["eventRelaylegs"] = 1
    obj["eventDistance"] = distance
    obj["eventGender"] = None
    obj["eventMinAge"] = 0
    obj["eventMaxAge"] = 0
    obj["eventDescription"] = ""
    obj["eventShortLabel"] = ""
    obj["eventFullLabel"] = ""
    obj["eventStartTime"] = ""
    return obj


def generate_timedrops_json(reference: dict[str, Any], athletes: list[dict[str, Any]], *, meet_name: str, host_team: str, start_date: str, course: str, pool_lanes: int, timezone_offset: str = "+02:00") -> dict[str, Any]:
    data = copy.deepcopy(reference)
    data["meetName"] = meet_name
    data["meetHostTeamName"] = host_team
    data["meetStartDate"] = start_date
    data["meetEndDate"] = None
    data["meetProgramVersion"] = reference.get("meetProgramVersion", 1)
    data["meetProgramDateTime"] = None

    data["meetEvents"] = [
        _build_event_template(reference, 1, 25),
        _build_event_template(reference, 2, 50),
        _build_event_template(reference, 3, 100),
    ]

    swimmers = [a for a in athletes if a.get("swimming_heat") is not None]
    swimming_heats = {}
    for a in swimmers:
        swimming_heats.setdefault(int(a["swimming_heat"]), []).append(a)

    # Count heats per event so raceTotalHeats is preserved in the required structure.
    heat_event = {}
    for heat, rows in swimming_heats.items():
        events = {event_for_group(r.get("group_name")) for r in rows}
        events.discard(None)
        if not events:
            raise ValueError(f"Could not map swimming Heat {heat} to a TimeDrops event.")
        if len(events) > 1:
            raise ValueError(f"Swimming Heat {heat} contains groups that map to different TimeDrops events: {sorted(events)}")
        heat_event[heat] = int(next(iter(events)))
    totals = {n: sum(1 for e in heat_event.values() if e == n) for n in (1, 2, 3)}

    base_session = copy.deepcopy(reference["meetSessions"][0])
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

    races = []
    for heat in sorted(swimming_heats):
        event_num = heat_event[heat]
        race_template = copy.deepcopy(reference["meetSessions"][0]["sessionRaces"][0])
        race_template["raceEventNumber"] = str(event_num)
        race_template["raceNumber"] = heat
        race_template["raceHeatType"] = "F"
        race_template["raceHeatNumber"] = heat
        race_template["raceTotalHeats"] = totals[event_num]
        lanes = []
        for a in sorted(swimming_heats[heat], key=lambda x: (x.get("swimming_lane") is None, x.get("swimming_lane") or 999)):
            lane_template = copy.deepcopy(reference["meetSessions"][0]["sessionRaces"][0]["raceLanes"][0])
            lane_template["laneNumber"] = int(a["swimming_lane"])
            lane_template["isEmpty"] = False
            lane_template["laneEventNumber"] = str(event_num)
            lane_template["laneSeedTime"] = 0
            lane_template["laneSwimmerId"] = str(a["athlete_number"])
            lane_template["laneTeamId"] = "1"
            lanes.append(lane_template)
        race_template["raceLanes"] = lanes
        races.append(race_template)
    base_session["sessionRaces"] = races
    data["meetSessions"] = [base_session]

    # Preserve the required team structure; use the event host/team name.
    team = copy.deepcopy(reference["meetTeams"][0]) if reference.get("meetTeams") else {
        "teamId": "1", "teamAbbreviation": "", "teamShortName": host_team, "teamFullName": host_team, "teamMascot": None
    }
    team["teamId"] = "1"
    team["teamFullName"] = host_team
    team["teamShortName"] = host_team[:40]
    data["meetTeams"] = [team]

    swimmer_template = copy.deepcopy(reference["meetSwimmers"][0]) if reference.get("meetSwimmers") else {
        "swimmerId": "", "swimmerName": "", "swimmerGender": "", "swimmerAge": 0, "swimmerTeamId": "1"
    }
    out_swimmers = []
    seen = set()
    for a in sorted(swimmers, key=lambda x: int(x["athlete_number"])):
        aid = str(a["athlete_number"])
        if aid in seen:
            continue
        seen.add(aid)
        s = copy.deepcopy(swimmer_template)
        s["swimmerId"] = aid
        s["swimmerName"] = _timedrops_swimmer_name(a["athlete_name"], aid)
        s["swimmerGender"] = infer_gender(a.get("group_name"))
        s["swimmerAge"] = 0
        s["swimmerTeamId"] = "1"
        out_swimmers.append(s)
    data["meetSwimmers"] = out_swimmers

    return data


def dumps_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=4, ensure_ascii=False) + "\n"
