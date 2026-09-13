"""Deterministic two-pass heat generation and validation, independent of Streamlit."""
from collections import defaultdict
from copy import deepcopy
from math import ceil
import json

from services.competition import category_key, category_order, compatibility, gender_for_group, distances


DISCIPLINES = {"run": "running", "swim": "swimming"}


def enrich_imported(rows):
    """Keep supplied assignments; supply metadata for validation and shared outputs."""
    rows=deepcopy(rows)
    for row in rows:
        run,swim=distances(row.get("group_name"))
        row["gender"]=row.get("gender") or gender_for_group(row.get("group_name"))
        row["run_distance"]=row.get("run_distance") or run
        row["swim_distance"]=row.get("swim_distance") or swim
        for discipline,prefix in DISCIPLINES.items():
            if row.get(discipline+"_entered") is None:
                row[discipline+"_entered"]=int(row.get(prefix+"_heat") is not None)
    for discipline,prefix in DISCIPLINES.items():
        for row in rows:
            if row.get(prefix+"_heat") is not None and row.get(discipline+"_distance") is None:
                known={a[discipline+"_distance"] for a in rows if a.get(prefix+"_heat")==row[prefix+"_heat"] and a.get(discipline+"_distance")}
                if len(known)==1:
                    row[discipline+"_distance"]=known.pop()
    return rows


def centre_out(lanes):
    if type(lanes) is not int or lanes < 1:
        raise ValueError("Pool lane count must be a positive integer.")
    centre = (lanes + 1) / 2
    return sorted(range(1,lanes+1), key=lambda lane: (abs(lane-centre),lane))


def seed_order(row, discipline):
    value = row.get(f"{discipline}_seed")
    return (value is None, value if value is not None else 0, str(row["athlete_number"]))


def _initial(rows, discipline, capacity):
    groups = defaultdict(list)
    for row in rows:
        if not row.get(f"{discipline}_entered"):
            continue
        key = (row[f"{discipline}_distance"], category_key(row["group_name"]) or row["group_name"], row["gender"])
        groups[key].append(row)
    heats = []
    for key in sorted(groups, key=lambda k: (k[0],category_order(k[1]),k[1],k[2])):
        ranked = sorted(groups[key],key=lambda r:seed_order(r,discipline),reverse=True)
        count = ceil(len(ranked)/capacity)
        base, extra = divmod(len(ranked),count)
        offset = 0
        for index in range(count):
            size = base + (index < extra)
            heats.append(ranked[offset:offset+size])
            offset += size
    return heats


def _eligible(heat, discipline, capacity, meet_type):
    if meet_type == "National":
        return False
    if discipline == "swim":
        return capacity-len(heat) >= (3 if meet_type == "Interprovincial" else 2)
    return len(heat) <= 6 if meet_type == "Interprovincial" else len(heat) < capacity


def _candidate_score(target, row, discipline, meet_type):
    if any(a[f"{discipline}_distance"] != row[f"{discipline}_distance"] for a in target):
        return None
    ranks = [compatibility(a["group_name"],row["group_name"]) for a in target]
    if any(rank is None for rank in ranks):
        return None
    # Younger children/older masters pairing applies specifically to the 400m run.
    keys = {category_key(a["group_name"]) for a in [*target,row]}
    if any(k in {"U/08","U/09"} for k in keys) and any(k and k.startswith("MASTERS") for k in keys):
        if discipline != "run" or row[f"{discipline}_distance"] != 400:
            return None
    gender = 0 if all(a["gender"] == row["gender"] for a in target) else 1
    seeds = [a.get(f"{discipline}_seed") for a in target if a.get(f"{discipline}_seed") is not None]
    seed = row.get(f"{discipline}_seed")
    difference = abs(seed-sum(seeds)/len(seeds)) if seed is not None and seeds else float("inf")
    rank = max(ranks)
    return (gender,rank,difference) if meet_type == "Interprovincial" else (rank,gender,difference)


