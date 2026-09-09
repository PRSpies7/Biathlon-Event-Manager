"""School team selection from published season scores (never rescores results)."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
import re

from services.season_reports import category_key, completed_result, numeric_points, age_group_sort_key, attendance_qualification, score_qualification

SCHOOL_RULES = {"Primary": ((9, 11, 13, 15), 2), "High": ((15, 17, 19), 3)}
SUMMARY_HEADERS = ["Rank", "School", "School type", "Total school points", "Qualified", "Missing to qualify",
                   "Mandatory places filled", "Extra places filled", "Qualified selected athletes"]
ATHLETE_HEADERS = ["School", "School type", "Selected", "Team place", "Athlete number", "Athlete name", "Age group",
                   "Affiliated", "Qualified", "Missing to qualify", "Completed league/championship meets", "Completed interprovincial or championship events",
                   "Completed distinct qualifying events",
                   "Best total points", "School contribution points", "Best event", "Best event date"]


def school_key(name):
    return " ".join(name.split()).casefold()


def school_type_from_name(name):
    suffix = re.search(r"\b(ps|hs)\s*$", name, re.I)
    return {"ps": "Primary", "hs": "High"}.get(suffix[1].casefold(), "Unassigned") if suffix else "Unassigned"


def school_attendance(results):
    qualification = attendance_qualification(results, required=4)
    return (qualification["Completed league events"] + qualification["Completed championship events"],
            qualification["Completed interprovincial events"] + qualification["Completed championship events"],
            "" if qualification["Qualified"] == "Yes" else qualification["Missing to qualify"],
            qualification["Completed distinct qualifying events"])


def qualified_schools_report(snapshot):
    """One athlete belongs to their latest reported school/category; no duplicate team places.

    Qualified candidates precede others in each mandatory group and in extras.
    Within those pools the highest published completed score wins. Special needs
    are eligible only for extras and are capped for selection and contribution.
    """
    by_athlete = defaultdict(list)
    for result in snapshot["results"]:
        by_athlete[result["athlete_id"]].append(result)
    schools = defaultdict(list)
    names = {}
    for athlete in snapshot["athletes"]:
        results = sorted(by_athlete[athlete["id"]], key=lambda r: (r["event_date"], r["event_id"]), reverse=True)
        if not results:
            continue
        school = next((r["school"].strip() for r in results if r["school"].strip()), athlete["school"].strip())
        if not school:
            continue
        key = school_key(school)
        names.setdefault(key, school)
        category = results[0]["category"]
        group = category_key(category)
        under = re.match(r"^U(\d+)\b", group)
        special = bool(re.search(r"\bSPECIAL\s*NEEDS?\b", group))
        eligible = [r for r in results if category_key(r["category"]) == group
                    and completed_result(r) and numeric_points(r["total_points"]) is not None]
        best = max(eligible, key=lambda r: numeric_points(r["total_points"]), default=None)
        raw = numeric_points(best["total_points"]) if best else None
        points = min(raw, Decimal(2000)) if special and raw is not None else raw
        leagues, other, missing, distinct = school_attendance(results)
        score_missing = score_qualification(results, category)
        if score_missing:
            missing = "; ".join(filter(None, (missing, score_missing)))
        schools[key].append(dict(athlete=athlete, category=category, age=int(under[1]) if under else None,
                                special=special, best=best, points=points, raw=raw, results=results,
                                leagues=leagues, other=other, distinct=distinct, missing=missing, qualified=not missing))
    events = sorted(snapshot["events"], key=lambda e: (e["event_date"], e["id"]))
    labels = {e["id"]: f"{e['name']} ({e['event_date']}) [{e['id']}]" for e in events}
    summaries, details = [], []

    def order(candidate):
        return (not candidate["qualified"], -candidate["points"], candidate["athlete"]["athlete_number"])

    for key, candidates in schools.items():
        types = (school_type_from_name(names[key]),)
        for school_type in types:
            mandatory, extras = SCHOOL_RULES.get(school_type, ((), 0))
            selected, missing_groups = {}, []
            for age in mandatory:
                pool = [c for c in candidates if c["age"] == age and not c["special"] and c["points"] is not None]
                if pool:
                    winner = min(pool, key=order)
                    selected[winner["athlete"]["id"]] = f"Under-{age}"
                else:
                    missing_groups.append(f"Under-{age}")
            mandatory_filled = len(selected)
            if mandatory and not missing_groups:
                pool = sorted([c for c in candidates if c["athlete"]["id"] not in selected and c["points"] is not None
                               and (c["age"] in mandatory or c["special"])], key=order)
                special_used = False
                for candidate in pool:
                    if candidate["special"] and special_used:
                        continue
                    if len(selected) == len(mandatory) + extras:
                        break
                    selected[candidate["athlete"]["id"]] = f"Extra {len(selected) - len(mandatory) + 1}"
                    special_used |= candidate["special"]
            team = [c for c in candidates if c["athlete"]["id"] in selected]
            extra_filled = len(team) - mandatory_filled
            missing = []
            if not mandatory:
                missing.append("School name must end in Ps (primary) or Hs (high) to determine team rules")
            if missing_groups:
                missing.append("Missing mandatory athlete(s): " + ", ".join(missing_groups))
                missing.append("Extra places omitted until all mandatory groups are filled")
            elif mandatory and extra_filled < extras:
                missing.append(f"{extras - extra_filled} more eligible extra athlete(s)")
            for candidate in team:
                if candidate["missing"]:
                    missing.append(f"{candidate['athlete']['athlete_name']} ({candidate['athlete']['athlete_number']}): {candidate['missing']}")
            summaries.append({"Rank": "", "School": names[key], "School type": school_type,
                              "Total school points": float(sum((c["points"] for c in team), Decimal(0))) if mandatory else "",
                              "Qualified": "No" if missing else "Yes", "Missing to qualify": "; ".join(missing) or "None",
                              "Mandatory places filled": f"{mandatory_filled}/{len(mandatory)}" if mandatory else "",
                              "Extra places filled": f"{extra_filled}/{extras}" if mandatory else "",
                              "Qualified selected athletes": f"{sum(c['qualified'] for c in team)}/6" if mandatory else ""})
            visible = [c for c in candidates if not mandatory or c["age"] in mandatory or c["special"]]
            for candidate in sorted(visible, key=lambda c: (age_group_sort_key(c["category"]), c["points"] is None, -(c["points"] or 0), c["athlete"]["athlete_number"])):
                athlete, best = candidate["athlete"], candidate["best"]
                chosen = athlete["id"] in selected
                row = {"School": names[key], "School type": school_type, "Selected": "Yes" if chosen else "No",
                       "Team place": selected.get(athlete["id"], ""), "Athlete number": athlete["athlete_number"],
                       "Athlete name": athlete["athlete_name"], "Age group": candidate["category"],
                       "Affiliated": "Affiliated" if athlete["affiliated"] else "Not Affiliated",
                       "Qualified": "Yes" if candidate["qualified"] else "No", "Missing to qualify": candidate["missing"] or "None",
                       "Completed league/championship meets": candidate["leagues"], "Completed interprovincial or championship events": candidate["other"],
                       "Completed distinct qualifying events": candidate["distinct"],
                       "Best total points": float(candidate["raw"]) if best else "",
                       "School contribution points": float(candidate["points"]) if chosen else 0,
                       "Best event": best["event_name"] if best else "",
                       "Best event date": date.fromisoformat(best["event_date"]) if best else ""}
                for result in candidate["results"]:
                    points = numeric_points(result["total_points"])
                    row[labels[result["event_id"]]] = float(points) if points is not None else result["total_points"]
                details.append(row)
    summaries.sort(key=lambda r: (r["Total school points"] == "", -(r["Total school points"] or 0), r["School"].casefold(), r["School type"]))
    previous, rank = None, 0
    for index, row in enumerate(summaries, 1):
        if row["Total school points"] != "":
            if previous != row["Total school points"]:
                rank = index
            row["Rank"] = rank
            previous = row["Total school points"]
    positions = {(r["School"], r["School type"]): i for i, r in enumerate(summaries)}
    details.sort(key=lambda r: positions[(r["School"], r["School type"])])
    return summaries, ATHLETE_HEADERS + list(labels.values()), details
