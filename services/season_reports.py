"""Season report projections using published results and user-defined rules."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
import re

from parsers.season_results.models import INTERPROVINCIAL, LEAGUE, is_gn_championship
from services.season_results_service import athlete_rows
from parsers.season_records import category_key, record_category_key

RECORD_REPORT_HEADERS = ["Age group", "Athlete number", "Athlete name", "Event", "Event date", "Total points",
                         "Reference athlete number", "Reference athlete name", "Reference points", "Points above reference", "Record comparison",
                         "School", "Run time", "Swim time"]
QUALIFICATION_COLUMNS = ["Qualified", "Missing to qualify"]


def numeric_points(value):
    try:
        points = Decimal(str(value))
        return points if points.is_finite() else None
    except InvalidOperation:
        return None


def age_group_sort_key(category):
    key = category_key(category)
    under = re.match(r"^U(\d+)\b", key)
    masters = re.match(r"^MASTERS\s*(\d+)", key)
    if under:
        age = int(under.group(1))
    elif key.startswith("JUNIORS"):
        age = 20
    elif key.startswith("SENIORS"):
        age = 30
    elif masters:
        age = int(masters.group(1))
    else:
        age = 999  # Categories without an age, such as Special Needs, follow age groups.
    return age, key


def report_sort_key(row):
    points = numeric_points(row.get("Total points", row.get("total_points", "")))
    return (age_group_sort_key(row.get("Age group", row.get("Category", row.get("category", "")))),
            points is None, -points if points is not None else 0,
            str(row.get("Athlete name", row.get("athlete_name", ""))).casefold(),
            str(row.get("Athlete number", row.get("athlete_number", ""))))


def athlete_result_rows(snapshot):
    """One athlete row with a single, clearly identified best result in their latest age group."""
    results = defaultdict(list)
    for result in snapshot["results"]:
        results[result["athlete_number"]].append(result)
    rows = []
    for summary in athlete_rows(snapshot):
        entries = results[summary["Athlete number"]]
        latest = max(entries, key=lambda r: (r["event_date"], r["event_id"])) if entries else None
        category = latest["category"] if latest else summary["Category"]
        candidates = [r for r in entries if category_key(r["category"]) == category_key(category)]
        best = min(candidates, key=report_sort_key) if candidates else {}
        row = {("Age group" if k == "Category" else k): v for k, v in summary.items()}
        row.update({"Age group": category, "Run time": best.get("run_time", ""),
                    "Swim time": best.get("swim_time", ""),
                    "Total points": float(numeric_points(best["total_points"])) if numeric_points(best.get("total_points")) is not None else best.get("total_points", ""),
                    "Result event": f"{best['event_name']} ({best['event_date']})" if best else ""})
        rows.append(row)
    return sorted(rows, key=report_sort_key)


def qualified_report_rows(snapshot):
    return qualified_athlete_report(snapshot)[1]


def qualified_athlete_report(snapshot):
    """Best-score athlete summaries with qualification; event detail stays in Top Athletes."""
    headers, top_rows = top_athlete_report(snapshot)
    headers = headers[:10]  # Identity, affiliation, attendance and highest total only.
    qualifications = {r["Athlete number"]: r for r in qualification_rows(snapshot)}
    rows = []
    for row in top_rows:
        qualification = qualifications[row["Athlete number"]]
        rows.append({**row, "Qualified": qualification["Qualified"],
                     "Missing to qualify": qualification["Missing to qualify"]})
    headers = list(headers)
    headers.insert(headers.index("Athlete name") + 1, "Qualified")
    headers.append("Missing to qualify")
    return headers, [{h: row[h] for h in headers} for row in rows]


def top_athlete_report(snapshot):
    """All athletes per age group; event columns exist only in this report projection."""
    events = sorted(snapshot["events"], key=lambda e: (e["event_date"], e["id"]))
    labels = {}
    for event in events:
        label = f"{event['name']} ({event['event_date']})"
        if label in labels.values():
            label += f" [{event['competition_type']}, {event['id']}]"
        labels[event["id"]] = label
    headers = ["Rank", "Athlete number", "Athlete name", "Age group", "School", "Province", "Team",
               "Affiliated", "Events attended", "Highest total points", *labels.values()]
    athletes = {a["id"]: a for a in snapshot["athletes"]}
    grouped = defaultdict(dict)
    for result in snapshot["results"]:
        grouped[(result["athlete_id"], category_key(result["category"]))][result["event_id"]] = result
    ranked = []
    for (athlete_id, _), by_event in grouped.items():
        athlete = athletes[athlete_id]
        results = list(by_event.values())
        latest = max(results, key=lambda r: (r["event_date"], r["event_id"]))
        scores = [numeric_points(r["total_points"]) for r in results]
        highest = max((p for p in scores if p is not None), default=None)
        row = {"Rank": "", "Athlete number": athlete["athlete_number"], "Athlete name": athlete["athlete_name"],
               "Age group": latest["category"], "School": athlete["school"] or latest["school"],
               "Province": athlete["province"], "Team": athlete["team"],
               "Affiliated": "Affiliated" if athlete["affiliated"] else "Not Affiliated",
               "Events attended": len(by_event), "Highest total points": float(highest) if highest is not None else ""}
        for event in events:
            result = by_event.get(event["id"])
            points = numeric_points(result["total_points"]) if result else None
            row[labels[event["id"]]] = float(points) if points is not None else result["total_points"] if result else ""
        ranked.append((row, highest))
    ranked.sort(key=lambda item: (age_group_sort_key(item[0]["Age group"]), item[1] is None,
                                  -item[1] if item[1] is not None else 0, item[0]["Athlete name"].casefold(), item[0]["Athlete number"]))
    previous_group, previous_score, position, rank = None, None, 0, 0
    for row, score in ranked:
        group = category_key(row["Age group"])
        if group != previous_group:
            position, rank, previous_score = 0, 0, None
        position += 1
        if score is not None:
            if score != previous_score:
                rank = position
            row["Rank"] = rank
        previous_group, previous_score = group, score
    return headers, [row for row, _ in ranked]


def record_comparison_rows(snapshot):
    references = {record_category_key(r["category"]): r for r in snapshot.get("records", [])}
    schools = {a["athlete_number"]: a["school"] for a in snapshot["athletes"]}
    matches = []
    for result in snapshot["results"]:
        reference = references.get(record_category_key(result["category"]))
        if not reference:
            continue
        try:
            points, benchmark = Decimal(result["total_points"]), Decimal(reference["total_points"])
            if not points.is_finite() or points < benchmark:
                continue
        except InvalidOperation:
            continue
        matches.append({"Age group": result["category"], "Athlete number": result["athlete_number"],
                        "Athlete name": result["athlete_name"], "Event": result["event_name"],
                        "Event date": date.fromisoformat(result["event_date"]), "Total points": float(points),
                        "Reference athlete number": reference["athlete_number"], "Reference athlete name": reference["athlete_name"],
                        "Reference points": float(benchmark), "Points above reference": float(points - benchmark),
                        "Record comparison": "Exceeded" if points > benchmark else "Equalled",
                        "School": result["school"] or schools.get(result["athlete_number"], ""),
                        "Run time": result["run_time"], "Swim time": result["swim_time"]})
    return sorted(matches, key=report_sort_key)


def completed_result(result):
    if re.search(r"\b(?:DNF|DNS|DQ|DSQ|NS|NT)\b", result.get("status", ""), re.I):
        return False
    for key in ("run_time", "swim_time"):
        value = str(result.get(key, "")).strip()
        if not re.fullmatch(r"\d+(?::\d{2}){1,2}(?:\.\d+)?", value):
            return False
        if not any(float(part) > 0 for part in value.split(":")):
            return False
    return True


def attendance_qualification(results, required=4):
    """Distinct completed meets, including at least one IP or named GN championship."""
    completed = {r["event_id"]: r for r in results if completed_result(r)}
    leagues, ip, championships = {}, {}, {}
    for event_id, result in completed.items():
        if is_gn_championship(result["event_name"]):
            championships[event_id] = result
        elif result["competition_type"] == INTERPROVINCIAL:
            ip[event_id] = result
        elif result["competition_type"] == LEAGUE:
            leagues[event_id] = result
    counted = leagues | ip | championships
    shortfall = max(0, required - len(counted))
    missing = []
    if shortfall:
        missing.append(f"{shortfall} more completed event{'s' if shortfall != 1 else ''}")
    if not (ip or championships):
        missing.append("including at least 1 interprovincial or Gauteng North Championship" if shortfall
                       else "1 interprovincial or Gauteng North Championship")
    return {"Completed league events": len(leagues), "Completed interprovincial events": len(ip),
            "Completed championship events": len(championships), "Completed distinct qualifying events": len(counted),
            "Required completed events": required, "Qualified": "No" if missing else "Yes",
            "Missing to qualify": "; ".join(missing) or "None",
            "Counted events": "; ".join(f"{r['event_name']} ({r['event_date']})" for r in sorted(counted.values(), key=lambda r: (r["event_date"], r["event_id"])))}


def score_qualification(results, category):
    older = bool(re.match(r"^(?:JNR|JUNIORS?|SENIORS?|MASTERS?)\b", category.strip(), re.I))
    minimum = Decimal(1790 if older else 1890)
    scores = [numeric_points(r["total_points"]) for r in results
              if category_key(r["category"]) == category_key(category) and completed_result(r)]
    best = max((p for p in scores if p is not None), default=None)
    return f"Best completed score of at least {minimum} points required" if best is None or best < minimum else ""


def qualification_rows(snapshot):
    by_athlete = defaultdict(list)
    for result in snapshot["results"]:
        by_athlete[result["athlete_id"]].append(result)
    summaries = {row["Athlete number"]: row for row in athlete_rows(snapshot)}
    rows = []
    for athlete in snapshot["athletes"]:
        results = by_athlete[athlete["id"]]
        category = (max(results, key=lambda r: (r["event_date"], r["event_id"]))["category"]
                    if results else athlete["category"])
        required = 3 if re.match(r"^(?:JNR|JUNIORS?|SENIORS?|MASTERS?)\b", category.strip(), re.I) else 4
        qualification = attendance_qualification(results, required)
        shortfall = score_qualification(results, category)
        if shortfall:
            qualification["Missing to qualify"] = (qualification["Missing to qualify"] + "; " if qualification["Qualified"] == "No" else "") + shortfall
            qualification["Qualified"] = "No"
        rows.append({**summaries[athlete["athlete_number"]], "Category": category,
                     **qualification})
    return rows


def filtered_snapshot(snapshot, athlete_numbers):
    """Keep a coherent subset, including related events, results and awards."""
    athletes = [dict(a) for a in snapshot["athletes"] if a["athlete_number"] in athlete_numbers]
    ids = {a["id"] for a in athletes}
    results = [dict(r) for r in snapshot["results"] if r["athlete_id"] in ids]
    event_ids = {r["event_id"] for r in results}
    return {"athletes": athletes, "results": results,
            "awards": [a for a in snapshot["awards"] if a["athlete_id"] in ids],
            "events": [{**e, "result_count": sum(r["event_id"] == e["id"] for r in results)}
                       for e in snapshot["events"] if e["id"] in event_ids]}


def school_snapshot(snapshot):
    schools = {a["athlete_number"]: a["school"].strip() for a in snapshot["athletes"] if a["school"].strip()}
    # Event-specific school text can still be useful if the season profile changes.
    for result in snapshot["results"]:
        if result["school"].strip():
            schools.setdefault(result["athlete_number"], result["school"].strip())
    filtered = filtered_snapshot(snapshot, set(schools))
    for row in filtered["athletes"] + filtered["results"]:
        row["school"] = row["school"] or schools[row["athlete_number"]]
    return filtered
