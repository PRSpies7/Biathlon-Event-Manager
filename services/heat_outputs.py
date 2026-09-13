"""Build and store one revision-consistent operational package."""
import json

from database.db import get_conn
from exporters.heats import build_heats_pdf, build_heats_xlsx
from exporters.athlete_event_mapping import build_printable_athlete_mapping_xlsx
from exporters.swim_timekeeper import build_swim_timekeeper_xlsx
from exporters.timedrops_json import generate_timedrops_json, dumps_json
from services.heats import enrich_imported, validate_heats

XLSX="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def build_package(rows,event,reference):
    rows=enrich_imported(rows)
    errors,_=validate_heats(rows,event)
    if errors:
        raise ValueError("\n".join(errors))
    program=generate_timedrops_json(reference,rows,meet_name=event["name"],host_team=event["host_team"],
        start_date=event["start_date"],course=event["course"],pool_lanes=event["pool_lanes"],meet_type=event["meet_type"])
    return {
        "Combined Heats.pdf":("application/pdf",build_heats_pdf(rows,event).getvalue()),
        "Master Entries Heats.xlsx":(XLSX,build_heats_xlsx(rows,event).getvalue()),
        "Athlete Run Swim Lane Sheet.xlsx":(XLSX,build_printable_athlete_mapping_xlsx(rows).getvalue()),
        "Swim Timekeeper Sheets.xlsx":(XLSX,build_swim_timekeeper_xlsx(rows,event["name"],event["pool_lanes"]).getvalue()),
        "meet_program.json":("application/json",dumps_json(program).encode("utf-8")),
    }


def generate_outputs(db_path,event_id,reference):
    with get_conn(db_path) as conn:
        conn.execute("BEGIN")
        event=dict(conn.execute("SELECT * FROM events WHERE id=?",(event_id,)).fetchone())
        if event["heat_status"]!="approved" or event["approved_revision"]!=event["heat_revision"]:
            raise ValueError("Review and approve both disciplines before generating files.")
        rows=[dict(r) for r in conn.execute("SELECT * FROM athletes WHERE event_id=? ORDER BY sort_order",(event_id,))]
    files=build_package(rows,event,reference)
    with get_conn(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        current=conn.execute("SELECT * FROM events WHERE id=?",(event_id,)).fetchone()
        if current["heat_revision"]!=event["heat_revision"] or current["heat_status"]!="approved":
            raise ValueError("Assignments changed during export. Review and regenerate the files.")
        conn.execute("DELETE FROM event_outputs WHERE event_id=?",(event_id,))
        conn.executemany("INSERT INTO event_outputs VALUES (?,?,?,?,?)",
            [(event_id,event["heat_revision"],name,mime,content) for name,(mime,content) in files.items()])
        conn.execute("UPDATE events SET exports_revision=heat_revision WHERE id=?",(event_id,))
    return files


def current_outputs(db_path,event_id):
    with get_conn(db_path) as conn:
        return {r["filename"]:(r["mime"],r["content"]) for r in conn.execute("""
            SELECT o.* FROM event_outputs o JOIN events e ON e.id=o.event_id
            WHERE e.id=? AND e.heat_status='approved' AND e.approved_revision=e.heat_revision
              AND e.exports_revision=e.heat_revision AND o.revision=e.heat_revision""",(event_id,))}
