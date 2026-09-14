"""Shared biathlon season, category and distance rules."""
from datetime import date
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class GenerationPolicy:
    label: str
    description: str
    competition: str
    repack_clusters: bool = False


GENERATION_PROFILES = {
    "league": GenerationPolicy("League — Efficient", "Reduce the number of heats while keeping combinations competitively sensible.", "Local", True),
    "interprovincial": GenerationPolicy("Interprovincial — Conservative", "Prioritise age group and gender separation; incomplete heats are acceptable.", "Interprovincial"),
    "sa_champs": GenerationPolicy("SA Champs — Strict", "Keep age groups and genders separate automatically.", "National"),
}


def default_profile(meet_type):
    return {"Local":"league", "Interprovincial":"interprovincial", "National":"sa_champs"}[meet_type]


def running_capacity(distance):
    """Preferred and hard automatic sizes; retain 12 for nonstandard distances."""
    return {400:(10,12), 800:(12,15)}.get(distance,(12,12))


def infer_season(value):
    day = value if isinstance(value, date) else date.fromisoformat(str(value))
    return day.year + (day.month >= 8)


def category_key(group):
    text = str(group or "").upper()
    if re.search(r"\bSPECIAL\s+NEEDS\b", text):
        return "SPECIAL NEEDS"
    match = re.search(r"\bU\s*/?\s*0?(8|9|11|13|15|17|19)\b", text)
    if match:
        return f"U/{int(match[1]):02d}"
    match = re.search(r"\bMASTERS?\s*(40|50|60|70|80)\s*\+?", text)
    if match:
        return f"MASTERS {match[1]}+"
    if re.search(r"\b(JNR|JUNIOR)\b", text):
        return "JNR"
    if re.search(r"\bSENIORS?\b", text):
        return "SENIOR"
    return None


def gender_for_group(group):
    text = str(group or "").upper()
    if re.search(r"\b(GIRLS?|WOMEN|WOMAN|LADIES|LADY|FEMALE)\b", text):
        return "F"
    if re.search(r"\b(BOYS?|MEN|MAN|MALE)\b", text):
        return "M"
    return ""


def distances(group):
    key = category_key(group)
    if key is None:
        return None, None
    if key == "SPECIAL NEEDS":
        return 400, 50
    short_masters = key in {"MASTERS 60+", "MASTERS 70+", "MASTERS 80+"}
    age = int(key[2:]) if key.startswith("U/") else None
    run = 400 if short_masters or (age is not None and age <= 11) else 800
    swim = 25 if age == 8 else 50 if short_masters or (age is not None and age <= 13) else 100
    return run, swim


def category_order(group):
    key = category_key(group)
    if key and key.startswith("U/"):
        return int(key[2:])
    return {"JNR": 20, "SENIOR": 30, "MASTERS 40+": 40, "MASTERS 50+": 50,
            "MASTERS 60+": 60, "MASTERS 70+": 70, "MASTERS 80+": 80}.get(key, 99)


# Automatic compatibility tiers: 0 same category, 1 strong, 2 neighbouring,
# 3 weak/last resort. Unlisted pairs are incompatible, regardless of occupancy.
OLDER_MASTERS = ("MASTERS 60+", "MASTERS 70+", "MASTERS 80+")
ADULT_GROUPS = ("JNR", "SENIOR", "MASTERS 40+", "MASTERS 50+")
COMPATIBILITY = {("run", 400): {}, ("run", 800): {},
                 ("swim", 25): {}, ("swim", 50): {}, ("swim", 100): {}}


def _add_family(table, family):
    for left in family:
        for right in family:
            if left != right:
                table[frozenset((left, right))] = 1


for scope in (("run", 400), ("swim", 50)):
    _add_family(COMPATIBILITY[scope], OLDER_MASTERS)
for scope in (("run", 800), ("swim", 100)):
    table = COMPATIBILITY[scope]
    _add_family(table, ("U/15", "U/17", "U/19"))
    _add_family(table, ADULT_GROUPS)
    for adult in ADULT_GROUPS:
        table[frozenset(("U/19", adult))] = 2
        table[frozenset(("U/17", adult))] = 3
for scope, pairs in {
    ("run", 400): (("U/08", "U/09", 1), ("U/09", "U/11", 2), ("U/08", "U/11", 3)),
    ("run", 800): (("U/13", "U/15", 1), ("U/13", "U/17", 2), ("U/13", "U/19", 3)),
    ("swim", 50): (("U/09", "U/11", 1), ("U/11", "U/13", 2), ("U/09", "U/13", 3)),
}.items():
    for left, right, tier in pairs:
        COMPATIBILITY[scope][frozenset((left, right))] = tier


def compatibility(left, right, discipline, distance):
    """Category tier within a discipline/distance; callers enforce equal distances.

    Special Needs has equally valid same-distance destinations, allowing gender
    and measured seed suitability to choose rather than a fixed Masters route.
    """
    left, right = category_key(left), category_key(right)
    if left is None or right is None:
        return None
    if left == right:
        return 0
    if "SPECIAL NEEDS" in (left, right):
        return 2
    return COMPATIBILITY.get((discipline, distance), {}).get(frozenset((left, right)))
