"""School team selection from published season scores (never rescores results)."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
import re

from services.season_reports import category_key, completed_result, numeric_points, age_group_sort_key, attendance_qualification, score_qualification, compact_qualification_requirements

SCHOOL_RULES = {"Primary": ((9, 11, 13, 15), 2), "High": ((15, 17, 19), 3)}
SUMMARY_HEADERS = ["Rank", "School", "School type", "Total school points", "Qualified", "Missing to qualify",
                   "Mandatory places filled", "Extra places filled", "Qualified selected athletes",
                   "Full team", "Missing team members", "Missing Events", "Qualification requirements",
                   "Team athletes", "Highest scores", "All school athletes"]
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


def _place_requirements(team, selected, mandatory, extras):
    """Keep parallel position-based shortfalls, athlete names and best scores."""
    by_place = {selected[c["athlete"]["id"]]:c for c in team}
    places = [(f"Under-{age}",f"U/{age:02d}") for age in mandatory]
    places += [(f"Extra {i}",f"Extra {i}") for i in range(1,extras+1)]
    events,requirements,names,scores = [],[],[],[]
    for place,label in places:
        candidate = by_place.get(place)
        if candidate is None:
            message = f"{label}: athlete needed"
            events.append(message)
            requirements.append(message)
            names.append(f"{label}: Vacant")
            scores.append(f"{label}: —")
            continue
        athlete = candidate["athlete"]
        if place.startswith("Extra"):
            label += f" ({candidate['category']})"
        names.append(f"{label}: {athlete['athlete_name']} (#{athlete['athlete_number']})")
        score = f"{candidate['raw']:,.2f}"
        if candidate["points"] != candidate["raw"]:
            score += f" (counts {candidate['points']:,.2f})"
        scores.append(f"{label}: {score}")
        attendance = attendance_qualification(candidate["results"],required=4)
        events.append(f"{label}: {compact_qualification_requirements(attendance['Missing to qualify'])}")
        if candidate["missing"]:
            requirements.append(f"{label}: {compact_qualification_requirements(candidate['missing'])}")
    return tuple("\n".join(values) or "None" for values in (events,requirements,names,scores))


def _all_school_athletes(candidates):
    """One best completed season result per athlete, including non-team age groups."""
    rows = []
    for candidate in candidates:
        completed = [r for r in candidate["results"]
                     if completed_result(r) and numeric_points(r["total_points"]) is not None]
        if not completed:
            continue
        best = max(completed,key=lambda r:numeric_points(r["total_points"]))
        athlete = candidate["athlete"]
        points = numeric_points(best["total_points"])
        rows.append((age_group_sort_key(best["category"]),-points,athlete["athlete_name"],
                     f"{best['category']}: {athlete['athlete_name']} (#{athlete['athlete_number']}) — {points:,.2f}"))
    entries = [row[-1] for row in sorted(rows)]
    # Keep large school rosters within Excel's row-height limit.
    if len(entries) > 24:
        entries = [" | ".join(entries[i:i+2]) for i in range(0,len(entries),2)]
    return "\n".join(entries) or "None"


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
                                leagues=leagues, other=other, distinct=distinct,
                                missing=missing, qualified=not missing))
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
            if mandatory:
                pool = sorted([c for c in candidates if c["athlete"]["id"] not in selected and c["points"] is not None
                               and (c["age"] in mandatory or c["special"])], key=order)
                special_used = False
                for candidate in pool:
                    if candidate["special"] and special_used:
                        continue
                    if len(selected) == mandatory_filled + extras:
                        break
                    selected[candidate["athlete"]["id"]] = f"Extra {len(selected) - mandatory_filled + 1}"
                    special_used |= candidate["special"]
            team = [c for c in candidates if c["athlete"]["id"] in selected]
            extra_filled = len(team) - mandatory_filled
            missing = []
            if not mandatory:
                missing.append("School name must end in Ps (primary) or Hs (high) to determine team rules")
            if missing_groups:
                missing.append("Missing mandatory athlete(s): " + ", ".join(missing_groups))
            if mandatory and extra_filled < extras:
                missing.append(f"{extras - extra_filled} more eligible extra athlete(s)")
            for candidate in team:
                if candidate["missing"]:
                    missing.append(f"{candidate['athlete']['athlete_name']} ({candidate['athlete']['athlete_number']}): {candidate['missing']}")
            short_missing = [f"u/{int(group.split('-')[1]):02d}" for group in missing_groups]
            if not mandatory:
                short_missing.append("School type not identified")
            elif extra_filled < extras:
                short_missing.append(f"+ {extras - extra_filled}")
            event_summary, qualification_requirements, team_names, team_scores = _place_requirements(team,selected,mandatory,extras)
            if not mandatory:
                qualification_requirements = "School type needed: name must end in Ps or Hs"
            summaries.append({"Rank": "", "School": names[key], "School type": school_type,
                              "Total school points": float(sum((c["points"] for c in team), Decimal(0))) if mandatory else "",
                              "Qualified": "No" if missing else "Yes", "Missing to qualify": "; ".join(missing) or "None",
                              "Qualification summary": "; ".join(short_missing) or "None",
                              "Full team": "Yes" if mandatory and not missing_groups and extra_filled == extras else "No",
                              "Missing team members": "; ".join(short_missing) or "None",
                              "Missing Events": event_summary,
                              "Qualification requirements": qualification_requirements,
                              "Team athletes": team_names, "Highest scores": team_scores,
                              "All school athletes": _all_school_athletes(candidates),
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
