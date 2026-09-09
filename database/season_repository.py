"""Season storage operations. UI, parsers and exporters never issue SQL."""
from __future__ import annotations

from datetime import datetime, timezone

from .db import get_conn
from parsers.season_results.models import NormalizedEvent
from parsers.season_records import validate_record_benchmarks


class EventAlreadyExists(ValueError):
    pass


def reset_season_database(db_path) -> None:
    """Clear only season data atomically, preserving schema and workflow sessions."""
    with get_conn(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM season_events")  # Cascades results and awards.
        conn.execute("DELETE FROM season_athletes")
        conn.execute("DELETE FROM season_record_benchmarks")
        conn.execute("DELETE FROM season_record_templates")


def replace_record_benchmarks(db_path, records, source_filename, template_bytes=None):
    if template_bytes:
        from io import BytesIO
        from parsers.season_records import parse_record_benchmarks
        records = parse_record_benchmarks(BytesIO(template_bytes))
    else:
        records = validate_record_benchmarks(records)
    with get_conn(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM season_record_benchmarks")
        conn.execute("DELETE FROM season_record_templates")
        if template_bytes:
            conn.execute("INSERT INTO season_record_templates VALUES (1, ?, ?)", (source_filename, template_bytes))
        imported_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        conn.executemany("""INSERT INTO season_record_benchmarks
            (category_key, category, athlete_number, athlete_name, total_points, source_filename, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [(r["category_key"], r["category"], r["athlete_number"], r["athlete_name"], r["total_points"],
              source_filename, imported_at) for r in records])


def find_event(db_path, event: NormalizedEvent):
    if not event.event_date:
        return None
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM season_events WHERE identity=? AND event_date=? AND competition_type=?",
            (event.identity, event.event_date.isoformat(), event.competition_type),
        ).fetchone()
    return dict(row) if row else None


def store_event(db_path, event: NormalizedEvent, *, overwrite: bool = False) -> int:
    from services.season_scope import gn_event
    event = gn_event(event)
    event.check_structure()
    with get_conn(db_path) as conn:
        # Serialize duplicate check + replacement, including concurrent browser imports.
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT id FROM season_events WHERE identity=? AND event_date=? AND competition_type=?",
            (event.identity, event.event_date.isoformat(), event.competition_type),
        ).fetchone()
        if existing and not overwrite:
            raise EventAlreadyExists("This event already exists. Overwrite the existing event results or skip this event?")
        imported_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        if existing:
            event_id = existing["id"]
            conn.execute("DELETE FROM season_results WHERE event_id=?", (event_id,))
            conn.execute("UPDATE season_events SET name=?, source_filename=?, imported_at=? WHERE id=?",
                         (event.name.strip(), event.source_filename, imported_at, event_id))
        else:
            event_id = conn.execute(
                "INSERT INTO season_events(identity, name, event_date, competition_type, source_filename, imported_at) VALUES (?, ?, ?, ?, ?, ?)",
                (event.identity, event.name.strip(), event.event_date.isoformat(), event.competition_type, event.source_filename, imported_at),
            ).lastrowid
        affiliated_awards = {a.athlete_number for a in event.awards if a.affiliated}
        ids = {}
        for r in event.results:
            conn.execute("""
                INSERT INTO season_athletes(athlete_number, athlete_name, school, category, province, team, affiliated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(athlete_number) DO UPDATE SET
                    athlete_name=excluded.athlete_name,
                    school=COALESCE(NULLIF(excluded.school, ''), season_athletes.school),
                    category=COALESCE(NULLIF(excluded.category, ''), season_athletes.category),
                    province=COALESCE(NULLIF(excluded.province, ''), season_athletes.province),
                    team=COALESCE(NULLIF(excluded.team, ''), season_athletes.team),
                    affiliated=MAX(season_athletes.affiliated, excluded.affiliated)
            """, (r.athlete_number, r.athlete_name, r.school, r.category, r.province, r.team,
                  int(r.affiliated or r.athlete_number in affiliated_awards)))
            athlete_id = conn.execute("SELECT id FROM season_athletes WHERE athlete_number=?", (r.athlete_number,)).fetchone()["id"]
            ids[r.athlete_number] = athlete_id
            conn.execute("""
                INSERT INTO season_results(event_id, athlete_id, athlete_name, category, position,
                    run_time, running_points, swim_time, swimming_points, bonus_points, total_points,
                    status, school, province, team, annotations)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (event_id, athlete_id, r.athlete_name, r.category, r.position, r.run_time, r.running_points,
                  r.swim_time, r.swimming_points, r.bonus_points, r.total_points, r.status,
                  r.school, r.province, r.team, r.annotations))
        for award in event.awards:
            conn.execute("INSERT INTO season_awards(event_id, athlete_id, award_type, placing) VALUES (?, ?, ?, ?)",
                         (event_id, ids[award.athlete_number], award.award_type, award.placing))
    return event_id


def set_affiliation(db_path, athlete_id: int, affiliated: bool) -> None:
    """Explicit manual corrections may set either value; imports only promote."""
    if not isinstance(affiliated, bool):
        raise ValueError("Affiliation must be Yes or No.")
    with get_conn(db_path) as conn:
        cursor = conn.execute("UPDATE season_athletes SET affiliated=? WHERE id=?", (int(affiliated), athlete_id))
        if cursor.rowcount != 1:
            raise ValueError("Athlete no longer exists.")


def season_snapshot(db_path) -> dict[str, list[dict]]:
    """Read one consistent snapshot for browse/export, even during an overwrite."""
    with get_conn(db_path) as conn:
        conn.execute("BEGIN")
        events = conn.execute("""
            SELECT e.*, COUNT(r.athlete_id) AS result_count FROM season_events e
            LEFT JOIN season_results r ON r.event_id=e.id GROUP BY e.id ORDER BY e.event_date, e.id
        """).fetchall()
        athletes = conn.execute("""
            SELECT a.*, COUNT(r.event_id) AS events_attended FROM season_athletes a
            LEFT JOIN season_results r ON r.athlete_id=a.id GROUP BY a.id ORDER BY a.athlete_name, a.athlete_number
        """).fetchall()
        results = conn.execute("""
            SELECT r.*, a.athlete_number, e.name AS event_name, e.event_date, e.competition_type
            FROM season_results r JOIN season_athletes a ON a.id=r.athlete_id
            JOIN season_events e ON e.id=r.event_id ORDER BY e.event_date, e.id, r.category, CAST(r.position AS INTEGER), a.id
        """).fetchall()
        awards = conn.execute("""
            SELECT w.*, a.athlete_number, a.athlete_name, e.name AS event_name, e.event_date
            FROM season_awards w JOIN season_athletes a ON a.id=w.athlete_id
            JOIN season_events e ON e.id=w.event_id ORDER BY e.event_date, e.id, w.award_type, w.placing
        """).fetchall()
        records = conn.execute("SELECT * FROM season_record_benchmarks ORDER BY category_key").fetchall()
        templates = conn.execute("SELECT source_filename, content FROM season_record_templates").fetchall()
    return {key: [dict(row) for row in rows] for key, rows in
            (("events", events), ("athletes", athletes), ("results", results), ("awards", awards), ("records", records), ("record_templates", templates))}
