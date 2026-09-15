"""Explicit test-event helpers; never called during normal result ingestion."""
from random import Random

from database.db import get_conn, audit
from database.repository import get_athletes, get_run_groups, save_run_positions, update_run_times, update_swim_times
from services.seeding import time_hundredths, display_seed


def contains_test_data(db_path, event_id):
    with get_conn(db_path) as conn:
        return conn.execute("SELECT 1 FROM audit_log WHERE event_id=? AND action='TEST_DATA_GENERATED' LIMIT 1",(event_id,)).fetchone() is not None


def generate_test_positions(db_path, event_id, rng=None):
    """Fill blank finish positions, retaining saved combined groups and positions."""
    rng = rng or Random()
    rows = get_athletes(db_path,event_id)
    groups = get_run_groups(db_path,event_id)
    units = [g["heat_numbers"] for g in groups]
    covered = {h for unit in units for h in unit}
    units += [[h] for h in sorted({r["running_heat"] for r in rows if r["running_heat"] is not None}-covered)]
    if sum(map(len,units))!=len({h for unit in units for h in unit}):
        raise ValueError("Resolve overlapping combined run groups before generating test positions.")
    count = 0
    for unit in units:
        members = [r for r in rows if r["running_heat"] in unit]
        used = {r["run_position"] for r in members if r["run_position"] is not None}
        missing = [r for r in members if r["run_position"] is None]
        rng.shuffle(missing)
        positions = {r["athlete_number"]:r["run_position"] for r in members}
        next_position = 1
        for row in missing:
            while next_position in used:
                next_position += 1
            positions[row["athlete_number"]] = next_position
            used.add(next_position)
            count += 1
        if missing:
            save_run_positions(db_path,event_id,unit,positions)
    if count:
        audit(db_path,event_id,"TEST_DATA_GENERATED",f"Synthetic finish positions: {count}")
    return count


def generate_test_results(db_path, event_id, rng=None):
    """Fill only missing times for entered disciplines, preserving real results."""
    rng = rng or Random()
    rows = get_athletes(db_path,event_id)
    updates = {"run":{},"swim":{}}
    for row in rows:
        for discipline,prefix,seconds_per_metre in (("run","running",.25),("swim","swimming",.8)):
            if row.get(discipline+"_time") or row.get(discipline+"_time_manual"):
                continue
            if not (row.get(discipline+"_entered") or row.get(prefix+"_heat") is not None):
                continue
            seed = row.get(discipline+"_seed")
            base = seed or int((row.get(discipline+"_distance") or (400 if discipline=="run" else 50))*seconds_per_metre*100)
            updates[discipline][row["athlete_number"]] = display_seed(max(100,int(base*rng.uniform(.9,1.15))))
    if updates["run"]:
        update_run_times(db_path,event_id,updates["run"])
    if updates["swim"]:
        update_swim_times(db_path,event_id,updates["swim"])
    count = sum(map(len,updates.values()))
    if count:
        audit(db_path,event_id,"TEST_DATA_GENERATED",f"Synthetic result times: {count}")
    return count


def result_indicator(row, peers=()):
    """Colour-only summary; relative outliers prompt review, never reject data."""
    times = [time_hundredths(row.get(d+"_time")) for d in ("run","swim")]
    if not any(row.get(d+"_time") for d in ("run","swim")):
        return "🔴"
    if not all(t is not None and t>0 for t in times):
        return "🟠"
    for discipline,value in zip(("run","swim"),times):
        seed = row.get(discipline+"_seed")
        if seed and (value<seed/2 or value>seed*2):
            return "🟠"
        from statistics import median
        from services.competition import category_key
        prefix = "running" if discipline=="run" else "swimming"
        comparable = [other for other in peers if other.get("athlete_number")!=row.get("athlete_number")
            and row.get(discipline+"_distance") and other.get(discipline+"_distance")==row[discipline+"_distance"]]
        for same_group in (False,True):
            if same_group:
                cohort = [other for other in comparable if
                    category_key(other.get("group_name"))==category_key(row.get("group_name"))
                    and category_key(row.get("group_name")) is not None and other.get("gender")==row.get("gender")]
            else:
                cohort = [other for other in comparable if row.get(prefix+"_heat") is not None and other.get(prefix+"_heat")==row[prefix+"_heat"]]
            valid = [time_hundredths(other.get(discipline+"_time")) for other in cohort]
            valid = [t for t in valid if t is not None and t>0]
            if len(valid)>=3 and (value<median(valid)/2 or value>median(valid)*2):
                return "🟠"
    return "🟢"
