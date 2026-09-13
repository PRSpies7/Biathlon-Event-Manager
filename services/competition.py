"""Shared biathlon season, category and distance rules."""
from datetime import date
import re


def infer_season(value):
    day = value if isinstance(value, date) else date.fromisoformat(str(value))
    return day.year + (day.month >= 8)


def category_key(group):
    text = str(group or "").upper()
    match = re.search(r"\bU\s*/?\s*0?(8|9|10|11|12|13|15|17|19)\b", text)
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


# Lower values mean closer competition groups. Unlisted pairs stay separate.
COMPATIBILITY = {}
for family in (("MASTERS 40+", "MASTERS 50+"),
               ("MASTERS 60+", "MASTERS 70+", "MASTERS 80+"),
               ("U/08", "U/09", "U/10", "U/11"),
               ("U/12", "U/13", "U/15"), ("U/15", "U/17", "U/19"),
               ("U/19", "JNR", "SENIOR")):
    for left in family:
        for right in family:
            COMPATIBILITY[frozenset((left, right))] = 1
COMPATIBILITY[frozenset(("U/13", "U/17"))] = 2
COMPATIBILITY[frozenset(("U/13", "U/19"))] = 3
for youth in ("U/08", "U/09"):
    for masters in ("MASTERS 60+", "MASTERS 70+", "MASTERS 80+"):
        COMPATIBILITY[frozenset((youth, masters))] = 2


def compatibility(left, right):
    left, right = category_key(left) or left, category_key(right) or right
    return 0 if left == right else COMPATIBILITY.get(frozenset((left, right)))
