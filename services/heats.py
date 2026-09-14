"""Strict base heats, protection, compatible remainder merging and assignment.

Generation uses entries and seed times, never previous heat/lane assignments.
Profiles compare only valid arrangements; League may repack to remove heats.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from math import ceil
import json

from services.competition import category_key, category_order, compatibility, gender_for_group, distances
from services.competition import GENERATION_PROFILES, default_profile, running_capacity


DISCIPLINES = {"run": "running", "swim": "swimming"}
OLDER_GROUPS = {"MASTERS 60+", "MASTERS 70+", "MASTERS 80+", "SPECIAL NEEDS"}
RUN_CAPACITY = 12
SATISFACTORY_RUN_SIZE = 7  # Protection guideline, not a minimum valid heat size.
ACCEPTABLE_EMPTY_SWIM_LANES = {"Local": 1, "Interprovincial": 2}


def programme_order(group, gender, discipline):
    key = category_key(group) or group
    if key in OLDER_GROUPS:
        bucket = 0 if discipline == "run" else 1
    elif key == "U/08":
        bucket = 1 if discipline == "run" else 0
    else:
        sequence = ["U/09", "U/11"]
        if discipline == "swim":
            sequence += ["U/13"]
        sequence += ["JNR", "SENIOR", "MASTERS 40+", "MASTERS 50+"]
        sequence += ["U/13", "U/15", "U/17", "U/19"] if discipline == "run" else ["U/15", "U/17", "U/19"]
        bucket = sequence.index(key)+2 if key in sequence else 99
    return bucket, gender, category_order(group), key


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


def apply_heat_programme(entries, previous, event, discipline, programme, lane_overrides=(), *, validate=True):
    """Save a manual programme: remove empty heats, close gaps and seed positions.

    Programme rows have stable draft heat IDs; their list order is the requested
    programme order. Never run automatic grouping or drop an athlete. Explicit
    swim lane edits take priority over seeding within changed-membership heats.
    """
    rows = deepcopy(entries)
    prefix = DISCIPLINES[discipline]
    field, lane_field = prefix+"_heat", prefix+"_lane"
    occupied = {r[field] for r in rows if r.get(field) is not None}
    order = [p["Heat"] for p in programme]
    if len(order) != len(set(order)) or any(type(h) is not int or h < 1 for h in order):
        raise ValueError("Each programme heat must have a unique positive number.")
    deleted = {p["Heat"] for p in programme if p.get("Delete")}
    if occupied & deleted:
        raise ValueError("Move all athletes out before deleting Heat " + ", ".join(map(str, sorted(occupied & deleted))) + ".")
    if occupied - set(order):
        raise ValueError("Every assigned heat must appear in the heat programme.")
    if {r["athlete_number"] for r in rows} != {r["athlete_number"] for r in previous} or len(rows) != len(previous):
        raise ValueError("Heat changes must retain every athlete.")
    if discipline == "swim":
        old_members, new_members = defaultdict(set), defaultdict(set)
        for row in previous:
            if row.get(field) is not None:
                old_members[row[field]].add(row["athlete_number"])
        for row in rows:
            if row.get(field) is not None:
                new_members[row[field]].add(row["athlete_number"])
        overrides = set(lane_overrides)
        capacity = int(event["pool_lanes"])
        for heat, ids in new_members.items():
            members = [r for r in rows if r.get(field) == heat]
            if len(members) > capacity:
                raise ValueError(f"Swim Heat {heat} exceeds the pool capacity of {capacity} lanes.")
            if ids == old_members[heat]:
                continue  # Reordering a whole heat preserves its manual lanes.
            fixed = [r for r in members if r["athlete_number"] in overrides]
            reserved = [r[lane_field] for r in fixed]
            if len(reserved) != len(set(reserved)) or any(type(lane) is not int or not 1 <= lane <= capacity for lane in reserved):
                raise ValueError(f"Swim Heat {heat}: explicit lane edits must be unique and within the pool.")
            free = [lane for lane in centre_out(capacity) if lane not in reserved]
            for row, lane in zip(sorted((r for r in members if r["athlete_number"] not in overrides),
                                        key=lambda r: seed_order(r, "swim")), free):
                row[lane_field] = lane
    mapping = {heat: index for index, heat in enumerate((h for h in order if h in occupied), 1)}
    for row in rows:
        if row.get(field) is not None:
            row[field] = mapping[row[field]]
    if discipline == "run":
        rows = reseed_run_positions(rows)
    if validate:
        errors, _ = validate_heats(rows, event)
        if errors:
            raise ValueError("\n".join(errors))
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


def build_strict_groups(rows, discipline):
    """Partition participants by distance, category and gender before any mixing."""
    groups = defaultdict(list)
    for row in rows:
        if not row.get(f"{discipline}_entered"):
            continue
        key = (row[f"{discipline}_distance"], category_key(row["group_name"]) or row["group_name"], row["gender"])
        groups[key].append(row)
    return groups


def build_balanced_base_heats(groups, discipline, capacity):
    """Balance runs (16 -> 8+8); reserve full fast swims and a slow remainder."""
    heats = []
    for key in sorted(groups, key=lambda k: (*programme_order(k[1],k[2],discipline), k[0])):
        ranked = sorted(groups[key],key=lambda r:seed_order(r,discipline),reverse=True)
        count = ceil(len(ranked)/capacity)
        base, extra = divmod(len(ranked),count)
        offset = 0
        for index in range(count):
            # Reserve full, unmixed faster swim heats; the slower remainder can mix.
            size = (len(ranked)-capacity*(count-1) if index==0 else capacity) if discipline=="swim" else base + (index < extra)
            heats.append(ranked[offset:offset+size])
            offset += size
    return heats


def combine_selected_heats(entries, event, discipline, programme, selected):
    """Manually pool any number of selected same-distance heats and reseed them.

    Selected heats become a consecutive block at the first selected position.
    Other memberships stay unchanged. Slow/NT athletes precede full fast swims;
    runs use the usual balanced split, capped at twelve.
    """
    rows = deepcopy(entries)
    prefix = DISCIPLINES[discipline]
    selected = set(selected)
    ordered = [p["Heat"] for p in programme]
    if len(selected) < 2 or not selected <= set(ordered):
        raise ValueError("Select at least two heats to combine.")
    members = [r for r in rows if r.get(prefix+"_heat") in selected]
    if {r[prefix+"_heat"] for r in members} != selected:
        raise ValueError("Select heats containing athletes; empty heats disappear on save.")
    distances = {r.get(discipline+"_distance") for r in members}
    if len(distances) != 1 or None in distances:
        raise ValueError("Combined heats must use the same event distance.")
    capacity = RUN_CAPACITY if discipline == "run" else int(event["pool_lanes"])
    # This is an explicit manual selection, so category/gender mixing is allowed.
    heats = build_balanced_base_heats({(next(iter(distances)), "Manual selection", ""): members}, discipline, capacity)
    identifiers = [h for h in ordered if h in selected]
    next_heat = max(ordered, default=0)+1
    while len(identifiers) < len(heats):
        identifiers.append(next_heat)
        next_heat += 1
    identifiers = identifiers[:len(heats)]
    for heat, number in zip(heats, identifiers):
        lanes = range(len(heat), 0, -1) if discipline == "run" else centre_out(capacity)
        for row, lane in zip(sorted(heat, key=lambda r: seed_order(r, discipline)), lanes):
            row[prefix+"_heat"], row[prefix+"_lane"] = number, lane
    first = min(ordered.index(h) for h in selected)
    order = [h for h in ordered[:first] if h not in selected] + identifiers + [h for h in ordered[first:] if h not in selected]
    return rows, [{"Heat": h, "New Position": i, "Combine": False} for i, h in enumerate(order, 1)]


def protection_reason(heat, discipline, capacity, meet_type):
    if meet_type == "Local":
        return None  # Preferred structures may be repacked to eliminate a heat.
    """Explain why a heat cannot donate or receive athletes automatically."""
    if meet_type == "National":
        return "National age/gender groups remain separate."
    if len(heat) >= capacity:
        return "The heat is full."
    if discipline == "swim":
        if capacity-len(heat) <= ACCEPTABLE_EMPTY_SWIM_LANES[meet_type]:
            return "The number of empty swim lanes is acceptable."
    elif len(heat) >= SATISFACTORY_RUN_SIZE:
        return "Seven or more runners make a satisfactory heat."
    return None


def is_heat_protected(heat, discipline, capacity, meet_type):
    return protection_reason(heat, discipline, capacity, meet_type) is not None


def is_heat_eligible_for_optimisation(heat, discipline, capacity, meet_type):
    """Eligibility permits consideration; it never requires filling a heat."""
    return bool(heat) and not is_heat_protected(heat, discipline, capacity, meet_type)


def compatibility_tier(left, right, discipline):
    """Require a valid distance and category pair for EVERY athlete combination.

    A compatible intermediary never licenses an otherwise incompatible pair.
    """
    members = [*left, *right]
    distance_set = {a[f"{discipline}_distance"] for a in members}
    if len(distance_set) != 1 or not next(iter(distance_set)):
        return None
    distance = next(iter(distance_set))
    categories = sorted({a["group_name"] for a in members})
    tiers = [compatibility(a, b, discipline, distance)
             for index, a in enumerate(categories) for b in categories[index:]]
    return None if any(tier is None for tier in tiers) else max(tiers)


def _seed_gap(left, right, discipline):
    """Mean cross-group time gap; missing times never masquerade as a close seed."""
    first = [a.get(f"{discipline}_seed") for a in left]
    second = [a.get(f"{discipline}_seed") for a in right]
    gaps = [abs(a-b) for a in first for b in second if a is not None and b is not None]
    return sum(gaps)/len(gaps) if gaps else float("inf")


def rank_destination(left, right, discipline, capacity, meet_type):
    """Return ordered preferences, or None if this combination is not justified.

    League: category, gender, seeds, occupancy. Interprovincial allows same-gender
    strong/neighbouring pairs; cross-gender pairs must be same/strong categories
    AND form a satisfactory heat. Weak pairs remain separate at Interprovincials.
    Special Needs shares one flexible tier across same-distance destinations,
    so measured seed suitability decides after gender, without a Masters bias.
    """
    if not all(is_heat_eligible_for_optimisation(h, discipline, capacity, meet_type)
               for h in (left, right)) or len(left)+len(right) > capacity:
        return None
    tier = compatibility_tier(left, right, discipline)
    if tier is None:
        return None
    mixed_gender = len({a["gender"] for a in [*left, *right]}) > 1
    if meet_type == "Interprovincial":
        if tier > 2:
            return None
        if mixed_gender and (tier > 1 or not is_heat_protected(
                [*left, *right], discipline, capacity, meet_type)):
            return None
        # Same group/gender, compatible same gender, same category mixed,
        # then strong compatible mixed. Capacity cannot promote a lower tier.
        priority = (2 if tier == 0 else 3) if mixed_gender else (0 if tier == 0 else 1)
        grouping = (priority, tier)
    else:
        grouping = (tier, int(mixed_gender))
    return (*grouping, _seed_gap(left, right, discipline), capacity-len(left)-len(right))


def _heat_identity(heat):
    return tuple(sorted(str(a["athlete_number"]) for a in heat))


def optimise_heats(heats, discipline, capacity, meet_type):
    """Choose the best valid whole-remainder pair, then recheck protection.

    All eligible pairs compete before committing a merge, so programme order
    cannot steal an athlete's better destination. This is deterministic greedy
    selection, not training or an exhaustive search for maximum occupancy.
    """
    heats = [list(heat) for heat in heats]
    while True:
        eligible = [i for i, h in enumerate(heats)
                    if is_heat_eligible_for_optimisation(h, discipline, capacity, meet_type)]
        candidates = []
        for offset, left in enumerate(eligible):
            for right in eligible[offset+1:]:
                rank = rank_destination(heats[left], heats[right], discipline, capacity, meet_type)
                if rank is not None:
                    identity = tuple(sorted((_heat_identity(heats[left]), _heat_identity(heats[right]))))
                    candidates.append((rank, identity, left, right))
        if not candidates:
            return [h for h in heats if h]
        _, _, left, right = min(candidates)
        heats[left].extend(heats[right])
        heats[right] = []


def compatible_clusters(heats, discipline):
    """Enumerate maximal all-pairs-compatible category clusters, never graph paths.

    A bridge (including Special Needs) cannot legitimise an incompatible pair.
    Include pair/single-category alternatives so overlapping clusters can compete.
    """
    categories = sorted({category_key(a["group_name"]) or a["group_name"] for h in heats for a in h})
    distance = heats[0][0][discipline+"_distance"]
    neighbours = {c:{d for d in categories if c!=d and compatibility(c,d,discipline,distance) is not None} for c in categories}
    found = {frozenset([c]) for c in categories}
    found.update(frozenset((c,d)) for c in categories for d in neighbours[c])
    def visit(chosen, possible, excluded):
        if not possible and not excluded:
            found.add(frozenset(chosen))
        for c in sorted(possible.copy()):
            visit(chosen|{c},possible & neighbours[c],excluded & neighbours[c])
            possible.remove(c)
            excluded.add(c)
    visit(set(),set(categories),set())
    return sorted(found,key=lambda c:tuple(sorted(c)))


def arrangement_rank(heats, discipline, capacity, preferred):
    """Lexicographic comparison AFTER feasibility: count, then discipline policy.

    Running keeps gender/category ahead of seed spread; swimming puts measured
    seed coherence first. No absolute seed-gap cut-off or occupancy weight.
    """
    gender, age, spread, unknown = 0,0,0,0
    for heat in heats:
        known = sorted(a[discipline+"_seed"] for a in heat if a.get(discipline+"_seed") is not None)
        if known:
            mean = sum(known)/len(known)
            spread += sum((x-mean)**2 for x in known)
        unknown += len(known)*(len(heat)-len(known))
        genders = Counter(a["gender"] for a in heat)
        gender += genders["F"]*genders["M"]
        categories = Counter(a["group_name"] for a in heat)
        names = sorted(categories)
        for i,a in enumerate(names):
            for b in names[i+1:]:
                age += categories[a]*categories[b]*(compatibility(a,b,discipline,heat[0][discipline+"_distance"]) or 0)
    preference = (gender,age,unknown,spread) if discipline=="run" else (unknown,spread,gender,age)
    return (len(heats),*preference,sum(max(0,len(h)-preferred) for h in heats),
            sum((capacity-len(h))**2 for h in heats),tuple(sorted(_heat_identity(h) for h in heats)))


def repack_league_clusters(heats, discipline, capacity, preferred):
    """Repack whole compatible pools only when doing so removes at least one heat.

    Evaluate seed-, gender- and category-ordered partitions, comparing feasible
    alternatives lexicographically. Repeat the best reduction. This deterministic
    cluster search is intentionally not an unrestricted weighted optimiser.
    """
    while True:
        candidates = []
        for cluster in compatible_clusters(heats,discipline):
            for gender in (None,"F","M"):
                indexes = [i for i,h in enumerate(heats) if all(
                    (category_key(a["group_name"]) or a["group_name"]) in cluster and
                    (gender is None or a["gender"]==gender) for a in h)]
                members = [a for i in indexes for a in heats[i]]
                count = ceil(len(members)/capacity)
                if not members or count>=len(indexes):
                    continue
                base,extra = divmod(len(members),count)
                sizes = {tuple(base+(i<extra) for i in range(count)),
                         (len(members)-capacity*(count-1),)+(capacity,)*(count-1)}
                if len(members)>preferred*(count-1):
                    sizes.add((len(members)-preferred*(count-1),)+(preferred,)*(count-1))
                orderings = [lambda a:seed_order(a,discipline),
                    lambda a:(a["gender"],seed_order(a,discipline)),
                    lambda a:(category_key(a["group_name"]) or a["group_name"],a["gender"],seed_order(a,discipline))]
                for ordering in orderings:
                    ranked = sorted(members,key=ordering,reverse=True)
                    for partition in sorted(sizes):
                        if min(partition)<1 or max(partition)>capacity:
                            continue
                        packed,offset = [],0
                        for size in partition:
                            packed.append(ranked[offset:offset+size])
                            offset += size
                        # Explicit feasibility guard remains independent of ranking.
                        if any(compatibility_tier(h,[],discipline) is None for h in packed):
                            continue
                        result = [h for i,h in enumerate(heats) if i not in indexes]+packed
                        candidates.append((arrangement_rank(result,discipline,capacity,preferred),result,packed))
        if not candidates:
            return heats
        _,heats,packed = min(candidates,key=lambda c:c[0])
        anchor = min(a.get("_generation_order",programme_order(a["group_name"],a["gender"],discipline)) for h in packed for a in h)
        for h in packed:
            for a in h:
                a["_generation_order"] = anchor


def assign_positions_or_lanes(heats, discipline, capacity):
    """Apply programme order after grouping, then slow-to-fast heats and seeding."""
    def order(heat):
        programme = min(a.get("_generation_order",programme_order(a["group_name"], a["gender"], discipline)) for a in heat)
        seeds = [a.get(f"{discipline}_seed") for a in heat]
        known = [seed for seed in seeds if seed is not None]
        # NT heats precede fully seeded heats; larger times precede smaller times.
        return (programme, heat[0][f"{discipline}_distance"],
                not any(seed is None for seed in seeds),
                -sum(known)/len(known) if known else 0, _heat_identity(heat))
    prefix = DISCIPLINES[discipline]
    for number, heat in enumerate(sorted(heats, key=order), 1):
        lanes = range(len(heat), 0, -1) if discipline == "run" else centre_out(capacity)
        for row, lane in zip(sorted(heat, key=lambda r: seed_order(r, discipline)), lanes):
            row[prefix+"_heat"], row[prefix+"_lane"] = number, lane


def generate_heats(entries, event, *, optimise=True, profile=None):
    rows = deepcopy(entries)
    if event["meet_type"] not in {"Local","Interprovincial","National"}:
        raise ValueError("Select Local, Interprovincial or National event type.")
    profile = profile or default_profile(event["meet_type"])
    if profile not in GENERATION_PROFILES:
        raise ValueError("Select a valid heat generation profile.")
    policy = GENERATION_PROFILES[profile]
    for row in rows:
        if not row.get("group_name") or row.get("gender") not in {"F","M"}:
            raise ValueError(f"Confirm age group and gender for {row['athlete_name']}.")
        for discipline,prefix in DISCIPLINES.items():
            row[prefix+"_heat"] = row[prefix+"_lane"] = None
            if row.get(discipline+"_entered") and not row.get(discipline+"_distance"):
                raise ValueError(f"Confirm {discipline} distance for {row['athlete_name']}.")
    for discipline,prefix in DISCIPLINES.items():
        groups = build_strict_groups(rows, discipline)
        heats = []
        for distance in sorted({key[0] for key in groups}):
            preferred,capacity = running_capacity(distance) if discipline=="run" else (int(event["pool_lanes"]),)*2
            if capacity < 1:
                raise ValueError("Heat capacity must be positive.")
            base = build_balanced_base_heats({k:v for k,v in groups.items() if k[0]==distance},discipline,capacity)
            if optimise:
                base = (repack_league_clusters(base,discipline,capacity,preferred) if policy.repack_clusters else
                        optimise_heats(base,discipline,capacity,policy.competition))
            heats.extend(base)
        assign_positions_or_lanes(heats, discipline, int(event["pool_lanes"]))
        for row in rows:
            row.pop("_generation_order",None)
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
            warnings.append(f"{discipline.title()} Heat {heat}: manual combination of different distances; check operational arrangements.")
        run_limit = min(running_capacity(a.get("run_distance"))[1] for a in members)
        if discipline == "run" and len(members)>run_limit:
            warnings.append(f"Run Heat {heat} has {len(members)} runners, exceeding the distance's automatic maximum of {run_limit}.")
        if discipline == "run" and any(lane not in json.loads(event["run_positions"]) for lane in lanes):
            warnings.append(f"Run Heat {heat} uses a manually extended starting position.")
        if len({category_key(r["group_name"]) or r["group_name"] for r in members}) > 1:
            warnings.append(f"{discipline.title()} Heat {heat} combines age groups.")
        if len({r.get("gender") or gender_for_group(r.get("group_name")) for r in members}) > 1:
            warnings.append(f"{discipline.title()} Heat {heat} combines genders.")
    return errors,warnings
