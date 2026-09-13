"""Save captured times into the same historical records used by seeds and Reports."""
from datetime import date

from database.db import get_conn
from database.season_repository import season_snapshot, store_event
from parsers.season_results.models import NormalizedEvent, Result, LEAGUE, INTERPROVINCIAL, NATIONAL
from services.competition import infer_season
from services.heats import enrich_imported
from services.seeding import name_key, number_key
from validation.validators import normalize_time


def save_workflow_results(db_path, history_path, event_id):
    with get_conn(db_path) as conn:
        conn.execute("BEGIN")
        event=dict(conn.execute("SELECT * FROM events WHERE id=?",(event_id,)).fetchone())
        athletes=enrich_imported([dict(r) for r in conn.execute("SELECT * FROM athletes WHERE event_id=?",(event_id,))])
    history=season_snapshot(history_path)["athletes"]
    by_id={a["id"]:a for a in history}
    results=[]
    for athlete in athletes:
        run,swim=normalize_time(athlete.get("run_time")),normalize_time(athlete.get("swim_time"))
        if not run and not swim:
            continue
        if not athlete.get("group_name"):
            raise ValueError(f"Confirm the competed age group for {athlete['athlete_name']} before saving history.")
        matched=by_id.get(athlete.get("history_athlete_id"))
        if athlete.get("history_athlete_id") is not None and matched is None:
            raise ValueError(f"Historical identity for {athlete['athlete_name']} no longer exists; review the identity before saving.")
        numbered=[a for a in history if number_key(a["athlete_number"])==number_key(athlete["athlete_number"])]
        if not matched and numbered:
            if len(numbered)!=1 or name_key(numbered[0]["athlete_name"])!=name_key(athlete["athlete_name"]):
                raise ValueError(f"Historical athlete number conflicts for {athlete['athlete_number']} · {athlete['athlete_name']}. Resolve the identity before saving history.")
            matched=numbered[0]
        number=matched["athlete_number"] if matched else athlete["athlete_number"]
        results.append(Result(number,athlete["athlete_name"],athlete["group_name"],
            run_time=run or "",swim_time=swim or "",run_distance=athlete.get("run_distance"),
            swim_distance=athlete.get("swim_distance"),province=athlete.get("province") or "",
            team=athlete.get("province") or "",school=matched["school"] if matched else "",
            annotations="Captured event times; published points not supplied"))
    if not results:
        raise ValueError("There are no valid captured times to save.")
    normalized=NormalizedEvent(event["name"],date.fromisoformat(event["start_date"]),
        {"Local":LEAGUE,"Interprovincial":INTERPROVINCIAL,"National":NATIONAL}[event["meet_type"]],
        f"Event session {event_id}",results,season_year=event["season_year"] or infer_season(event["start_date"]),
        workflow_key=event["history_key"],result_source="workflow")
    return store_event(history_path,normalized,overwrite=True)
