"""Small participation follow-up lists based on distinct imported event attendance."""
from collections import defaultdict
from services.season_reports import age_group_sort_key, numeric_points, completed_result, category_key


def insight_sections(snapshot, *, affiliation_only=False):
    grouped = defaultdict(list)
    for r in snapshot["results"]:
        grouped[r["athlete_id"]].append(r)
    athletes, categories = [], defaultdict(set)
    for a in snapshot["athletes"]:
        results = grouped[a["id"]]
        if not results:
            continue
        latest = max(results, key=lambda r: (r["event_date"], r["event_id"]))
        category = category_key(latest["category"])
        categories[category].add(a["id"])
        scores = [numeric_points(r["total_points"]) for r in results if completed_result(r) and category_key(r["category"]) == category]
        best = max((p for p in scores if p is not None), default=None)
        athletes.append({"Athlete number": a["athlete_number"], "Athlete name": a["athlete_name"],
                         "Age group": category, "School": a["school"], "Events attended": len({r["event_id"] for r in results}),
                         "Affiliated": "Affiliated" if a["affiliated"] else "Not Affiliated",
                         "Best total points": float(best) if best is not None else ""})
    followup = [{k: v for k, v in a.items() if k != "Best total points"} for a in athletes
                if a["Events attended"] >= 2 and a["Affiliated"] == "Not Affiliated"]
    followup.sort(key=lambda r: (-r["Events attended"], r["Athlete name"]))
    affiliation = ("Affiliation follow-up: two or more events, not affiliated", ["Athlete number", "Athlete name", "Age group", "School", "Events attended", "Affiliated"], followup)
    if affiliation_only:
        return [affiliation]
    counts = [{"Event": e["name"], "Date": e["event_date"], "Athletes": len({r["athlete_id"] for r in snapshot["results"] if r["event_id"] == e["id"]})}
              for e in sorted(snapshot["events"], key=lambda e: (e["event_date"], e["id"]))]
    small = [{"Age group": c, "Athletes": len(ids), "Additional athletes to reach six": 6 - len(ids)}
             for c, ids in sorted(categories.items(), key=lambda item: age_group_sort_key(item[0])) if len(ids) < 6]
    # Strong is explicitly defined as a top-three season score within the latest category.
    one_off = []
    for a in athletes:
        if a["Events attended"] != 1 or a["Best total points"] == "":
            continue
        rank = 1 + sum(b["Age group"] == a["Age group"] and b["Best total points"] != ""
                       and b["Best total points"] > a["Best total points"] for b in athletes)
        if rank <= 3:
            one_off.append({**a, "Category rank": rank})
    one_off.sort(key=lambda r: (age_group_sort_key(r["Age group"]), r["Category rank"], r["Athlete name"]))
    return [("Participation by event", ["Event", "Date", "Athletes"], counts),
            ("Age groups with fewer than six athletes (latest category)", ["Age group", "Athletes", "Additional athletes to reach six"], small),
            ("Top-three category performers who attended only one event", ["Athlete number", "Athlete name", "Age group", "School", "Events attended", "Best total points", "Category rank"], one_off), affiliation]
