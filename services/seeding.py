"""Entry enrichment and real, distance-matched historical seed selection."""
from copy import deepcopy
import re
import unicodedata

from database.season_repository import historical_performances, season_snapshot
from services.competition import distances, gender_for_group


def name_key(value):
    text = unicodedata.normalize("NFKD", str(value).replace("(AFL)", ""))
    return " ".join(re.findall(r"\w+", "".join(c for c in text if not unicodedata.combining(c)).casefold()))


def number_key(value):
    text = str(value or "").strip()
    return str(int(text)) if text.isdigit() else text.casefold()


def time_hundredths(value):
    text = str(value or "").strip()
    # Reject annotated/non-finishes; accept published seconds or minute formats.
    match = re.fullmatch(r"(?:(\d+):)?(\d{1,2})(?:\.(\d{1,3}))?", text)
    if not match:
        return None
    minutes, seconds, fraction = match.groups()
    if minutes is not None and int(seconds) >= 60:
        return None
    result = int(minutes or 0) * 6000 + int(seconds) * 100 + int(((fraction or "") + "00")[:2])
    return result if result > 0 else None


def display_seed(value):
    if value is None:
        return "NT"
    return f"{int(value) // 6000:02d}:{int(value) // 100 % 60:02d}.{int(value) % 100:02d}"


def select_seed(db_path, athlete_id, discipline, distance, season_year):
    if athlete_id is None or distance is None:
        return None, "NT - no matched history"
    records = historical_performances(db_path, athlete_id, discipline, distance, season_year)
    return _select(records, season_year)


def _select(records, season_year):
    for year in (season_year, season_year - 1, season_year - 2):
        valid = []
        for row in records:
            # A DNF in the other discipline does not invalidate a real completed time.
            if re.search(r"\b(DQ|DSQ|DISQUALIFIED)\b", str(row.get("status", "")), re.I):
                continue
            value = time_hundredths(row["time"])
            if row["season_year"] == year and value is not None:
                valid.append((value, row))
        if valid:
            value, source = min(valid, key=lambda item: (item[0], item[1]["event_date"], item[1]["event_id"]))
            return value, f"{year} | {source['event_name']} | {source['event_date']}"
    return None, "NT - no valid matching distance in three seasons"


def prepare_entries(parsed, history_path, season_year, matches=None):
    """Link by athlete number; name differences are non-blocking notices.

    matches maps entry number to historical athlete ID or None (new/visiting).
    Source heat membership only determines discipline participation, never seeding.
    """
    snapshot = season_snapshot(history_path)
    history = snapshot["athletes"]
    performances = {}
    for result in snapshot["results"]:
        for discipline in ("run", "swim"):
            key = result["athlete_id"], discipline, result[f"{discipline}_distance"]
            performances.setdefault(key, []).append(dict(result, time=result[f"{discipline}_time"]))
    by_id = {a["id"]: a for a in history}
    matches = matches or {}
    prepared, ambiguities = [], []
    for entry in parsed["athletes"]:
        row = deepcopy(entry)
        number = row["athlete_number"]
        same_number = [a for a in history if number_key(a["athlete_number"]) == number_key(number)]
        same_name = [a for a in history if name_key(a["athlete_name"]) == name_key(row["athlete_name"])]
        candidates = {a["id"]: a for a in same_number + same_name}
        matched = None
        if number in matches:
            matched = matches[number]
            if matched is not None and matched not in by_id:
                raise ValueError("Selected historical athlete no longer exists.")
        elif len(same_number) == 1:
            matched = same_number[0]["id"]
            if name_key(same_number[0]["athlete_name"]) != name_key(row["athlete_name"]):
                ambiguities.append({"entry": row, "candidates": same_number, "number_matched": True})
        elif len(same_number) > 1:
            ambiguities.append({"entry": row, "candidates": list(candidates.values())})
        run, swim = distances(row.get("group_name"))
        for discipline,prefix in (("run","running"),("swim","swimming")):
            record=next((r for r in parsed.get(prefix+"_records",[]) if r["athlete_number"]==number),{})
            if record.get("distance"):
                row[discipline+"_distance"]=record["distance"]
        row.update(history_athlete_id=matched, gender=gender_for_group(row.get("group_name")),
                   run_distance=row.get("run_distance") or run, swim_distance=row.get("swim_distance") or swim,
                   run_entered=int(row.get("running_heat") is not None),
                   swim_entered=int(row.get("swimming_heat") is not None))
        for discipline in ("run", "swim"):
            records = performances.get((matched, discipline, row[f"{discipline}_distance"]), []) if matched else []
            seed, source = _select(records, season_year)
            row[f"{discipline}_seed"] = seed
            row[f"{discipline}_seed_source"] = source
        row.update(running_heat=None, running_lane=None, swimming_heat=None, swimming_lane=None)
        prepared.append(row)
    linked = [r["history_athlete_id"] for r in prepared if r["history_athlete_id"] is not None]
    if len(linked) != len(set(linked)):
        raise ValueError("Two entries resolve to the same historical athlete. Correct the entry identities before continuing.")
    return prepared, ambiguities