def optimise_heats(heats, discipline, capacity, meet_type):
    """Move compatible entrants only out of incomplete groups; never chase full lanes.

    Consolidate toward earlier heats. Donor eligibility is also required so an
    otherwise acceptable heat is not dismantled simply to fill another heat.
    """
    if meet_type == "National":
        return heats
    eligible = {i for i,h in enumerate(heats) if _eligible(h,discipline,capacity,meet_type)}
    for index in sorted(eligible):
        target = heats[index]
        if not target:
            continue
        while len(target) < capacity:
            candidates = []
            for donor in sorted(eligible):
                if donor <= index or not heats[donor]:
                    continue
                for row in heats[donor]:
                    score = _candidate_score(target,row,discipline,meet_type)
                    if score is not None:
                        candidates.append((score, len(heats[donor]), donor, str(row["athlete_number"]), row))
            if not candidates:
                break
            _,_,donor,_,row = min(candidates,key=lambda c:c[:-1])
            target.append(row)
            heats[donor].remove(row)
    return [h for h in heats if h]


def generate_heats(entries, event, *, optimise=True):
    rows = deepcopy(entries)
    positions = list(range(1,13))
    if event["meet_type"] not in {"Local","Interprovincial","National"}:
        raise ValueError("Select Local, Interprovincial or National event type.")
    for row in rows:
        if not row.get("group_name") or row.get("gender") not in {"F","M"}:
            raise ValueError(f"Confirm age group and gender for {row['athlete_name']}.")
        for discipline,prefix in DISCIPLINES.items():
            row[prefix+"_heat"] = row[prefix+"_lane"] = None
            if row.get(discipline+"_entered") and not row.get(discipline+"_distance"):
                raise ValueError(f"Confirm {discipline} distance for {row['athlete_name']}.")
    for discipline,prefix in DISCIPLINES.items():
        capacity = min(12,len(positions)) if discipline == "run" else int(event["pool_lanes"])
        if capacity < 1:
            raise ValueError("Heat capacity must be positive.")
        heats = _initial(rows,discipline,capacity)
        if optimise:
            heats = optimise_heats(heats,discipline,capacity,event["meet_type"])
        lanes = list(reversed(positions)) if discipline == "run" else centre_out(capacity)
        for number,heat in enumerate(heats,1):
            for row,lane in zip(sorted(heat,key=lambda r:seed_order(r,discipline)),lanes):
                row[prefix+"_heat"],row[prefix+"_lane"] = number,lane
    return rows


def validate_heats(rows,event):
    errors,warnings = [],[]
    groups = defaultdict(list)
    for row in rows:
        for discipline,prefix in DISCIPLINES.items():
            heat,lane = row.get(prefix+"_heat"),row.get(prefix+"_lane")
            entered = row.get(discipline+"_entered")
            if entered and heat is None:
                errors.append(f"{row['athlete_name']}: missing {discipline} heat.")
            if heat is None:
                continue
            if type(heat) is not int or heat < 1 or type(lane) is not int or lane < 1:
                errors.append(f"{row['athlete_name']}: {discipline} heat and starting position must be positive integers.")
            if discipline == "swim" and (lane is None or lane > int(event["pool_lanes"])):
                errors.append(f"{row['athlete_name']}: swim lane is outside the pool.")
            if discipline == "swim" and row.get("swim_distance") not in {25,50,100}:
                errors.append(f"{row['athlete_name']}: confirm a supported swim distance (25, 50 or 100 m).")
            groups[discipline,heat].append(row)
    for (discipline,heat),members in groups.items():
        prefix = DISCIPLINES[discipline]
        lanes = [r[prefix+"_lane"] for r in members]
        if len(lanes) != len(set(lanes)):
            errors.append(f"{discipline.title()} Heat {heat}: duplicate starting positions/lanes.")
        if len({r.get(discipline+"_distance") for r in members}) > 1:
            errors.append(f"{discipline.title()} Heat {heat}: different distances cannot share a heat.")
        if discipline == "run" and len(members)>12:
            warnings.append(f"Run Heat {heat} has {len(members)} runners, exceeding the automatic maximum of 12.")
        if discipline == "run" and any(lane not in json.loads(event["run_positions"]) for lane in lanes):
            warnings.append(f"Run Heat {heat} uses a manually extended starting position.")
        if len({category_key(r["group_name"]) or r["group_name"] for r in members}) > 1:
            warnings.append(f"{discipline.title()} Heat {heat} combines age groups.")
        if len({r.get("gender") or gender_for_group(r.get("group_name")) for r in members}) > 1:
            warnings.append(f"{discipline.title()} Heat {heat} combines genders.")
    return errors,warnings
