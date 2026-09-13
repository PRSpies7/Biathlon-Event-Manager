"""Deterministic two-pass heat generation and validation, independent of Streamlit."""
from collections import defaultdict
from copy import deepcopy
from math import ceil
import json

from services.competition import category_key, category_order, compatibility, gender_for_group, distances


DISCIPLINES = {"run": "running", "swim": "swimming"}
OLDER_GROUPS = {"MASTERS 60+", "MASTERS 70+", "MASTERS 80+", "SPECIAL NEEDS"}


def programme_order(group, gender, discipline):
    key = category_key(group) or group
    if key in OLDER_GROUPS:
        bucket = 0 if discipline == "run" else 1
    elif key == "U/08":
        bucket = 1 if discipline == "run" else 0
    else:
        sequence = ["U/09", "U/10", "U/11", "U/12"]
        if discipline == "swim":
            sequence += ["U/13"]
        sequence += ["JNR", "SENIOR", "MASTERS 40+", "MASTERS 50+"]
        sequence += ["U/13", "U/15", "U/17", "U/19"] if discipline == "run" else ["U/15", "U/17", "U/19"]
        bucket = sequence.index(key)+2 if key in sequence else 99
    return bucket, gender, category_order(group), key


def heat_capacity(heat, discipline, capacity, meet_type):
    if discipline == "run" and meet_type == "Local" and any(category_key(a["group_name"]) in OLDER_GROUPS for a in heat):
        return min(10, capacity)
    return capacity


def reorder_heat(entries, discipline, heat_number, new_position):
    """Insert a whole heat at a programme position, retaining its assignments."""
    rows = deepcopy(entries)
    field = DISCIPLINES[discipline]+"_heat"
    order = sorted({r[field] for r in rows if r.get(field) is not None})
    if heat_number not in order or not 1 <= new_position <= len(order):
        raise ValueError("Choose an existing heat and a position in the programme.")
    if order.index(heat_number) == new_position-1:
        return rows
    order.remove(heat_number)
    order.insert(new_position-1,heat_number)
    mapping = {old:new for new,old in enumerate(order,1)}
    for row in rows:
        if row.get(field) is not None:
            row[field] = mapping[row[field]]
    return rows


def reseed_run_positions(entries):
    """Keep heat membership and assign contiguous positions, fastest outermost."""
    rows = deepcopy(entries)
    heats = defaultdict(list)
    for row in rows:
        if row.get("running_heat") is not None:
            heats[row["running_heat"]].append(row)
    for members in heats.values():
        for row, position in zip(sorted(members,key=lambda r:seed_order(r,"run")),range(len(members),0,-1)):
            row["running_lane"] = position
    return rows


def move_or_swap(entries, event, discipline, athlete_number, target_heat, swap_number=None):
    """Change membership and reseed only the affected heats; keep other manual edits."""
    rows = deepcopy(entries)
    prefix = DISCIPLINES[discipline]
    selected = next(a for a in rows if a["athlete_number"] == athlete_number)
    affected = {selected.get(prefix+"_heat")}
    if swap_number:
        other = next(a for a in rows if a["athlete_number"] == swap_number)
        selected[prefix+"_heat"], other[prefix+"_heat"] = other[prefix+"_heat"], selected[prefix+"_heat"]
    else:
        selected[prefix+"_heat"] = int(target_heat)
    affected.add(selected[prefix+"_heat"])
    for heat in affected:
        if heat is None:
            continue
        members = [a for a in rows if a.get(prefix+"_heat") == heat]
        if discipline == "swim" and len(members) > int(event["pool_lanes"]):
            raise ValueError("The destination swim heat is full. Swap athletes or choose another heat.")
        positions = range(len(members),0,-1) if discipline == "run" else centre_out(int(event["pool_lanes"]))
        for row, lane in zip(sorted(members,key=lambda a:seed_order(a,discipline)), positions):
            row[prefix+"_lane"] = lane
    errors, _ = validate_heats(rows,event)
    if errors:
        raise ValueError("\n".join(errors))
    return rows


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


def _initial(rows, discipline, capacity, meet_type="Local"):
    groups = defaultdict(list)
    for row in rows:
        if not row.get(f"{discipline}_entered"):
            continue
        key = (row[f"{discipline}_distance"], category_key(row["group_name"]) or row["group_name"], row["gender"])
        groups[key].append(row)
    heats = []
    for key in sorted(groups, key=lambda k: (*programme_order(k[1],k[2],discipline), k[0])):
        ranked = sorted(groups[key],key=lambda r:seed_order(r,discipline),reverse=True)
        count = ceil(len(ranked)/heat_capacity(ranked,discipline,capacity,meet_type))
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
    def rank_for(a):
        left, right = category_key(a["group_name"]), category_key(row["group_name"])
        pair = {left,right}
        if "SPECIAL NEEDS" in pair:
            if pair <= OLDER_GROUPS:
                return 1
            if discipline == "run" and meet_type == "Local" and pair <= {"SPECIAL NEEDS","U/08","U/09"}:
                return 2
        return compatibility(a["group_name"],row["group_name"])
    ranks = [rank_for(a) for a in target]
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
    opening_run = discipline == "run" and meet_type == "Local" and any(k in OLDER_GROUPS for k in keys)
    return (gender,rank,difference) if meet_type == "Interprovincial" or opening_run else (rank,gender,difference)


def optimise_heats(heats, discipline, capacity, meet_type):
    """Move compatible entrants only out of incomplete groups; never chase full lanes.

    Consolidate toward earlier heats. Donor eligibility is also required so an
    otherwise acceptable heat is not dismantled simply to fill another heat.
    """
    if meet_type == "National":
        return heats
    eligible = {i for i,h in enumerate(heats) if _eligible(h,discipline,heat_capacity(h,discipline,capacity,meet_type),meet_type)}
    for index in sorted(eligible):
        target = heats[index]
        if not target:
            continue
        while len(target) < heat_capacity(target,discipline,capacity,meet_type):
            candidates = []
            for donor in sorted(eligible):
                if donor <= index or not heats[donor]:
                    continue
                for row in heats[donor]:
                    if len(target)+1 > heat_capacity([*target,row],discipline,capacity,meet_type):
                        continue
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
        heats = _initial(rows,discipline,capacity,event["meet_type"])
        if optimise:
            heats = optimise_heats(heats,discipline,capacity,event["meet_type"])
        for number,heat in enumerate(heats,1):
            lanes = range(len(heat),0,-1) if discipline == "run" else centre_out(capacity)
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
