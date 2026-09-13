"""Small import decisions and presentation projections for the season module."""
from __future__ import annotations

from database.season_repository import find_event, store_event
from database.migrations import validate_season


def import_summary(db_path, event):
    from services.season_scope import gn_event
    filtered = gn_event(event)
    existing = find_event(db_path, event)
    return {
        "Source file": event.source_filename, "Event": event.name,
        "Date": event.event_date, "Competition type": event.competition_type or "Confirm type",
        "Season": event.season_year if event.season_year is not None else "Unassigned",
        "Results": len(filtered.results), "Awards": len(filtered.awards),
        "Excluded non-GN / unknown team": len(event.results) - len(filtered.results),
        "Status": "Already Imported" if existing else "New",
    }


def import_event(db_path, event, action="Import"):
    if action == "Skip":
        return None
    if action not in {"Import", "Overwrite"}:
        raise ValueError("Choose Import, Overwrite or Skip.")
    validate_season(event.season_year, required=True)
    return store_event(db_path, event, overwrite=action == "Overwrite")


def athlete_rows(snapshot):
    awards = {}
    for award in snapshot["awards"]:
        placing = {1: "1st", 2: "2nd", 3: "3rd"}[award["placing"]]
        title = "Athlete" if award["award_type"] == "Overall Athlete" else award["award_type"]
        awards.setdefault(award["athlete_id"], []).append(f"{award['event_name']} - {placing} Top {title}")
    return [{
        "Athlete number": a["athlete_number"], "Athlete name": a["athlete_name"],
        "School": a["school"], "Category": a["category"], "Province": a["province"], "Team": a["team"],
        "Affiliated": "Affiliated" if a["affiliated"] else "Not Affiliated",
        "Events attended": a["events_attended"], "Event awards": "; ".join(awards.get(a["id"], [])),
    } for a in snapshot["athletes"]]
